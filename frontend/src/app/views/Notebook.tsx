// Notebook pages: photograph (or type) a page of the exercise book: a day's sales, the debtors
// page, or what the shop spent. Every line is checked before anything is added.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money } from '../../lib/format';
import { toast } from '../../lib/toast';
import {
  EmptyState,
  ListHeader,
  Modal,
  Notice,
  PhotoInput,
  Pill,
  ReadOnlyNotice,
  Segmented,
  SkeletonRows,
  StatusText,
} from '../components/ui';
import { keys, useWorkspace } from '../workspace';
import { shrink } from './ScanInvoice';

type PageType = 'sales' | 'debts' | 'expenses';

interface PageLine {
  include: boolean;
  date: string | null;
  description: string;
  customer: string | null;
  quantity: number | null;
  amount: number | null;
  confidence: number;
  notes: string[];
}

interface Draft {
  id: string;
  type: PageType;
  date: string | null;
  source: 'vision' | 'text';
  lines: PageLine[];
}

const TYPE_LABEL: Record<PageType, string> = { sales: 'Sales', debts: 'Debts (customers owe)', expenses: 'Money spent' };
const EXAMPLES: Record<PageType, string> = {
  sales: 'Rice 5kg 2 190\nMilo 47.50\nSugar 1kg 3 36',
  debts: 'Akosua - 2 bags rice - 190\nKojo - sugar - 30',
  expenses: 'Shop rent 500\nTrotro to Makola 30\nECG prepaid 100',
};
const WHERE: Record<PageType, string> = {
  sales: 'Added as an import: it shows on the dashboards and in the books.',
  debts: 'Each line goes into the debt book as money the customer owes.',
  expenses: 'Added as spending: the books sort it into rent, transport, airtime and so on.',
};

function PageCapture({ onDone }: { onDone: () => Promise<void> }) {
  const { business, businessPath } = useWorkspace();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<'photo' | 'text'>('photo');
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [typedType, setTypedType] = useState<PageType>('sales');
  const [draft, setDraft] = useState<Draft | null>(null);
  const [pageType, setPageType] = useState<PageType>('sales');
  const [pageDate, setPageDate] = useState(isoDate(new Date()));
  const [lines, setLines] = useState<PageLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);

  async function read(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus({ message: mode === 'photo' ? 'Reading the page…' : 'Reading your lines…', error: false });
    try {
      let result: Draft;
      if (mode === 'photo') {
        if (!file) throw new Error('Choose a photo first.');
        const body = new FormData();
        const blob = await shrink(file);
        body.append('file', blob, blob === file ? file.name : 'page.jpg');
        result = await request<Draft>(businessPath('/pages'), { method: 'POST', body });
      } else {
        result = await request<Draft>(businessPath('/pages/text'), { method: 'POST', json: { text, page_type: typedType } });
      }
      setDraft(result);
      setPageType(result.type);
      setPageDate(result.date ?? isoDate(new Date()));
      setLines(result.lines.map((line) => ({ ...line, include: line.amount !== null })));
      setStatus(null);
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  const update = (index: number, patch: Partial<PageLine>) =>
    setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));
  const total = lines.filter((line) => line.include).reduce((sum, line) => sum + (line.amount ?? 0), 0);

  async function confirm() {
    if (!draft) return;
    setBusy(true);
    try {
      const result = await request<{ total: number }>(businessPath(`/pages/${draft.id}/confirm`), {
        method: 'POST',
        json: {
          page_type: pageType,
          page_date: pageDate,
          lines: lines.map(({ include, date, description, customer, quantity, amount }) => ({
            include,
            date,
            description,
            customer,
            quantity,
            amount,
          })),
        },
      });
      toast(`Added ${money(result.total)} from the page.`);
      setDraft(null);
      setFile(null);
      setText('');
      await queryClient.invalidateQueries({ queryKey: keys.business(business.id) });
      await queryClient.invalidateQueries({ queryKey: keys.datasets(business.id) });
      await onDone();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    if (draft) await request(businessPath(`/pages/${draft.id}`), { method: 'DELETE' }).catch(() => undefined);
    setDraft(null);
    setStatus(null);
  }

  if (draft) {
    return (
      <div className="card" id="page-review">
        <div className="card-header">
          <div>
            <h2 className="card-title">Check the page</h2>
            <p className="card-subtitle">
              Untick anything that should not be added, and fix any number that was read wrongly. Nothing is added until you press Add.
            </p>
          </div>
        </div>
        <div className="card-body form-grid">
          <label className="field">
            This page is
            <select className="select" value={pageType} onChange={(event) => setPageType(event.target.value as PageType)}>
              {(Object.keys(TYPE_LABEL) as PageType[]).map((key) => (
                <option key={key} value={key}>
                  {TYPE_LABEL[key]}
                </option>
              ))}
            </select>
            <span className="field-hint">{WHERE[pageType]}</span>
          </label>
          <label className="field">
            Page date
            <input
              className="input"
              type="date"
              required
              max={isoDate(new Date())}
              value={pageDate}
              onChange={(event) => setPageDate(event.target.value)}
            />
          </label>
          <ol className="invoice-lines">
            {lines.map((line, index) => (
              <li key={index} className={`invoice-line page-line${line.include ? '' : ' muted'}`}>
                <label className="field field-inline page-include">
                  <input type="checkbox" checked={line.include} onChange={(event) => update(index, { include: event.target.checked })} />
                  Add
                </label>
                {pageType === 'debts' ? (
                  <label className="field">
                    Customer
                    <input
                      className="input"
                      maxLength={120}
                      value={line.customer ?? ''}
                      onChange={(event) => update(index, { customer: event.target.value })}
                    />
                  </label>
                ) : null}
                <label className="field">
                  {pageType === 'expenses' ? 'What for' : 'Item'}
                  <input
                    className="input"
                    maxLength={200}
                    value={line.description}
                    onChange={(event) => update(index, { description: event.target.value })}
                  />
                </label>
                {pageType === 'sales' ? (
                  <label className="field">
                    Qty
                    <input
                      className="input"
                      inputMode="decimal"
                      value={line.quantity ?? ''}
                      onChange={(event) => update(index, { quantity: event.target.value === '' ? null : Number(event.target.value) })}
                    />
                  </label>
                ) : null}
                <label className="field">
                  Amount
                  <input
                    className="input"
                    inputMode="decimal"
                    value={line.amount ?? ''}
                    onChange={(event) => update(index, { amount: event.target.value === '' ? null : Number(event.target.value) })}
                  />
                </label>
                {line.confidence < 0.6 ? <Pill tone="warning">Check this line</Pill> : null}
                {line.notes.map((note) => (
                  <small className="footnote" key={note}>
                    {note}
                  </small>
                ))}
              </li>
            ))}
          </ol>
          <div className="button-row">
            <strong className="invoice-total num">{`Total ${money(total)}`}</strong>
            <button className="btn btn-primary" type="button" disabled={busy} onClick={() => void confirm()}>
              Add
            </button>
            <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => void discard()}>
              Discard
            </button>
            <StatusText message={status?.message} error={status?.error} />
          </div>
        </div>
      </div>
    );
  }

  return (
    <form className="card" id="page-read" onSubmit={(event) => void read(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">Add a page from your book</h2>
          <p className="card-subtitle">A day's sales, the debtors page, or what you spent: take a photo, or type it in.</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <Segmented
          label="How to add the page"
          value={mode}
          onChange={setMode}
          options={[
            { value: 'photo', label: 'Photo' },
            { value: 'text', label: 'Type it' },
          ]}
        />
        {mode === 'photo' ? (
          <>
            <PhotoInput id="page-file" label="Photo of the page" file={file} onFile={setFile} />
            <Notice tone="info" icon="info">
              Lay the book flat in good light. The photo is made smaller on your phone (which also removes its location), sent to your AI
              provider to read, and not stored.
            </Notice>
          </>
        ) : (
          <>
            <label className="field">
              This page is
              <select className="select" value={typedType} onChange={(event) => setTypedType(event.target.value as PageType)}>
                {(Object.keys(TYPE_LABEL) as PageType[]).map((key) => (
                  <option key={key} value={key}>
                    {TYPE_LABEL[key]}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              One line per row: the amount last
              <textarea
                className="textarea"
                id="page-text"
                rows={6}
                placeholder={EXAMPLES[typedType]}
                value={text}
                onChange={(event) => setText(event.target.value)}
              />
              <span className="field-hint">
                {typedType === 'debts' ? 'Start each line with the customer, then a dash. ' : ''}Read on our server without any AI. Free.
              </span>
            </label>
          </>
        )}
        <div className="button-row">
          <button className="btn btn-primary" type="submit" disabled={busy || (mode === 'photo' ? !file : !text.trim())}>
            {mode === 'photo' ? 'Read the page' : 'Read the lines'}
          </button>
          <StatusText message={status?.message} error={status?.error} />
        </div>
      </div>
    </form>
  );
}

interface RecentPage {
  id: string;
  type: PageType;
  page_date: string | null;
  status: 'draft' | 'confirmed';
  source: 'vision' | 'text';
  created_at: string;
  outcome: { total?: number; lines?: number; debts?: number } | null;
}

export default function Notebook() {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const editable = can('write_data');
  const [open, setOpen] = useState(false);
  const recent = useQuery({
    queryKey: keys.business(business.id, 'pages'),
    queryFn: ({ signal }) => request<RecentPage[]>(businessPath('/pages'), { signal }),
  });
  return (
    <>
      <ListHeader
        title="Pages you have added"
        subtitle="Sales, debtors and spending pages from your exercise book"
        action={editable ? 'Add a page' : undefined}
        onAction={() => setOpen(true)}
      />
      {!editable ? <ReadOnlyNotice role={business.role ?? 'accountant'} what="notebook pages" /> : null}
      {open ? (
        <Modal label="Add a page from your book" onClose={() => setOpen(false)} wide>
          <PageCapture
            onDone={async () => {
              setOpen(false);
              await queryClient.invalidateQueries({ queryKey: keys.business(business.id, 'pages') });
            }}
          />
        </Modal>
      ) : null}
      <div className="card" id="page-list">
        {recent.data ? (
          recent.data.length ? (
            <ul className="debt-list">
              {recent.data.map((page) => (
                <li className="debt-card" key={page.id}>
                  <div className="debt-head">
                    <div className="file-cell">
                      <strong>{`${TYPE_LABEL[page.type]}${page.page_date ? ` · ${formatDate(page.page_date)}` : ''}`}</strong>
                      <small>{`${page.source === 'vision' ? 'From a photo' : 'Typed'} · added ${formatDate(page.created_at)}`}</small>
                    </div>
                    <div className="debt-amount">
                      {page.outcome?.total != null ? <span className="num">{money(page.outcome.total)}</span> : null}
                      <Pill tone={page.status === 'confirmed' ? 'success' : 'warning'}>
                        {page.status === 'confirmed' ? 'Added' : 'Not checked yet'}
                      </Pill>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="No pages yet" message="Photograph a page of your book, or type it in." />
          )
        ) : (
          <SkeletonRows count={3} />
        )}
      </div>
    </>
  );
}
