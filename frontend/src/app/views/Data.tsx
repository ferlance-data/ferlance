// Data imports: file uploads, Mobile Money SMS, and the import history with
// per-file inclusion switches.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type DragEvent, type FormEvent, type ReactNode } from 'react';
import { Link, useNavigate } from '../../lib/router';
import { request } from '../../lib/api';
import { formatDateTime, money, number, plural } from '../../lib/format';
import { Icon } from '../../lib/icons';
import { toast } from '../../lib/toast';
import type { Dataset } from '../../lib/types';
import { DataTable, Segmented, StatusText, type Column, ReadOnlyNotice } from '../components/ui';
import { pagePath } from '../routes';
import { keys, useScope, useWorkspace } from '../workspace';
import { StatusPill } from './shared';

interface MomoRecord {
  transaction_date: string;
  customer?: string | null;
  channel?: string | null;
  amount: number;
  currency?: string | null;
}
interface MomoResult {
  dataset: Dataset;
  records: MomoRecord[];
}
interface Result {
  dataset: Dataset;
  records?: MomoRecord[];
}
interface Status {
  message: string;
  error: boolean;
}

type Tab = 'file' | 'momo';

const MOMO_COLUMNS: Column<MomoRecord>[] = [
  { label: 'Date', value: (item) => item.transaction_date },
  { label: 'From', value: (item) => item.customer || '—' },
  { label: 'Network', value: (item) => item.channel || '—' },
  { label: 'Amount', num: true, value: (item) => money(item.amount, { code: item.currency || 'GHS' }) },
];

function ImportResult({ result }: { result: Result }) {
  const { setScope } = useScope();
  const navigate = useNavigate();
  const { dataset } = result;
  const failed = dataset.status === 'failed';
  const title = failed
    ? 'This file could not be imported'
    : dataset.status === 'partial'
      ? 'Imported with some rows rejected'
      : 'Every row imported';
  const counts: [string, number][] = [
    ['Rows found', dataset.source_rows],
    ['Accepted', dataset.accepted_rows],
    ['Rejected', dataset.rejected_rows],
  ];
  return (
    <div className="import-result">
      <div className="import-result-head">
        <strong>{title}</strong>
        <StatusPill dataset={dataset} />
      </div>
      <div className="import-counts">
        {counts.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{number(value)}</strong>
          </div>
        ))}
      </div>
      {result.records ? (
        <div className="table-wrap">
          <DataTable columns={MOMO_COLUMNS} rows={result.records.slice(0, 20)} rowKey={(_, index) => index} />
        </div>
      ) : null}
      {(dataset.errors || []).map((message, index) => (
        <div className="notice notice-error" key={index}>
          {message}
        </div>
      ))}
      {dataset.warnings?.length ? (
        <details className="import-warnings" open={dataset.warnings.length <= 5}>
          <summary>{`Notes and rejected rows (${dataset.warnings.length})`}</summary>
          <ul>
            {dataset.warnings.slice(0, 200).map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}
      {failed ? null : (
        <div className="button-row">
          <Link className="btn btn-primary btn-sm" to={pagePath('overview')}>
            See the overview
          </Link>
          <button
            className="btn btn-ghost btn-sm"
            type="button"
            onClick={() => {
              setScope({ datasetId: dataset.id });
              navigate(pagePath('overview'));
            }}
          >
            View only this file
          </button>
        </div>
      )}
    </div>
  );
}

export default function Data() {
  const { business, datasets, refreshDatasets, businessPath, can, role } = useWorkspace();
  const canWrite = can('write_data');
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('file');

  // The background folder importer can add files at any time: re-read the list on every visit.
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: keys.datasets(business.id) });
  }, [queryClient, business.id]);
  const [result, setResult] = useState<Result | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  function changeTab(next: Tab) {
    setTab(next);
    setResult(null);
  }

  return (
    <>
      <div className="grid-main">
        <div className="card">
          <div className="card-header">
            <Segmented
              id="import-tabs"
              mode="tabs"
              label="Import method"
              value={tab}
              onChange={changeTab}
              options={[
                { value: 'file', label: 'Upload a file' },
                { value: 'momo', label: 'Mobile Money SMS' },
              ]}
            />
          </div>
          <div className="card-body">
            {canWrite ? (
              <>
                <UploadForm hidden={tab !== 'file'} businessPath={businessPath} onResult={setResult} onImported={refreshDatasets} />
                <MomoForm hidden={tab !== 'momo'} businessPath={businessPath} onResult={setResult} onImported={refreshDatasets} />
              </>
            ) : (
              <ReadOnlyNotice role={role} what="imports" />
            )}
            <div id="import-result" ref={resultRef}>
              {result ? <ImportResult key={result.dataset.id} result={result} /> : null}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">What Ferlance reads</h2>
              <p className="card-subtitle">Headers are matched loosely — “Order Date” and order_date are the same</p>
            </div>
          </div>
          <div className="card-body">
            <dl className="contract">
              <div>
                <dt>
                  Date <span className="pill pill-warning">Required</span>
                </dt>
                <dd>date, transaction_date, sale_date, order_date, invoice_date</dd>
              </div>
              <div>
                <dt>
                  Money <span className="pill pill-warning">One required</span>
                </dt>
                <dd>amount, revenue, sales, total — or cost, expense, unit_cost</dd>
              </div>
              <div>
                <dt>Product</dt>
                <dd>product, item, item_name, service_name</dd>
              </div>
              <div>
                <dt>Customer</dt>
                <dd>customer, client, customer_name</dd>
              </div>
              <div>
                <dt>Quantity</dt>
                <dd>quantity, qty, units</dd>
              </div>
              <div>
                <dt>Transaction ID</dt>
                <dd>transaction_id, id, sale_id — enables duplicate detection</dd>
              </div>
            </dl>
            <p className="body-sm muted">Rejected rows are never dropped silently: every one is listed with its reason.</p>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Import history</h2>
            <p className="card-subtitle">Switch a file off to leave it out of business-wide numbers without deleting it</p>
          </div>
        </div>
        <div className="table-wrap" id="imports-table">
          <History
            datasets={datasets}
            businessPath={businessPath}
            canWrite={canWrite}
            onImported={refreshDatasets}
            onShowNotes={(dataset) => {
              setResult({ dataset });
              requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
            }}
          />
        </div>
      </div>
    </>
  );
}

interface FormProps {
  hidden: boolean;
  businessPath: (suffix?: string) => string;
  onResult: (result: Result) => void;
  onImported: () => Promise<void>;
}

function UploadForm({ hidden, businessPath, onResult, onImported }: FormProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  function drag(event: DragEvent) {
    event.preventDefault();
    setDragging(true);
  }
  function drop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const [dropped] = event.dataTransfer.files;
    if (!dropped || !inputRef.current) return;
    const transfer = new DataTransfer();
    transfer.items.add(dropped);
    inputRef.current.files = transfer.files;
    setFile(dropped);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const chosen = inputRef.current?.files?.[0];
    if (!chosen) return;
    setBusy(true);
    setStatus({ message: 'Checking every row…', error: false });
    try {
      const body = new FormData();
      body.append('file', chosen);
      const dataset = await request<Dataset>(businessPath('/datasets'), { method: 'POST', body });
      setStatus(null);
      onResult({ dataset });
      form.reset();
      setFile(null);
      setBusy(false);
      await onImported();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
      setBusy(false);
    }
  }

  return (
    <form id="upload-form" data-panel="file" hidden={hidden} onSubmit={(event) => void submit(event)}>
      <label
        className={`dropzone${dragging ? ' dragging' : ''}`}
        id="dropzone"
        onDragEnter={drag}
        onDragOver={drag}
        onDragLeave={() => setDragging(false)}
        onDrop={drop}
      >
        <input
          id="upload-file"
          type="file"
          accept=".csv,.xlsx,.tsv,.txt,.md"
          ref={inputRef}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
        <span className="dropzone-icon" data-icon="upload">
          <Icon name="upload" />
        </span>
        <strong>Drop a file here, or browse</strong>
        <span className="muted">CSV, Excel, TSV, text or Markdown table · up to 10 MB</span>
        <span className="dropzone-file" id="upload-filename">
          {file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : ''}
        </span>
      </label>
      <div className="button-row">
        <button className="btn btn-primary" id="upload-submit" type="submit" disabled={!file || busy}>
          Import and check
        </button>
        <StatusText id="upload-status" message={status?.message} error={status?.error} />
      </div>
    </form>
  );
}

function MomoForm({ hidden, businessPath, onResult, onImported }: FormProps) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus({ message: 'Reading messages…', error: false });
    try {
      const response = await request<MomoResult>(businessPath('/sources/momo'), { method: 'POST', json: { sms_text: text } });
      setStatus(null);
      setText('');
      onResult({ dataset: response.dataset, records: response.records });
      await onImported();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="form-grid" id="momo-form" data-panel="momo" hidden={hidden} onSubmit={(event) => void submit(event)}>
      <label className="field">
        Paste MoMo SMS alerts <span className="field-hint">MTN MoMo, Telecel Cash or AirtelTigo Money — one or many messages</span>
        <textarea
          className="textarea"
          id="momo-text"
          rows={6}
          required
          placeholder="Payment received for GHS 150.00 from Kweku Mensah. Current Balance: GHS 1,450.00. Financial Transaction Id: 18274910291."
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <div className="button-row">
        <button className="btn btn-primary" id="momo-submit" type="submit" disabled={busy}>
          Import transactions
        </button>
        <StatusText id="momo-status" message={status?.message} error={status?.error} />
      </div>
    </form>
  );
}

function History({
  datasets,
  businessPath,
  canWrite,
  onImported,
  onShowNotes,
}: {
  datasets: Dataset[];
  businessPath: (suffix?: string) => string;
  canWrite: boolean;
  onImported: () => Promise<void>;
  onShowNotes: (dataset: Dataset) => void;
}) {
  // Switch position shown while a PATCH is in flight, so the control responds at once.
  const [pending, setPending] = useState<Record<string, boolean>>({});

  async function toggle(dataset: Dataset, included: boolean) {
    setPending((current) => ({ ...current, [dataset.id]: included }));
    try {
      await request(businessPath(`/datasets/${dataset.id}`), { method: 'PATCH', json: { included } });
      await onImported();
      toast(included ? `${dataset.filename} is back in your numbers.` : `${dataset.filename} is now left out of business-wide numbers.`);
    } catch (error) {
      toast((error as Error).message, { error: true });
    } finally {
      setPending((current) => {
        const { [dataset.id]: _done, ...rest } = current;
        return rest;
      });
    }
  }

  const columns: Column<Dataset>[] = [
    {
      label: 'File',
      value: (item) => (
        <div className="file-cell">
          <strong>{item.filename}</strong>
          <small>{`${item.extension.replace('.', '').toUpperCase()} · ${formatDateTime(item.created_at)}`}</small>
        </div>
      ),
    },
    { label: 'Status', value: (item) => <StatusPill dataset={item} /> },
    { label: 'Rows', num: true, value: (item) => number(item.source_rows) },
    { label: 'Accepted', num: true, value: (item) => number(item.accepted_rows) },
    {
      label: 'Notes',
      value: (item): ReactNode =>
        item.warnings.length || item.errors.length ? (
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => onShowNotes(item)}>
            {plural(item.warnings.length + item.errors.length, 'note')}
          </button>
        ) : (
          '—'
        ),
    },
    {
      label: 'In analysis',
      value: (item) => {
        if (item.status === 'failed') return <span className="muted body-sm">Not usable</span>;
        const included = pending[item.id] ?? item.included;
        return (
          <label className="switch" title={included ? 'Included in business-wide numbers' : 'Left out of business-wide numbers'}>
            <input
              type="checkbox"
              checked={included}
              aria-label={`Include ${item.filename} in analysis`}
              disabled={!canWrite}
              onChange={(event) => void toggle(item, event.target.checked)}
            />
            <span />
          </label>
        );
      },
    },
  ];

  return (
    <DataTable
      columns={columns}
      rows={datasets}
      rowKey={(item) => item.id}
      empty="No imports yet. Upload a spreadsheet or paste Mobile Money alerts to begin."
    />
  );
}
