// Invoices, quotes and receipts: make one in a minute, share it on WhatsApp as a PDF, and let
// the debt book and the books keep track of what is paid.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money } from '../../lib/format';
import { Icon } from '../../lib/icons';
import { toast } from '../../lib/toast';
import type { InventoryResponse } from '../../lib/types';
import { EmptyState, Pill, ReadOnlyNotice, Segmented, SkeletonRows, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import type { DebtBook } from './debts.logic';
import { METHOD_LABEL } from './debts.logic';
import { draftTotal, emptyLine, KIND_LABEL, lineMinor, shareText, STATUS, type DocKind, type DocSummary, type DraftLine } from './invoices.logic';

interface InvoiceSettings {
  tin: string;
  address: string;
  phone: string;
  footer: string;
  pay_to: string;
}

const METHODS = ['cash', 'momo_mtn', 'momo_telecel', 'momo_at', 'bank'];

function NewDocument({ kind, onDone }: { kind: DocKind; onDone: (created: { id: string; number: string }) => Promise<void> }) {
  const { business, businessPath } = useWorkspace();
  const today = isoDate(new Date());
  const [customer, setCustomer] = useState('');
  const [phone, setPhone] = useState('');
  const [issued, setIssued] = useState(today);
  const [due, setDue] = useState('');
  const [paidBy, setPaidBy] = useState('cash');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([emptyLine()]);
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const stock = useQuery({ queryKey: keys.inventory(business.id), queryFn: ({ signal }) => request<InventoryResponse>(businessPath('/inventory'), { signal }) });
  const book = useQuery({ queryKey: keys.business(business.id, 'debts'), queryFn: ({ signal }) => request<DebtBook>(businessPath('/debts'), { signal }) });
  const products = (stock.data?.items ?? []).filter((item) => item.active);
  const customers = (book.data?.parties ?? []).filter((party) => party.kind === 'customer');
  const total = draftTotal(lines);

  const update = (index: number, patch: Partial<DraftLine>) => setLines((current) => current.map((line, i) => (i === index ? { ...line, ...patch } : line)));

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const created = await request<{ id: string; number: string }>(businessPath('/invoices'), {
        method: 'POST',
        json: {
          kind,
          customer_name: customer,
          phone,
          issued_on: issued,
          due_on: due || null,
          notes,
          paid_by: kind === 'receipt' ? paidBy : null,
          lines: lines
            .filter((line) => line.product_id || line.description.trim())
            .map((line) => ({ product_id: line.product_id || null, description: line.description, quantity: Number(line.quantity), unit_price: Number(line.unit_price || 0) })),
        },
      });
      setCustomer('');
      setPhone('');
      setNotes('');
      setDue('');
      setLines([emptyLine()]);
      setStatus(null);
      await onDone(created);
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" id="invoice-new" onSubmit={(event) => void submit(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">{`New ${KIND_LABEL[kind].toLowerCase()}`}</h2>
          <p className="card-subtitle">
            {kind === 'quote' ? 'A price offer. Nothing is recorded until you turn it into an invoice.' : kind === 'receipt' ? 'Paid now. It goes into your sales and your cash, MoMo or bank.' : 'Goes into the debt book until it is paid. Stock items leave stock.'}
          </p>
        </div>
      </div>
      <div className="card-body form-grid">
        <label className="field">
          Customer
          <input
            className="input"
            required
            maxLength={120}
            list="invoice-customers"
            value={customer}
            onChange={(event) => {
              setCustomer(event.target.value);
              const match = customers.find((party) => party.name.toLowerCase() === event.target.value.trim().toLowerCase());
              if (match?.phone) setPhone(match.phone);
            }}
          />
          <datalist id="invoice-customers">
            {customers.map((party) => (
              <option key={party.id} value={party.name} />
            ))}
          </datalist>
        </label>
        <label className="field">
          Phone (optional)
          <input className="input" type="tel" inputMode="tel" maxLength={30} value={phone} onChange={(event) => setPhone(event.target.value)} />
        </label>
        <label className="field">
          Date
          <input className="input" type="date" required max={today} value={issued} onChange={(event) => setIssued(event.target.value)} />
        </label>
        {kind === 'receipt' ? (
          <label className="field">
            Paid by
            <select className="select" value={paidBy} onChange={(event) => setPaidBy(event.target.value)}>
              {METHODS.map((key) => (
                <option key={key} value={key}>
                  {METHOD_LABEL[key]}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="field">
            {kind === 'quote' ? 'Valid until (optional)' : 'Pay by (optional)'}
            <input className="input" type="date" min={issued} value={due} onChange={(event) => setDue(event.target.value)} />
          </label>
        )}
        <ol className="invoice-lines">
          {lines.map((line, index) => (
            <li key={index} className="invoice-line">
              <label className="field">
                Item
                <select
                  className="select"
                  value={line.product_id}
                  onChange={(event) => update(index, { product_id: event.target.value, description: event.target.value ? '' : line.description })}
                >
                  <option value="">Not a stock item (type below)</option>
                  {products.map((item) => (
                    <option key={item.id} value={item.id}>
                      {`${item.name} (${item.quantity_on_hand} in stock)`}
                    </option>
                  ))}
                </select>
              </label>
              {!line.product_id ? (
                <label className="field">
                  Description
                  <input className="input" maxLength={200} placeholder="e.g. Delivery" value={line.description} onChange={(event) => update(index, { description: event.target.value })} />
                </label>
              ) : null}
              <label className="field">
                Qty
                <input className="input" required inputMode="decimal" value={line.quantity} onChange={(event) => update(index, { quantity: event.target.value })} />
              </label>
              <label className="field">
                Price each
                <input className="input" required inputMode="decimal" value={line.unit_price} onChange={(event) => update(index, { unit_price: event.target.value })} />
              </label>
              <div className="invoice-line-total">
                <span className="num">{money(lineMinor(line) / 100)}</span>
                {lines.length > 1 ? (
                  <button className="btn btn-ghost btn-sm" type="button" aria-label={`Remove line ${index + 1}`} onClick={() => setLines(lines.filter((_, i) => i !== index))}>
                    Remove
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
        <button className="btn btn-ghost btn-sm" type="button" onClick={() => setLines([...lines, emptyLine()])}>
          <Icon name="plus" />
          <span className="btn-label">Add line</span>
        </button>
        <label className="field">
          Note (optional)
          <input className="input" maxLength={500} placeholder="e.g. Delivery on Friday" value={notes} onChange={(event) => setNotes(event.target.value)} />
        </label>
        <div className="button-row">
          <strong className="invoice-total num">{`Total ${money(total)}`}</strong>
          <button className="btn btn-primary" type="submit" disabled={saving || total <= 0}>
            {`Create ${KIND_LABEL[kind].toLowerCase()}`}
          </button>
          <StatusText message={status?.message} error={status?.error} />
        </div>
      </div>
    </form>
  );
}

function DocCard({ doc, editable, settings, onDone }: { doc: DocSummary; editable: boolean; settings: InvoiceSettings | undefined; onDone: () => Promise<void> }) {
  const { business, businessPath } = useWorkspace();
  const [paying, setPaying] = useState(false);
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('cash');
  const [paidOn, setPaidOn] = useState(isoDate(new Date()));
  const [error, setError] = useState('');
  const [label, tone] = STATUS[doc.status];
  const total = money(doc.total, { code: doc.currency });

  async function share() {
    try {
      const blob = await request<Blob>(businessPath(`/invoices/${doc.id}/pdf`), { asBlob: true });
      const file = new File([blob], `${doc.number}.pdf`, { type: 'application/pdf' });
      const text = shareText(doc, business.name, total, settings?.pay_to ?? '');
      if (navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: `${KIND_LABEL[doc.kind]} ${doc.number}`, text });
        return;
      }
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = file.name;
      link.click();
      URL.revokeObjectURL(link.href);
      toast('PDF downloaded. Attach it in WhatsApp to send it.');
    } catch (failure) {
      if ((failure as Error).name !== 'AbortError') toast((failure as Error).message, { error: true });
    }
  }

  async function act(path: string, body?: unknown) {
    try {
      await request(businessPath(path), { method: 'POST', json: body });
      await onDone();
    } catch (failure) {
      toast((failure as Error).message, { error: true });
    }
  }

  async function pay(event: FormEvent) {
    event.preventDefault();
    try {
      await request(businessPath(`/debts/${doc.debt_id}/payments`), { method: 'POST', json: { amount: Number(amount), method, paid_on: paidOn } });
      setPaying(false);
      toast(`Payment recorded on ${doc.number}.`);
      await onDone();
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  return (
    <li className="debt-card">
      <div className="debt-head">
        <div className="file-cell">
          <strong>{`${doc.number} · ${doc.customer_name}`}</strong>
          <small>{`${formatDate(doc.issued_on)}${doc.due_on ? ` · ${doc.kind === 'quote' ? 'valid until' : 'pay by'} ${formatDate(doc.due_on)}` : ''}`}</small>
        </div>
        <div className="debt-amount">
          <span className="num">{total}</span>
          <Pill tone={tone}>{label}</Pill>
        </div>
      </div>
      {doc.kind === 'invoice' && doc.paid > 0 && !doc.voided ? <small className="muted">{`${money(doc.paid, { code: doc.currency })} paid · ${money(doc.balance, { code: doc.currency })} to go`}</small> : null}
      <div className="button-row">
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => void share()}>
          <Icon name="send" />
          <span className="btn-label">Share PDF</span>
        </button>
        {editable && doc.kind === 'invoice' && doc.balance > 0 ? (
          <button
            className="btn btn-ghost btn-sm"
            type="button"
            aria-expanded={paying}
            onClick={() => {
              setAmount(String(doc.balance));
              setError('');
              setPaying(!paying);
            }}
          >
            Record payment
          </button>
        ) : null}
        {editable && doc.status === 'quote' ? (
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => void act(`/invoices/${doc.id}/convert`, { issued_on: isoDate(new Date()), due_on: null })}>
            Make invoice
          </button>
        ) : null}
        {editable && !doc.voided ? (
          <button
            className="btn btn-ghost btn-sm"
            type="button"
            onClick={() => {
              if (window.confirm(`Void ${doc.number}? It keeps its number, payments are voided and stock comes back.`)) void act(`/invoices/${doc.id}/void`);
            }}
          >
            Void
          </button>
        ) : null}
      </div>
      {paying ? (
        <form className="form-grid debt-pay" onSubmit={(event) => void pay(event)}>
          <label className="field">
            Amount
            <input className="input" required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </label>
          <label className="field">
            Paid by
            <select className="select" value={method} onChange={(event) => setMethod(event.target.value)}>
              {METHODS.map((key) => (
                <option key={key} value={key}>
                  {METHOD_LABEL[key]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Date
            <input className="input" type="date" required min={doc.issued_on} value={paidOn} onChange={(event) => setPaidOn(event.target.value)} />
          </label>
          <div className="button-row">
            <button className="btn btn-primary btn-sm" type="submit">
              Save payment
            </button>
            <StatusText message={error} error />
          </div>
        </form>
      ) : null}
    </li>
  );
}

function Letterhead({ settings, onDone }: { settings: InvoiceSettings; onDone: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const [form, setForm] = useState({ tin: settings.tin, address: settings.address, phone: settings.phone, footer: settings.footer });
  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      await request(businessPath('/invoices/settings'), { method: 'PUT', json: form });
      toast('Saved. New PDFs use these details.');
      await onDone();
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }
  const field = (key: keyof typeof form, label: string, max: number, hint?: string) => (
    <label className="field">
      {label}
      <input className="input" maxLength={max} value={form[key]} onChange={(event) => setForm({ ...form, [key]: event.target.value })} />
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
  return (
    <form className="card" id="invoice-letterhead" onSubmit={(event) => void save(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">Your details on documents</h2>
          <p className="card-subtitle">{settings.pay_to ? `Pay-to line: ${settings.pay_to} (change it in the Debt book)` : 'Add your MoMo pay-to details in the Debt book so invoices show where to pay.'}</p>
        </div>
      </div>
      <div className="card-body form-grid">
        {field('address', 'Address', 300)}
        {field('phone', 'Phone', 60)}
        {field('tin', 'TIN (optional)', 40, 'Your Ghana Revenue Authority taxpayer number, if you have one.')}
        {field('footer', 'Footer note (optional)', 300)}
        <div className="button-row">
          <button className="btn btn-secondary" type="submit">
            Save details
          </button>
        </div>
      </div>
    </form>
  );
}

export default function Invoices() {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const editable = can('write_data');
  const [kind, setKind] = useState<DocKind>('invoice');
  const docs = useQuery({ queryKey: keys.business(business.id, 'invoices', kind), queryFn: ({ signal }) => request<DocSummary[]>(businessPath(`/invoices?kind=${kind}`), { signal }) });
  const settings = useQuery({ queryKey: keys.business(business.id, 'invoice-settings'), queryFn: ({ signal }) => request<InvoiceSettings>(businessPath('/invoices/settings'), { signal }) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.business(business.id) });

  return (
    <>
      <PageActions>
        <Segmented
          id="invoice-kind"
          label="Document type"
          mode="tabs"
          value={kind}
          onChange={setKind}
          options={[
            { value: 'invoice', label: 'Invoices' },
            { value: 'quote', label: 'Quotes' },
            { value: 'receipt', label: 'Receipts' },
          ]}
        />
      </PageActions>

      {editable ? (
        <NewDocument
          key={kind}
          kind={kind}
          onDone={async (created) => {
            toast(`${created.number} created. Use "Share PDF" to send it.`);
            await refresh();
          }}
        />
      ) : (
        <ReadOnlyNotice role={business.role ?? 'accountant'} what="invoices" />
      )}

      <div className="card" id="invoice-list">
        <div className="card-header">
          <div>
            <h2 className="card-title">{`${KIND_LABEL[kind]}s`}</h2>
            <p className="card-subtitle">Numbers never repeat or skip; a voided document keeps its number.</p>
          </div>
        </div>
        {docs.data ? (
          docs.data.length ? (
            <ul className="debt-list">
              {docs.data.map((doc) => (
                <DocCard key={doc.id} doc={doc} editable={editable} settings={settings.data} onDone={refresh} />
              ))}
            </ul>
          ) : (
            <EmptyState title={`No ${KIND_LABEL[kind].toLowerCase()}s yet`} />
          )
        ) : (
          <SkeletonRows count={3} />
        )}
      </div>

      {editable && settings.data ? <Letterhead key={JSON.stringify(settings.data)} settings={settings.data} onDone={refresh} /> : null}
    </>
  );
}
