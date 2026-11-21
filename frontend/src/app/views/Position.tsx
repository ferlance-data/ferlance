// Financial position: dated balances rolled into a point-in-time statement.

import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money } from '../../lib/format';
import { Icon } from '../../lib/icons';
import { POSITION_LABELS, printPositionReport } from '../../lib/reports';
import type { BalanceHistoryRow, PositionBalance, PositionResult } from '../../lib/types';
import { DataTable, Kpi, Notice, Pill, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import { categoryOptionGroups, CATEGORY_GROUPS, minimumBalance } from './position.logic';

const OPTION_GROUPS = categoryOptionGroups(POSITION_LABELS);

function GroupCard({ title, items, total, asOf }: { title: string; items: PositionBalance[]; total: number; asOf: string }) {
  return (
    <div className="card statement-group">
      <div className="card-header">
        <h3>{title}</h3>
        <span className="num">{money(total)}</span>
      </div>
      <div className="table-wrap" style={{ marginTop: '8px' }}>
        <DataTable
          columns={[
            {
              label: 'Account',
              value: (item) => (
                <div className="file-cell">
                  <strong>{item.account_name}</strong>
                  <small>{POSITION_LABELS[item.category] || item.category}</small>
                </div>
              ),
            },
            {
              label: 'Balance date',
              value: (item) =>
                item.as_of_date < asOf ? (
                  <span>
                    {formatDate(item.as_of_date)} <Pill tone="warning">Carried forward</Pill>
                  </span>
                ) : (
                  formatDate(item.as_of_date)
                ),
            },
            { label: 'Balance', num: true, value: (item) => money(item.amount) },
          ]}
          rows={items}
          rowKey={(item, index) => `${item.category}:${item.account_name}:${index}`}
          empty={`No ${title.toLowerCase()} recorded on or before this date.`}
        />
      </div>
    </div>
  );
}

export default function Position() {
  const { user, business, businessPath, markSetup, setup } = useWorkspace();
  const queryClient = useQueryClient();
  const today = isoDate(new Date());
  const [asOf, setAsOf] = useState(today);
  const [balanceDate, setBalanceDate] = useState(today);
  const [category, setCategory] = useState('cash');
  const [account, setAccount] = useState('');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [status, setStatus] = useState<{ message: string; error: boolean }>({ message: '', error: false });
  const [saving, setSaving] = useState(false);

  const reportQuery = useQuery({
    queryKey: keys.business(business.id, `/financial-position?as_of=${asOf}`),
    queryFn: ({ signal }) => request<PositionResult>(businessPath(`/financial-position?as_of=${encodeURIComponent(asOf)}`), { signal }),
    enabled: Boolean(asOf),
    placeholderData: keepPreviousData,
  });
  const historyQuery = useQuery({
    queryKey: keys.business(business.id, '/financial-position/history'),
    queryFn: ({ signal }) => request<BalanceHistoryRow[]>(businessPath('/financial-position/history'), { signal }),
  });
  const result = reportQuery.data;
  const history = historyQuery.data;

  const hasBalances = history ? history.length > 0 : null;
  useEffect(() => {
    if (hasBalances !== null && hasBalances !== setup.balances) markSetup({ balances: hasBalances });
  }, [hasBalances, setup.balances, markSetup]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    try {
      const saved = await request<PositionBalance>(businessPath('/financial-position/balances'), {
        method: 'POST',
        json: { as_of_date: balanceDate, category, account_name: account, amount: Number(amount), note },
      });
      setAccount('');
      setAmount('');
      setNote('');
      if (saved.as_of_date > asOf) setAsOf(saved.as_of_date);
      await queryClient.invalidateQueries({ queryKey: keys.business(business.id) });
      setStatus({ message: `Saved ${POSITION_LABELS[saved.category]} for ${formatDate(saved.as_of_date)}.`, error: false });
    } catch (error) {
      setStatus({ message: error instanceof Error ? error.message : 'Request failed.', error: true });
    } finally {
      setSaving(false);
    }
  };

  const totals = result?.totals;

  return (
    <>
      <PageActions>
        <button className="btn btn-secondary" type="button" onClick={() => result && printPositionReport(result, { business, user })}>
          <Icon name="printer" />
          <span className="btn-label">Print statement</span>
        </button>
      </PageActions>

      <div className="toolbar toolbar-plain">
        <label className="field field-inline">
          As of
          <input className="input" id="position-date" type="date" required value={asOf} onChange={(event) => setAsOf(event.target.value)} />
        </label>
        <span id="position-check">
          {totals ? (
            totals.complete ? (
              totals.balanced ? <Pill tone="success" icon="check">Statement balances</Pill> : <Pill tone="error" icon="alert">Does not balance</Pill>
            ) : (
              <Pill tone="warning" icon="alert">Partial statement</Pill>
            )
          ) : null}
        </span>
      </div>

      <div className="kpi-grid" id="position-kpis">
        {totals && result ? (
          <>
            <Kpi label="Total assets" value={money(totals.assets)} icon="coins" />
            <Kpi label="Total liabilities" value={money(totals.liabilities)} icon="receipt" />
            <Kpi label="Equity" value={money(totals.equity)} icon="scale" />
            <Kpi label={totals.complete ? 'Assets − liabilities − equity' : 'Known difference (partial)'} value={money(totals.balance_difference)} icon="check" />
          </>
        ) : null}
      </div>

      <div id="position-warnings" className="stack-sm">
        {result?.missing_categories.length ? (
          <Notice>{`Missing categories: ${result.missing_categories.map((item) => item.label).join(', ')}. Record each, including zero balances, for a complete statement.`}</Notice>
        ) : null}
        {result?.stale_balances.length ? <Notice tone="warning" icon="info">{`${result.stale_balances.length} balance(s) are carried forward from earlier dates.`}</Notice> : null}
      </div>

      <div className="grid-main">
        <div className="stack" id="position-groups">
          {result && totals ? (
            <>
              <GroupCard title="Assets" items={result.assets} total={totals.assets} asOf={result.as_of_date} />
              <GroupCard title="Liabilities" items={result.liabilities} total={totals.liabilities} asOf={result.as_of_date} />
              <GroupCard title="Equity" items={result.equity} total={totals.equity} asOf={result.as_of_date} />
            </>
          ) : null}
        </div>
        <div className="stack">
          <form className="card" id="balance-form" onSubmit={(event) => void submit(event)}>
            <div className="card-header">
              <div>
                <h2 className="card-title">Record a balance</h2>
                <p className="card-subtitle">Enter zero explicitly when a balance is zero</p>
              </div>
            </div>
            <div className="card-body form-grid">
              <label className="field">
                Balance date
                <input className="input" id="balance-date" type="date" required value={balanceDate} onChange={(event) => setBalanceDate(event.target.value)} />
              </label>
              <label className="field">
                Category
                <select className="select" id="balance-category" required value={category} onChange={(event) => setCategory(event.target.value)}>
                  {OPTION_GROUPS.map((group) => (
                    <optgroup key={group.group} label={group.group}>
                      {group.options.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              <label className="field">
                Account
                <input className="input" id="balance-account" maxLength={120} required placeholder="e.g. GCB current account" value={account} onChange={(event) => setAccount(event.target.value)} />
              </label>
              <label className="field">
                Balance
                <input className="input" id="balance-amount" type="number" step="0.01" min={minimumBalance(category)} required value={amount} onChange={(event) => setAmount(event.target.value)} />
              </label>
              <label className="field">
                Note
                <input className="input" id="balance-note" maxLength={500} placeholder="Optional" value={note} onChange={(event) => setNote(event.target.value)} />
              </label>
              <button className="btn btn-primary" type="submit" disabled={saving}>Save balance</button>
              <StatusText id="balance-status" message={status.message} error={status.error} />
            </div>
          </form>
          <div className="card">
            <div className="card-body body-sm muted stack-sm">
              <p>
                <strong className="fg">How this works.</strong> Each account carries forward its latest balance on or before the report date. Missing categories stay visibly incomplete — zero is never assumed.
              </p>
              <p>This is an operational view, not a tax filing or full general ledger. Verify opening balances with your accountant.</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Balance history</h2>
            <p className="card-subtitle">Dated entries behind every statement</p>
          </div>
        </div>
        <div className="table-wrap" id="position-history">
          {history ? (
            <DataTable
              columns={[
                { label: 'Balance date', value: (item) => formatDate(item.as_of_date) },
                { label: 'Account', value: (item) => item.account_name },
                { label: 'Category', value: (item) => `${CATEGORY_GROUPS[item.category] || ''} · ${POSITION_LABELS[item.category] || item.category}` },
                { label: 'Balance', num: true, value: (item) => money(item.amount) },
                { label: 'Note', value: (item) => item.note || '—' },
                { label: 'Recorded by', value: (item) => item.recorded_by },
              ]}
              rows={history}
              rowKey={(item, index) => `${item.id ?? index}`}
              empty="No balances recorded yet. Start with cash on hand and your bank balance."
            />
          ) : null}
        </div>
      </div>
    </>
  );
}
