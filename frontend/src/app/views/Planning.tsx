// Planning: recurring expenses (confirmed each month, never automatic), budgets against what
// actually happened, and downloads (the accountant's year-end pack, and all your data).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money } from '../../lib/format';
import { Icon } from '../../lib/icons';
import { toast } from '../../lib/toast';
import { DataTable, EmptyState, ListHeader, Modal, Notice, Pill, Segmented, SkeletonRows, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import { METHOD_LABEL } from './debts.logic';
import { EXPENSE_KINDS } from './reconcile.logic';

interface RecurringState {
  items: {
    id: string;
    name: string;
    account: string;
    amount: number;
    paid_from: string;
    day_of_month: number;
    start_month: string;
    end_month: string | null;
    active: boolean;
  }[];
  due: { item_id: string; name: string; month: string; due_on: string; amount: number }[];
  history: { item_id: string; month: string; status: 'confirmed' | 'skipped'; amount: number; posted_on: string }[];
}

interface BudgetState {
  month: string;
  lines: {
    account: string;
    name: string;
    type: 'income' | 'expense';
    budget: number | null;
    actual: number;
    used_pct: number | null;
    over: boolean;
  }[];
}

const BUDGET_ACCOUNTS: Record<string, string> = { sales: 'Sales', cogs: 'Cost of goods sold', ...EXPENSE_KINDS };

async function download(path: string, filename: string) {
  try {
    const blob = await request<Blob>(path, { asBlob: true });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  } catch (error) {
    toast((error as Error).message, { error: true });
  }
}

function Recurring({ editable }: { editable: boolean }) {
  const { business, businessPath } = useWorkspace();
  const queryClient = useQueryClient();
  const state = useQuery({
    queryKey: keys.business(business.id, 'recurring'),
    queryFn: ({ signal }) => request<RecurringState>(businessPath('/recurring'), { signal }),
  });
  const [form, setForm] = useState({
    name: '',
    account: 'rent',
    amount: '',
    paid_from: 'momo_mtn',
    day_of_month: '1',
    start_month: isoDate(new Date()).slice(0, 7),
  });
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const [adding, setAdding] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.business(business.id) });

  async function call(path: string, method: 'POST' | 'DELETE', json?: unknown, done?: string): Promise<boolean> {
    try {
      await request(businessPath(path), { method, json });
      if (done) toast(done);
      setStatus(null);
      await refresh();
      return true;
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
      return false;
    }
  }

  if (!state.data) return <SkeletonRows count={4} />;
  const names = Object.fromEntries(state.data.items.map((item) => [item.id, item.name]));
  return (
    <>
      <ListHeader
        title="Regular payments"
        subtitle="Rent, subscriptions, regular staff payments outside payroll"
        action={editable ? 'Add a regular payment' : undefined}
        onAction={() => setAdding(true)}
      />
      <div className="card" id="recurring-due">
        <div className="card-header">
          <div>
            <h2 className="card-title">Due to confirm</h2>
            <p className="card-subtitle">Nothing is booked until you confirm it was paid, with the real amount.</p>
          </div>
        </div>
        {state.data.due.length ? (
          <ul className="debt-list">
            {state.data.due.map((due) => {
              const key = `${due.item_id}:${due.month}`;
              return (
                <li className="debt-card" key={key}>
                  <div className="debt-head">
                    <div className="file-cell">
                      <strong>{due.name}</strong>
                      <small>{`${due.month} · due ${formatDate(due.due_on)}`}</small>
                    </div>
                    <span className="num">{money(due.amount)}</span>
                  </div>
                  {editable ? (
                    <div className="button-row">
                      <input
                        className="input recurring-amount"
                        inputMode="decimal"
                        aria-label={`Amount paid for ${due.name} in ${due.month}`}
                        value={amounts[key] ?? String(due.amount)}
                        onChange={(event) => setAmounts({ ...amounts, [key]: event.target.value })}
                      />
                      <button
                        className="btn btn-primary btn-sm"
                        type="button"
                        onClick={() =>
                          void call(
                            `/recurring/${due.item_id}/decide`,
                            'POST',
                            { month: due.month, confirm: true, amount: Number(amounts[key] ?? due.amount) },
                            `${due.name} for ${due.month} booked.`,
                          )
                        }
                      >
                        Paid
                      </button>
                      <button
                        className="btn btn-ghost btn-sm"
                        type="button"
                        onClick={() =>
                          void call(`/recurring/${due.item_id}/decide`, 'POST', { month: due.month, confirm: false }, 'Skipped.')
                        }
                      >
                        Skip this month
                      </button>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState title="Nothing due" />
        )}
        <StatusText message={status?.message} error={status?.error} />
      </div>

      {adding ? (
        <Modal label="Add a regular payment" onClose={() => setAdding(false)}>
          <form
            className="card"
            id="recurring-add"
            onSubmit={(event: FormEvent) => {
              event.preventDefault();
              void call(
                '/recurring',
                'POST',
                { ...form, amount: Number(form.amount), day_of_month: Number(form.day_of_month) },
                `${form.name} added.`,
              ).then((ok) => {
                if (!ok) return;
                setForm({ ...form, name: '', amount: '' });
                setAdding(false);
              });
            }}
          >
            <div className="card-header">
              <div>
                <h2 className="card-title">Add a regular payment</h2>
                <p className="card-subtitle">Rent, a subscription, a regular staff payment outside payroll…</p>
              </div>
            </div>
            <div className="card-body form-grid">
              <label className="field">
                Name
                <input
                  className="input"
                  required
                  maxLength={120}
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </label>
              <label className="field">
                Kind
                <select className="select" value={form.account} onChange={(event) => setForm({ ...form, account: event.target.value })}>
                  {Object.entries(EXPENSE_KINDS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Usual amount
                <input
                  className="input"
                  required
                  inputMode="decimal"
                  value={form.amount}
                  onChange={(event) => setForm({ ...form, amount: event.target.value })}
                />
              </label>
              <label className="field">
                Paid from
                <select className="select" value={form.paid_from} onChange={(event) => setForm({ ...form, paid_from: event.target.value })}>
                  {['momo_mtn', 'momo_telecel', 'momo_at', 'bank', 'cash'].map((key) => (
                    <option key={key} value={key}>
                      {METHOD_LABEL[key]}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Day of the month
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={28}
                  value={form.day_of_month}
                  onChange={(event) => setForm({ ...form, day_of_month: event.target.value })}
                />
              </label>
              <label className="field">
                First month
                <input
                  className="input"
                  type="month"
                  value={form.start_month}
                  onChange={(event) => setForm({ ...form, start_month: event.target.value })}
                />
              </label>
              <div className="button-row">
                <button className="btn btn-secondary" type="submit">
                  Add
                </button>
              </div>
            </div>
          </form>
        </Modal>
      ) : null}

      <div className="card" id="recurring-items">
        <div className="card-header">
          <div>
            <h2 className="card-title">Regular payments</h2>
          </div>
        </div>
        <div className="table-wrap">
          <DataTable
            columns={[
              { label: 'Name', value: (item) => item.name },
              { label: 'Amount', num: true, value: (item) => money(item.amount) },
              { label: 'Day', num: true, value: (item) => item.day_of_month },
              {
                label: '',
                value: (item) =>
                  item.active ? (
                    editable ? (
                      <button
                        className="btn btn-ghost btn-sm"
                        type="button"
                        onClick={() => void call(`/recurring/${item.id}/stop`, 'POST', undefined, 'Stopped.')}
                      >
                        Stop
                      </button>
                    ) : (
                      <Pill tone="success">Active</Pill>
                    )
                  ) : (
                    <Pill>Stopped</Pill>
                  ),
              },
            ]}
            rows={state.data.items}
            rowKey={(item) => item.id}
            empty="No regular payments yet."
          />
        </div>
        {state.data.history.length ? (
          <div className="card-body">
            <ul className="pending-invites">
              {state.data.history.map((row) => (
                <li key={`${row.item_id}:${row.month}`}>
                  <span>{`${names[row.item_id] ?? ''} · ${row.month} · ${row.status === 'confirmed' ? money(row.amount) : 'skipped'}`}</span>
                  {editable ? (
                    <button
                      className="btn btn-ghost btn-sm"
                      type="button"
                      onClick={() => void call(`/recurring/${row.item_id}/months/${row.month}`, 'DELETE', undefined, 'Undone.')}
                    >
                      Undo
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </>
  );
}

function Budgets({ editable }: { editable: boolean }) {
  const { business, businessPath } = useWorkspace();
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(isoDate(new Date()).slice(0, 7));
  const state = useQuery({
    queryKey: keys.business(business.id, 'budgets', month),
    queryFn: ({ signal }) => request<BudgetState>(businessPath(`/budgets?month=${month}`), { signal }),
  });
  const [account, setAccount] = useState('rent');
  const [amount, setAmount] = useState('');
  const [setting, setSetting] = useState(false);

  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await request(businessPath('/budgets'), { method: 'PUT', json: { month, account, amount: Number(amount) } });
      setAmount('');
      setSetting(false);
      await queryClient.invalidateQueries({ queryKey: keys.business(business.id, 'budgets', month) });
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  return (
    <div className="card" id="budgets">
      <div className="card-header">
        <div>
          <h2 className="card-title">Budget and actual</h2>
          <p className="card-subtitle">Actuals come from your books.</p>
        </div>
        <div className="list-header-actions">
          <input className="input" type="month" aria-label="Month" value={month} onChange={(event) => setMonth(event.target.value)} />
          {editable ? (
            <button className="btn btn-primary" type="button" onClick={() => setSetting(true)}>
              Set a budget
            </button>
          ) : null}
        </div>
      </div>
      {state.data ? (
        <div className="table-wrap">
          <DataTable
            columns={[
              { label: 'Account', value: (line) => line.name },
              { label: 'Budget', num: true, value: (line) => (line.budget == null ? '—' : money(line.budget)) },
              { label: 'Actual', num: true, value: (line) => money(line.actual) },
              {
                label: '',
                value: (line) =>
                  line.used_pct == null ? null : (
                    <Pill
                      tone={line.over ? 'error' : line.type === 'income' && line.used_pct < 100 ? 'warning' : 'success'}
                    >{`${line.used_pct}%`}</Pill>
                  ),
              },
            ]}
            rows={state.data.lines}
            rowKey={(line) => line.account}
            empty="No budget or activity this month."
          />
        </div>
      ) : (
        <SkeletonRows count={3} />
      )}
      {setting ? (
        <Modal label="Set a budget" onClose={() => setSetting(false)}>
          <div className="card-header">
            <div>
              <h2 className="card-title">{`Set a budget for ${month}`}</h2>
            </div>
          </div>
          <form className="card-body form-grid" onSubmit={(event) => void save(event)}>
            <label className="field">
              Account
              <select className="select" value={account} onChange={(event) => setAccount(event.target.value)}>
                {Object.entries(BUDGET_ACCOUNTS).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {`Budget for ${month}`}
              <input className="input" required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
              <span className="field-hint">0 removes the budget.</span>
            </label>
            <div className="button-row">
              <button className="btn btn-secondary" type="submit">
                Save budget
              </button>
            </div>
          </form>
        </Modal>
      ) : null}
    </div>
  );
}

function Downloads() {
  const { businessPath, can } = useWorkspace();
  const [year, setYear] = useState(new Date().getFullYear());
  return (
    <div className="card" id="downloads">
      <div className="card-header">
        <div>
          <h2 className="card-title">Downloads</h2>
          <p className="card-subtitle">Spreadsheet files (CSV) inside a zip.</p>
        </div>
      </div>
      <div className="card-body form-grid">
        {can('manage_books') ? (
          <>
            <label className="field">
              Year-end pack for your accountant
              <input
                className="input"
                type="number"
                min={2000}
                max={2100}
                value={year}
                onChange={(event) => setYear(Number(event.target.value))}
              />
              <span className="field-hint">
                Trial balance, profit and loss, balance sheet, the year's journal, debtors, creditors and stock value.
              </span>
            </label>
            <div className="button-row">
              <button
                className="btn btn-secondary"
                type="button"
                onClick={() => void download(businessPath(`/year-end.zip?year=${year}`), `ferlance-year-end-${year}.zip`)}
              >
                <Icon name="download" />
                <span className="btn-label">Download year-end pack</span>
              </button>
            </div>
          </>
        ) : null}
        {can('manage_business') ? (
          <div className="button-row">
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => void download(businessPath('/my-data.zip'), 'ferlance-my-data.zip')}
            >
              <Icon name="download" />
              <span className="btn-label">Download all my data</span>
            </button>
          </div>
        ) : null}
        {!can('manage_books') ? (
          <Notice tone="info" icon="info">
            Downloads are for the owner and the accountant.
          </Notice>
        ) : null}
      </div>
    </div>
  );
}

export default function Planning() {
  const { can } = useWorkspace();
  const editable = can('manage_books');
  const [tab, setTab] = useState<'recurring' | 'budgets' | 'downloads'>('recurring');
  return (
    <>
      <PageActions>
        <Segmented
          id="planning-tabs"
          label="Planning section"
          mode="tabs"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'recurring', label: 'Recurring' },
            { value: 'budgets', label: 'Budgets' },
            { value: 'downloads', label: 'Downloads' },
          ]}
        />
      </PageActions>
      {tab === 'recurring' ? <Recurring editable={editable} /> : tab === 'budgets' ? <Budgets editable={editable} /> : <Downloads />}
    </>
  );
}
