// The books: profit and loss, balance sheet and cash flow from the double-entry ledger, in plain
// words for owners. Debits and credits appear only on the "For your accountant" tab.

import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money } from '../../lib/format';
import { Icon } from '../../lib/icons';
import { toast } from '../../lib/toast';
import { DataTable, Kpi, Notice, Pill, ReadOnlyNotice, Segmented, SkeletonRows, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import { cashOnHand, salesToPlace, type BalanceBlock, type BooksSummary, type LedgerLine } from './books.logic';

interface Account {
  id: string;
  code: string;
  name: string;
  type: 'asset' | 'liability' | 'equity' | 'income' | 'expense';
  system_key: string | null;
}
interface JournalEntry {
  id: string;
  entry_date: string;
  memo: string;
  kind: string;
  user_email: string | null;
  lines: { code: string; name: string; currency: string; debit: number; credit: number; description: string }[];
}
interface OpeningProposal {
  start_date: string;
  lines: { account: string; account_name: string; category: string; amount: number; as_of_date: string }[];
  notes: string[];
}

const FLOW_LABELS: Record<string, string> = {
  sales: 'From sales',
  expenses: 'Paid for expenses',
  stock: 'Paid for stock',
  owner: 'Owner put in or took out',
  loans: 'Loans',
  opening: 'Opening balances',
  other: 'Other',
};

function Lines({ items, empty }: { items: LedgerLine[]; empty: string }) {
  return (
    <DataTable
      columns={[
        { label: 'Account', value: (item) => item.name },
        { label: 'Amount', num: true, value: (item) => money(item.amount) },
      ]}
      rows={items}
      rowKey={(item) => `${item.code}:${item.name}`}
      empty={empty}
    />
  );
}

function Statements({ data }: { data: BooksSummary }) {
  const pnl = data.profit_and_loss.currencies;
  const sheets = data.balance_sheet.currencies;
  const flows = data.cash_flow.currencies;
  const diff = data.differences;
  return (
    <>
      {pnl.length ? (
        pnl.map((block) => (
          <div className="card" id="books-pnl" key={block.currency}>
            <div className="card-header">
              <div>
                <h2 className="card-title">Profit and loss</h2>
                <p className="card-subtitle">{`${formatDate(data.profit_and_loss.from)} to ${formatDate(data.profit_and_loss.to)} · ${block.currency}`}</p>
              </div>
              <span className="num">{money(block.net_profit, { code: block.currency })}</span>
            </div>
            <div className="table-wrap">
              <Lines items={block.income} empty="No sales in this period." />
            </div>
            <div className="table-wrap">
              <Lines items={block.expenses} empty="No costs in this period." />
            </div>
            <dl className="books-totals card-body">
              <div>
                <dt>Gross profit</dt>
                <dd>{money(block.gross_profit, { code: block.currency })}</dd>
              </div>
              <div>
                <dt>Net profit</dt>
                <dd>{money(block.net_profit, { code: block.currency })}</dd>
              </div>
            </dl>
          </div>
        ))
      ) : (
        <div className="card card-body">
          <p className="body-sm muted">No sales or costs in this period.</p>
        </div>
      )}

      {sheets.map((block: BalanceBlock) => (
        <div className="card" id="books-balance-sheet" key={block.currency}>
          <div className="card-header">
            <div>
              <h2 className="card-title">What the business owns and owes</h2>
              <p className="card-subtitle">{`On ${formatDate(data.balance_sheet.as_of)} · ${block.currency}`}</p>
            </div>
            {block.balanced ? <Pill tone="success" icon="check">Balances</Pill> : <Pill tone="error" icon="alert">Does not balance</Pill>}
          </div>
          <h3 className="books-group">{`Owns · ${money(block.totals.assets, { code: block.currency })}`}</h3>
          <div className="table-wrap">
            <Lines items={block.assets} empty="Nothing recorded." />
          </div>
          <h3 className="books-group">{`Owes · ${money(block.totals.liabilities, { code: block.currency })}`}</h3>
          <div className="table-wrap">
            <Lines items={block.liabilities} empty="Nothing owed." />
          </div>
          <h3 className="books-group">{`Owner's share · ${money(block.totals.equity, { code: block.currency })}`}</h3>
          <div className="table-wrap">
            <Lines items={block.equity} empty="Nothing recorded." />
          </div>
          {block.to_allocate.length ? (
            <p className="footnote card-body">
              “To allocate” holds sales and payments whose cash, MoMo or bank account is not known yet. Add a payment method column to your files to place them.
            </p>
          ) : null}
        </div>
      ))}

      {flows.map((block) => (
        <div className="card" id="books-cash-flow" key={block.currency}>
          <div className="card-header">
            <div>
              <h2 className="card-title">Money in and out</h2>
              <p className="card-subtitle">Cash, MoMo wallets and bank</p>
            </div>
            <span className="num">{money(block.net, { code: block.currency })}</span>
          </div>
          <div className="table-wrap">
            <DataTable
              columns={[
                { label: 'Where it went', value: (item) => FLOW_LABELS[item[0]] ?? item[0] },
                { label: 'Amount', num: true, value: (item) => money(item[1], { code: block.currency }) },
              ]}
              rows={Object.entries(block.lines).filter(([, value]) => value !== 0)}
              rowKey={(item) => item[0]}
              empty="No money moved in this period."
            />
          </div>
          <p className="footnote card-body">{data.cash_flow.note}</p>
        </div>
      ))}

      <div className="card" id="books-differences">
        <div className="card-header">
          <div>
            <h2 className="card-title">Books and dashboards compared</h2>
            <p className="card-subtitle">Sales in the books against revenue on the dashboards, for the same dates</p>
          </div>
          {diff.unexplained === 0 ? <Pill tone="success" icon="check">Every difference explained</Pill> : <Pill tone="warning" icon="alert">{`${money(diff.unexplained)} unexplained`}</Pill>}
        </div>
        <dl className="books-totals card-body">
          <div>
            <dt>Dashboards</dt>
            <dd>{money(diff.analytics_revenue)}</dd>
          </div>
          <div>
            <dt>Books</dt>
            <dd>{money(diff.ledger_sales)}</dd>
          </div>
        </dl>
        {diff.explained.length ? (
          <ul className="pending-invites card-body">
            {diff.explained.map((item) => (
              <li key={item.reason}>
                <span>{item.reason}</span>
                <span className="num">{money(item.amount)}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </>
  );
}

function OpeningStep({ onDone }: { onDone: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const firstOfMonth = isoDate(new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [start, setStart] = useState(firstOfMonth);
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const proposal = useQuery({
    queryKey: ['books-opening', businessPath(''), start],
    queryFn: ({ signal }) => request<OpeningProposal>(businessPath(`/books/opening?start=${encodeURIComponent(start)}`), { signal }),
    enabled: Boolean(start),
  });
  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!proposal.data) return;
    setSaving(true);
    try {
      const lines = proposal.data.lines.map((line, index) => ({ ...line, amount: Number(amounts[index] ?? line.amount) }));
      await request(businessPath('/books/opening'), { method: 'POST', json: { start_date: start, lines } });
      toast(`Your books start on ${formatDate(start)}.`);
      await onDone();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" id="books-opening" onSubmit={(event) => void confirm(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">Where you stand on day one</h2>
          <p className="card-subtitle">Choose the day your books start and check what you had then. Sales before that day stay on the dashboards only, so nothing is counted twice.</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <label className="field">
          Books start on
          <input
            className="input"
            type="date"
            required
            value={start}
            onChange={(event) => {
              setStart(event.target.value);
              setAmounts({});
            }}
          />
        </label>
        {proposal.data ? (
          proposal.data.lines.length ? (
            proposal.data.lines.map((line, index) => (
              <label className="field" key={`${line.account}:${line.account_name}`}>
                {line.account_name}
                <input className="input" inputMode="decimal" value={amounts[index] ?? String(line.amount)} onChange={(event) => setAmounts({ ...amounts, [index]: event.target.value })} />
                <span className="field-hint">{`From your balance on ${formatDate(line.as_of_date)}`}</span>
              </label>
            ))
          ) : (
            <p className="body-sm muted">No balances recorded on or before this day. You can still start: your books will begin from zero, and you can add balances on Financial position first.</p>
          )
        ) : (
          <SkeletonRows count={2} />
        )}
        {proposal.data?.notes.map((note) => (
          <p className="footnote" key={note}>
            {note}
          </p>
        ))}
        <div className="button-row">
          <button className="btn btn-primary" type="submit" disabled={saving || !proposal.data}>
            Start my books
          </button>
          <StatusText message={status?.message} error={status?.error} />
        </div>
      </div>
    </form>
  );
}

function Accountant({ accounts, lockDate, onChanged }: { accounts: Account[]; lockDate: string | null; onChanged: () => Promise<void> }) {
  const { business, businessPath, can } = useWorkspace();
  const editable = can('manage_books');
  const [offset, setOffset] = useState(0);
  const journal = useQuery({
    queryKey: keys.business(business.id, 'books-journal', offset),
    queryFn: ({ signal }) => request<JournalEntry[]>(businessPath(`/books/journal?limit=25&offset=${offset}`), { signal }),
    placeholderData: keepPreviousData,
  });
  const today = isoDate(new Date());
  const [entryDate, setEntryDate] = useState(today);
  const [memo, setMemo] = useState('');
  const [lines, setLines] = useState([
    { account_id: '', debit: '', credit: '' },
    { account_id: '', debit: '', credit: '' },
  ]);
  const [lock, setLock] = useState(lockDate ?? '');
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [type, setType] = useState<Account['type']>('expense');

  async function act(work: () => Promise<unknown>, done: string) {
    try {
      await work();
      setStatus({ message: done, error: false });
      await onChanged();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  async function download() {
    try {
      const csv = await request<string>(businessPath('/books/journal.csv'), { asText: true });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
      link.download = 'ferlance-journal.csv';
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  const accountOptions = accounts.map((account) => (
    <option key={account.id} value={account.id}>
      {`${account.code} ${account.name}`}
    </option>
  ));

  return (
    <>
      <div className="card" id="books-journal">
        <div className="card-header">
          <div>
            <h2 className="card-title">Journal</h2>
            <p className="card-subtitle">{lockDate ? `Locked up to ${formatDate(lockDate)}` : 'No period is locked'}</p>
          </div>
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => void download()}>
            <Icon name="download" />
            <span className="btn-label">Download CSV</span>
          </button>
        </div>
        {journal.data ? (
          journal.data.length ? (
            <ol className="journal-list">
              {journal.data.map((entry) => (
                <li key={entry.id}>
                  <div className="journal-head">
                    <strong>{entry.memo}</strong>
                    <small className="muted">{`${formatDate(entry.entry_date)} · ${entry.kind}${entry.user_email ? ` · ${entry.user_email}` : ''}`}</small>
                  </div>
                  <table className="journal-lines">
                    <thead>
                      <tr>
                        <th scope="col">Account</th>
                        <th scope="col" className="num">Debit</th>
                        <th scope="col" className="num">Credit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entry.lines.map((line, index) => (
                        <tr key={index}>
                          <td>{`${line.code} ${line.name}`}</td>
                          <td className="num">{line.debit ? money(line.debit, { code: line.currency }) : ''}</td>
                          <td className="num">{line.credit ? money(line.credit, { code: line.currency }) : ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </li>
              ))}
            </ol>
          ) : (
            <p className="body-sm muted card-body">Nothing in the journal yet.</p>
          )
        ) : (
          <SkeletonRows count={4} />
        )}
        <div className="button-row card-body">
          <button className="btn btn-ghost btn-sm" type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>
            Newer
          </button>
          <button className="btn btn-ghost btn-sm" type="button" disabled={(journal.data?.length ?? 0) < 25} onClick={() => setOffset(offset + 25)}>
            Older
          </button>
        </div>
      </div>

      {editable ? (
        <>
          <form
            className="card"
            id="books-manual"
            onSubmit={(event) => {
              event.preventDefault();
              void act(
                () =>
                  request(businessPath('/books/journal'), {
                    method: 'POST',
                    json: { entry_date: entryDate, memo, lines: lines.map((line) => ({ account_id: line.account_id, debit: Number(line.debit || 0), credit: Number(line.credit || 0) })) },
                  }),
                'Journal entry posted.',
              ).then(() => {
                setMemo('');
                setLines([
                  { account_id: '', debit: '', credit: '' },
                  { account_id: '', debit: '', credit: '' },
                ]);
              });
            }}
          >
            <div className="card-header">
              <div>
                <h2 className="card-title">Manual journal</h2>
                <p className="card-subtitle">Debits must equal credits. Posted entries cannot be edited; correct them with another entry.</p>
              </div>
            </div>
            <div className="card-body form-grid">
              <label className="field">
                Date
                <input className="input" type="date" required value={entryDate} onChange={(event) => setEntryDate(event.target.value)} />
              </label>
              <label className="field">
                Description
                <input className="input" required maxLength={300} value={memo} onChange={(event) => setMemo(event.target.value)} />
              </label>
              {lines.map((line, index) => (
                <fieldset className="journal-entry-line" key={index}>
                  <legend className="visually-hidden">{`Line ${index + 1}`}</legend>
                  <label className="field">
                    Account
                    <select className="select" required value={line.account_id} onChange={(event) => setLines(lines.map((l, i) => (i === index ? { ...l, account_id: event.target.value } : l)))}>
                      <option value="">Choose…</option>
                      {accountOptions}
                    </select>
                  </label>
                  <label className="field">
                    Debit
                    <input className="input" inputMode="decimal" value={line.debit} onChange={(event) => setLines(lines.map((l, i) => (i === index ? { ...l, debit: event.target.value, credit: '' } : l)))} />
                  </label>
                  <label className="field">
                    Credit
                    <input className="input" inputMode="decimal" value={line.credit} onChange={(event) => setLines(lines.map((l, i) => (i === index ? { ...l, credit: event.target.value, debit: '' } : l)))} />
                  </label>
                </fieldset>
              ))}
              <div className="button-row">
                <button className="btn btn-ghost btn-sm" type="button" onClick={() => setLines([...lines, { account_id: '', debit: '', credit: '' }])}>
                  Add line
                </button>
                <button className="btn btn-primary" type="submit">
                  Post entry
                </button>
              </div>
            </div>
          </form>

          <form
            className="card"
            id="books-lock"
            onSubmit={(event) => {
              event.preventDefault();
              void act(() => request(businessPath('/books/lock'), { method: 'PUT', json: { lock_date: lock || null } }), lock ? `Locked up to ${formatDate(lock)}.` : 'Period unlocked.');
            }}
          >
            <div className="card-header">
              <div>
                <h2 className="card-title">Lock a period</h2>
                <p className="card-subtitle">Nothing can be posted on or before the lock date. Late changes land on the first open day.</p>
              </div>
            </div>
            <div className="card-body form-grid">
              <label className="field">
                Locked up to
                <input className="input" type="date" max={today} value={lock} onChange={(event) => setLock(event.target.value)} />
              </label>
              <div className="button-row">
                <button className="btn btn-secondary" type="submit">
                  Save lock
                </button>
              </div>
            </div>
          </form>

          <form
            className="card"
            id="books-accounts"
            onSubmit={(event) => {
              event.preventDefault();
              void act(() => request(businessPath('/books/accounts'), { method: 'POST', json: { code, name, type } }), `Added ${code} ${name}.`).then(() => {
                setCode('');
                setName('');
              });
            }}
          >
            <div className="card-header">
              <div>
                <h2 className="card-title">Chart of accounts</h2>
                <p className="card-subtitle">{`${accounts.length} accounts`}</p>
              </div>
            </div>
            <div className="table-wrap">
              <DataTable
                columns={[
                  { label: 'Code', value: (item) => item.code },
                  { label: 'Account', value: (item) => item.name },
                  { label: 'Type', value: (item) => item.type },
                ]}
                rows={accounts}
                rowKey={(item) => item.id}
              />
            </div>
            <div className="card-body form-grid">
              <label className="field">
                Code
                <input className="input" required maxLength={12} pattern="[0-9A-Za-z-]+" value={code} onChange={(event) => setCode(event.target.value)} />
              </label>
              <label className="field">
                Name
                <input className="input" required maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <label className="field">
                Type
                <select className="select" value={type} onChange={(event) => setType(event.target.value as Account['type'])}>
                  <option value="asset">Asset</option>
                  <option value="liability">Liability</option>
                  <option value="equity">Equity</option>
                  <option value="income">Income</option>
                  <option value="expense">Expense</option>
                </select>
              </label>
              <div className="button-row">
                <button className="btn btn-secondary" type="submit">
                  Add account
                </button>
              </div>
            </div>
          </form>
        </>
      ) : (
        <ReadOnlyNotice role={business.role ?? 'manager'} what="the journal" />
      )}
      <StatusText id="books-status" message={status?.message} error={status?.error} />
    </>
  );
}

export default function Books() {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const today = new Date();
  const [from, setFrom] = useState(isoDate(new Date(today.getFullYear(), 0, 1)));
  const [to, setTo] = useState(isoDate(today));
  const [tab, setTab] = useState<'statements' | 'accountant'>('statements');
  const summary = useQuery({
    queryKey: keys.business(business.id, 'books', from, to),
    queryFn: ({ signal }) => request<BooksSummary>(businessPath(`/books?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`), { signal }),
    enabled: Boolean(from && to),
    placeholderData: keepPreviousData,
  });
  const accounts = useQuery({
    queryKey: keys.business(business.id, 'books-accounts'),
    queryFn: ({ signal }) => request<Account[]>(businessPath('/books/accounts'), { signal }),
    enabled: tab === 'accountant',
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.business(business.id) });
  const data = summary.data;
  const sheet = data?.balance_sheet.currencies[0];
  const pnl = data?.profit_and_loss.currencies[0];

  return (
    <>
      <PageActions>
        <Segmented
          id="books-tabs"
          label="Books view"
          mode="tabs"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'statements', label: 'Statements' },
            { value: 'accountant', label: 'For your accountant' },
          ]}
        />
      </PageActions>

      <div className="toolbar toolbar-plain">
        <label className="field field-inline">
          From
          <input className="input" id="books-from" type="date" required value={from} max={to} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="field field-inline">
          To
          <input className="input" id="books-to" type="date" required value={to} min={from} onChange={(event) => setTo(event.target.value)} />
        </label>
      </div>

      {data && !data.settings.books_start && can('manage_books') ? <OpeningStep onDone={refresh} /> : null}

      <div className="kpi-grid" id="books-kpis">
        {data ? (
          <>
            <Kpi label="Sales" icon="coins" value={money(pnl?.total_income ?? 0)} />
            <Kpi label="Profit" icon="scale" value={money(pnl?.net_profit ?? 0)} />
            <Kpi label="Cash, MoMo and bank" icon="receipt" value={money(sheet ? cashOnHand(sheet) : 0)} foot={sheet ? `On ${formatDate(data.balance_sheet.as_of)}` : null} />
            <Kpi label="Sales not yet placed" icon="alert" value={money(sheet ? salesToPlace(sheet) : 0)} foot="Cash, MoMo or bank not known" />
          </>
        ) : (
          <SkeletonRows count={2} />
        )}
      </div>

      {data?.issues.length ? (
        <Notice tone="info" icon="info">
          <strong>Not fully in the books</strong>
          <ul className="books-issues">
            {data.issues.slice(0, 8).map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </Notice>
      ) : null}

      {data ? tab === 'statements' ? <Statements data={data} /> : accounts.data ? <Accountant accounts={accounts.data} lockDate={data.settings.lock_date} onChanged={refresh} /> : <SkeletonRows count={4} /> : <SkeletonRows count={6} />}
    </>
  );
}
