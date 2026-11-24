// Reconcile: import a MoMo or bank statement, see which lines the books already have, book the
// rest, and check that the statement balance and the books agree, every cedi explained.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, money } from '../../lib/format';
import { toast } from '../../lib/toast';
import { EmptyState, Notice, Pill, ReadOnlyNotice, Segmented, SkeletonRows, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import type { DebtBook } from './debts.logic';
import { BOOKING_LABEL, EXPENSE_KINDS, FIELD_LABEL, OTHER_ACCOUNTS, categoriesFor, type Field, type Overview, type Preview, type Reconciliation, type StatementLine } from './reconcile.logic';

function ImportStatement({ choices, onDone }: { choices: Record<string, string>; onDone: (account: string) => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const [account, setAccount] = useState('momo_mtn');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<Field, number | null> | null>(null);
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  async function look(chosen: File) {
    setFile(chosen);
    setPreview(null);
    setStatus(null);
    try {
      const body = new FormData();
      body.append('file', chosen);
      const result = await request<Preview>(businessPath('/statements/preview'), { method: 'POST', body });
      setPreview(result);
      setMapping(result.mapping);
      if (!result.confident) setStatus({ message: 'Please choose which column is which below.', error: false });
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file || !preview || !mapping) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append('file', file);
      body.append('account', account);
      body.append('header_row', String(preview.header_row));
      body.append('mapping', JSON.stringify(mapping));
      const result = await request<{ new_lines: number; duplicates: number; checks: string[] }>(businessPath('/statements'), { method: 'POST', body });
      toast(`${result.new_lines} new line(s)${result.duplicates ? `, ${result.duplicates} already imported` : ''}.`);
      setStatus(result.checks.length ? { message: result.checks.join(' '), error: true } : null);
      setPreview(null);
      setFile(null);
      await onDone(account);
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" id="statement-import" onSubmit={(event) => void submit(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">Import a statement</h2>
          <p className="card-subtitle">CSV or Excel export from MTN, Telecel, AT or your bank. Lines already imported are skipped.</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <label className="field">
          Account
          <select className="select" value={account} onChange={(event) => setAccount(event.target.value)}>
            {Object.entries(choices).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Statement file
          <input className="input" type="file" accept=".csv,.xlsx,.txt" onChange={(event) => event.target.files?.[0] && void look(event.target.files[0])} />
        </label>
        {preview && mapping ? (
          <fieldset className="mapping-grid">
            <legend className="body-sm">Which column is which</legend>
            {(Object.keys(FIELD_LABEL) as Field[]).map((field) => (
              <label className="field" key={field}>
                {FIELD_LABEL[field]}
                <select
                  className="select"
                  value={mapping[field] ?? ''}
                  onChange={(event) => setMapping({ ...mapping, [field]: event.target.value === '' ? null : Number(event.target.value) })}
                >
                  <option value="">Not in this file</option>
                  {preview.columns.map((name, index) => (
                    <option key={index} value={index}>
                      {name || `Column ${index + 1}`}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </fieldset>
        ) : null}
        <Notice tone="info" icon="info">
          Importing never changes your books by itself: it shows which lines the books already have, and you choose what to add.
        </Notice>
        <div className="button-row">
          <button className="btn btn-primary" type="submit" disabled={busy || !preview}>
            Import
          </button>
          <StatusText message={status?.message} error={status?.error} />
        </div>
      </div>
    </form>
  );
}

function LineRow({ line, editable, openDebts, onDone }: { line: StatementLine; editable: boolean; openDebts: DebtBook['debts']; onDone: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const inflow = line.amount > 0;
  const [category, setCategory] = useState('');
  const [expense, setExpense] = useState('uncategorised');
  const [other, setOther] = useState('cash');
  const [debtId, setDebtId] = useState('');
  const tone = { matched: 'success', booked: 'info', suggested: 'warning', unmatched: 'error' } as const;
  const label = { matched: 'In the books', booked: 'Booked', suggested: 'Check the match', unmatched: 'Not in the books' };

  async function call(path: string, method: 'POST' | 'PUT' | 'DELETE', json?: unknown) {
    try {
      await request(businessPath(path), { method, json });
      await onDone();
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  const detail = category === 'expense' ? { expense } : category === 'transfer' ? { other_account: other } : category === 'debt_payment' ? { debt_id: debtId } : {};
  return (
    <li className="debt-card">
      <div className="debt-head">
        <div className="file-cell">
          <strong>{line.description || line.reference || 'Statement line'}</strong>
          <small>{`${formatDate(line.date)}${line.reference ? ` · ${line.reference}` : ''}${line.fee ? ` · fee ${money(line.fee)}${line.fee_booked ? ' (booked)' : ''}` : ''}`}</small>
        </div>
        <div className="debt-amount">
          <span className="num">{`${inflow ? '+' : '−'}${money(Math.abs(line.amount))}`}</span>
          <Pill tone={tone[line.status]}>{line.booking ? BOOKING_LABEL[line.booking] ?? label.booked : label[line.status]}</Pill>
        </div>
      </div>
      {line.matched_to ? <small className="muted">{`Matches: ${line.matched_to.label} (${formatDate(line.matched_to.date)})`}</small> : null}
      {editable && line.status === 'suggested' ? (
        <label className="field">
          This is the same as
          <select className="select" defaultValue="" onChange={(event) => event.target.value && void call(`/statements/lines/${line.id}/match`, 'PUT', { candidate_id: event.target.value })}>
            <option value="">Choose…</option>
            {line.suggestions.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {`${candidate.label} · ${formatDate(candidate.date)} · ${money(candidate.amount)}`}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {editable && (line.status === 'unmatched' || line.status === 'suggested') ? (
        <div className="form-grid debt-pay">
          <label className="field">
            Add to the books as
            <select className="select" value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">Choose…</option>
              {categoriesFor(inflow).map((key) => (
                <option key={key} value={key}>
                  {BOOKING_LABEL[key]}
                </option>
              ))}
            </select>
          </label>
          {category === 'expense' ? (
            <label className="field">
              Kind of spending
              <select className="select" value={expense} onChange={(event) => setExpense(event.target.value)}>
                {Object.entries(EXPENSE_KINDS).map(([key, text]) => (
                  <option key={key} value={key}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {category === 'transfer' ? (
            <label className="field">
              {inflow ? 'Came from' : 'Went to'}
              <select className="select" value={other} onChange={(event) => setOther(event.target.value)}>
                {Object.entries(OTHER_ACCOUNTS).map(([key, text]) => (
                  <option key={key} value={key}>
                    {text}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {category === 'debt_payment' ? (
            <label className="field">
              Debt
              <select className="select" value={debtId} onChange={(event) => setDebtId(event.target.value)}>
                <option value="">Choose…</option>
                {openDebts
                  .filter((debt) => debt.direction === (inflow ? 'owed_to_us' : 'we_owe'))
                  .map((debt) => (
                    <option key={debt.id} value={debt.id}>
                      {`${debt.party_name} · ${money(debt.balance)} owing`}
                    </option>
                  ))}
              </select>
            </label>
          ) : null}
          <div className="button-row">
            <button
              className="btn btn-secondary btn-sm"
              type="button"
              disabled={!category || (category === 'debt_payment' && !debtId)}
              onClick={() => void call(`/statements/lines/${line.id}/book`, 'POST', { category, detail })}
            >
              Add to books
            </button>
          </div>
        </div>
      ) : null}
      {editable && line.booking ? (
        <div className="button-row">
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => void call(`/statements/lines/${line.id}/book`, 'DELETE')}>
            Undo
          </button>
        </div>
      ) : null}
    </li>
  );
}

export default function Reconcile() {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const editable = can('manage_books');
  const overview = useQuery({ queryKey: keys.business(business.id, 'statements'), queryFn: ({ signal }) => request<Overview>(businessPath('/statements'), { signal }) });
  const [chosen, setChosen] = useState<string | null>(null);
  const account = chosen ?? overview.data?.accounts[0]?.account ?? null;
  const recon = useQuery({
    queryKey: keys.business(business.id, 'reconcile', account ?? ''),
    queryFn: ({ signal }) => request<Reconciliation>(businessPath(`/statements/${account}`), { signal }),
    enabled: Boolean(account),
  });
  const book = useQuery({ queryKey: keys.business(business.id, 'debts'), queryFn: ({ signal }) => request<DebtBook>(businessPath('/debts'), { signal }), enabled: editable });
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.business(business.id) });
  const summary = recon.data?.summary;
  const unbookedFees = (recon.data?.lines ?? []).filter((line) => line.fee > 0 && !line.fee_booked).length;

  return (
    <>
      {overview.data?.accounts.length ? (
        <PageActions>
          <Segmented
            id="reconcile-account"
            label="Account"
            mode="tabs"
            value={account ?? ''}
            onChange={setChosen}
            options={overview.data.accounts.map((item) => ({ value: item.account, label: item.label }))}
          />
        </PageActions>
      ) : null}

      {editable && overview.data ? (
        <ImportStatement
          choices={overview.data.choices}
          onDone={async (imported) => {
            setChosen(imported);
            await refresh();
          }}
        />
      ) : null}
      {!editable ? <ReadOnlyNotice role={business.role ?? 'manager'} what="reconciliation" /> : null}

      {account && recon.data ? (
        <>
          {summary ? (
            <div className="card" id="reconcile-summary">
              <div className="card-header">
                <div>
                  <h2 className="card-title">{`${recon.data.label}: statement and books`}</h2>
                  <p className="card-subtitle">{`${formatDate(summary.first)} to ${formatDate(summary.last)}`}</p>
                </div>
                {summary.unexplained === 0 ? <Pill tone="success" icon="check">Every cedi explained</Pill> : summary.unexplained != null ? <Pill tone="warning" icon="alert">{`${money(summary.unexplained)} unexplained`}</Pill> : null}
              </div>
              <dl className="books-totals card-body">
                <div>
                  <dt>Statement closing</dt>
                  <dd>{summary.statement_closing == null ? 'No balance column' : money(summary.statement_closing)}</dd>
                </div>
                <div>
                  <dt>Books on the same day</dt>
                  <dd>{money(summary.books_closing)}</dd>
                </div>
                <div>
                  <dt>Difference</dt>
                  <dd>{summary.difference == null ? '—' : money(summary.difference)}</dd>
                </div>
              </dl>
              {summary.explained.length ? (
                <div className="card-body">
                  <ul className="pending-invites">
                    {summary.explained.map((item) => (
                      <li key={item.reason}>
                        <span>{item.reason}</span>
                        <span className="num">{money(item.amount)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {editable && unbookedFees ? (
                <div className="button-row card-body">
                  <button className="btn btn-secondary btn-sm" type="button" onClick={() => void request(businessPath(`/statements/${account}/fees`), { method: 'POST' }).then(refresh)}>
                    {`Book ${unbookedFees} fee(s) as MoMo and bank charges`}
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="card" id="reconcile-lines">
            <div className="card-header">
              <div>
                <h2 className="card-title">Statement lines</h2>
                <p className="card-subtitle">{summary ? `${summary.unmatched_lines} not in the books yet` : recon.data.books_start ? 'Only lines from your books start are shown.' : ''}</p>
              </div>
            </div>
            {recon.data.lines.length ? (
              <ul className="debt-list">
                {recon.data.lines.map((line) => (
                  <LineRow key={line.id} line={line} editable={editable} openDebts={(book.data?.debts ?? []).filter((debt) => debt.status === 'open')} onDone={refresh} />
                ))}
              </ul>
            ) : (
              <EmptyState title="No statement lines for this account yet" />
            )}
          </div>

          {recon.data.only_in_books?.length ? (
            <div className="card" id="reconcile-books-only">
              <div className="card-header">
                <div>
                  <h2 className="card-title">In the books but not on the statement</h2>
                  <p className="card-subtitle">Check these: a wrong payment method on an import, or a payment the statement doesn't show.</p>
                </div>
              </div>
              <div className="card-body">
                <ul className="pending-invites">
                  {recon.data.only_in_books.map((item) => (
                    <li key={item.id}>
                      <span>{`${item.label} · ${formatDate(item.date)}`}</span>
                      <span className="num">{money(item.amount)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </>
      ) : account ? (
        <SkeletonRows count={4} />
      ) : null}
    </>
  );
}
