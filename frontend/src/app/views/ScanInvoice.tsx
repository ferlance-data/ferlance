// Scan an invoice into stock: photo/PDF (read by AI) or a typed list (no AI) becomes a draft,
// the owner reviews every line, and only "Add to stock" writes purchases to the ledger.

import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { money, number } from '../../lib/format';
import { toast } from '../../lib/toast';
import type { InventoryItem } from '../../lib/types';
import { Notice, Pill, Segmented, StatusText } from '../components/ui';
import { useWorkspace } from '../workspace';

export interface CaptureLine {
  name: string;
  sku: string | null;
  quantity: number | null;
  unit: string | null;
  unit_cost: number | null;
  line_total: number | null;
  expiry: string | null;
  confidence: number;
  notes: string[];
  match: { product_id: string; name: string; kind: 'exact' | 'similar' } | null;
}

interface Capture {
  id: string;
  source: 'vision' | 'text';
  filename: string;
  lines: CaptureLine[];
}

export interface Decision {
  action: 'add' | 'create' | 'skip';
  product_id: string;
  name: string;
  quantity: string;
  unit_cost: string;
  reason: string;
}

/** Exact matches default to "add to that product"; a similar name is only a hint, never preselected. */
export function initialDecision(line: CaptureLine): Decision {
  const exact = line.match?.kind === 'exact' ? line.match.product_id : '';
  return {
    action: exact ? 'add' : line.match ? 'add' : 'create',
    product_id: exact,
    name: line.name,
    quantity: line.quantity === null ? '' : String(line.quantity),
    unit_cost: line.unit_cost === null ? '' : String(line.unit_cost),
    reason: '',
  };
}

/** Shrink a phone photo before upload: less mobile data, and re-encoding drops EXIF (including location). */
async function shrink(file: File): Promise<Blob> {
  if (file.type === 'application/pdf' || !('createImageBitmap' in window)) return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85));
    return blob ?? file;
  } catch {
    return file;
  }
}

export function ScanInvoice({ hidden, products, onApplied }: { hidden: boolean; products: InventoryItem[]; onApplied: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const [mode, setMode] = useState<'photo' | 'text'>('photo');
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [capture, setCapture] = useState<Capture | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const active = products.filter((item) => item.active);

  async function read(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setStatus({ message: mode === 'photo' ? 'Reading the invoice…' : 'Reading your list…', error: false });
    try {
      let result: Capture;
      if (mode === 'photo') {
        if (!file) throw new Error('Choose a photo or PDF first.');
        const body = new FormData();
        const blob = await shrink(file);
        body.append('file', blob, blob === file ? file.name : file.name.replace(/\.\w+$/, '') + '.jpg');
        result = await request<Capture>(businessPath('/inventory/captures'), { method: 'POST', body });
      } else {
        result = await request<Capture>(businessPath('/inventory/captures/text'), { method: 'POST', json: { text } });
      }
      setCapture(result);
      setDecisions(result.lines.map(initialDecision));
      setStatus({ message: `${number(result.lines.length)} line(s) found. Check each one, then add to stock.`, error: false });
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  const update = (index: number, patch: Partial<Decision>) =>
    setDecisions((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)));

  async function apply() {
    if (!capture) return;
    setBusy(true);
    try {
      const lines = decisions.map((item) =>
        item.action === 'skip'
          ? { action: 'skip', reason: item.reason || 'Not stock' }
          : {
              action: item.action,
              product_id: item.action === 'add' ? item.product_id || null : null,
              name: item.action === 'create' ? item.name : null,
              quantity: Number(item.quantity),
              unit_cost: item.unit_cost.trim() === '' ? null : Number(item.unit_cost),
            },
      );
      const result = await request<{ outcome: { action: string }[] }>(businessPath(`/inventory/captures/${capture.id}/confirm`), { method: 'POST', json: { lines } });
      const added = result.outcome.filter((item) => item.action === 'added').length;
      toast(`${number(added)} line(s) added to stock.`);
      setCapture(null);
      setFile(null);
      setText('');
      setStatus(null);
      await onApplied();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }

  async function discard() {
    if (capture) await request(businessPath(`/inventory/captures/${capture.id}`), { method: 'DELETE' }).catch(() => undefined);
    setCapture(null);
    setStatus(null);
  }

  if (hidden) return null;
  if (capture) {
    return (
      <div className="scan-review" id="scan-review">
        <p className="body-sm muted">{`From ${capture.filename}. Nothing is in stock until you press "Add to stock".`}</p>
        <ol className="scan-lines">
          {capture.lines.map((line, index) => {
            const decision = decisions[index];
            if (!decision) return null;
            const low = line.confidence < 0.6;
            return (
              <li className={`scan-line${low ? ' low' : ''}`} key={index}>
                <div className="scan-line-head">
                  <strong>{line.name}</strong>
                  {low ? <Pill tone="warning">Check this line</Pill> : null}
                  {line.line_total !== null ? <span className="muted body-sm">{`Line total ${money(line.line_total)}`}</span> : null}
                </div>
                {line.notes.map((note) => (
                  <p className="footnote" key={note}>
                    {note}
                  </p>
                ))}
                <div className="scan-line-fields">
                  <label className="field">
                    What to do
                    <select className="select" value={decision.action} onChange={(event) => update(index, { action: event.target.value as Decision['action'] })}>
                      <option value="add">Add to an existing product</option>
                      <option value="create">Create a new product</option>
                      <option value="skip">Skip this line</option>
                    </select>
                  </label>
                  {decision.action === 'add' ? (
                    <label className="field">
                      Product
                      <select className="select" value={decision.product_id} onChange={(event) => update(index, { product_id: event.target.value })}>
                        <option value="">Choose…</option>
                        {active.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.name}
                          </option>
                        ))}
                      </select>
                      {line.match?.kind === 'similar' && !decision.product_id ? <span className="field-hint">{`Did you mean ${line.match.name}?`}</span> : null}
                    </label>
                  ) : null}
                  {decision.action === 'create' ? (
                    <label className="field">
                      New product name
                      <input className="input" value={decision.name} maxLength={200} onChange={(event) => update(index, { name: event.target.value })} />
                    </label>
                  ) : null}
                  {decision.action === 'skip' ? (
                    <label className="field">
                      Why skip (optional)
                      <input className="input" value={decision.reason} maxLength={200} placeholder="e.g. delivery fee" onChange={(event) => update(index, { reason: event.target.value })} />
                    </label>
                  ) : (
                    <>
                      <label className="field">
                        Quantity
                        <input className="input" inputMode="decimal" value={decision.quantity} onChange={(event) => update(index, { quantity: event.target.value })} />
                      </label>
                      <label className="field">
                        Unit cost
                        <input className="input" inputMode="decimal" value={decision.unit_cost} placeholder="optional" onChange={(event) => update(index, { unit_cost: event.target.value })} />
                      </label>
                    </>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
        <div className="button-row">
          <button className="btn btn-primary" id="scan-apply" type="button" disabled={busy} onClick={() => void apply()}>
            Add to stock
          </button>
          <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => void discard()}>
            Discard
          </button>
          <StatusText id="scan-status" message={status?.message} error={status?.error} />
        </div>
      </div>
    );
  }

  return (
    <form className="form-grid" id="scan-form" onSubmit={(event) => void read(event)}>
      <Segmented
        id="scan-mode"
        label="How to add the invoice"
        value={mode}
        onChange={setMode}
        options={[
          { value: 'photo', label: 'Photo or PDF' },
          { value: 'text', label: 'Type the lines' },
        ]}
      />
      {mode === 'photo' ? (
        <>
          <label className="field">
            Invoice, delivery note or stock list
            <input className="input" id="scan-file" type="file" accept="image/jpeg,image/png,image/webp,application/pdf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <Notice tone="info" icon="info">
            The photo is made smaller on your phone (which also removes its location data) and sent to your AI provider to read. It is not stored. Nothing goes into stock until you check each line.
          </Notice>
        </>
      ) : (
        <label className="field">
          One product per line: name, quantity, unit cost
          <textarea className="textarea" id="scan-text" rows={6} placeholder={'Rice 5kg, 10, 70\nMilo 400g x 12 @ 47.50'} value={text} onChange={(event) => setText(event.target.value)} />
          <span className="field-hint">Read on our server without any AI. Free.</span>
        </label>
      )}
      <div className="button-row">
        <button className="btn btn-primary" id="scan-read" type="submit" disabled={busy || (mode === 'photo' ? !file : !text.trim())}>
          {mode === 'photo' ? 'Read invoice' : 'Read list'}
        </button>
        <StatusText id="scan-status" message={status?.message} error={status?.error} />
      </div>
    </form>
  );
}
