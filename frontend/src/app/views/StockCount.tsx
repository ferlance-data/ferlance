// Stocktake from a count sheet: photograph the sheet (read by AI) or type the counts (free),
// check each line against the products, then apply. Stock becomes exactly what was counted, and
// each difference is one auditable stocktake movement.

import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { number } from '../../lib/format';
import type { InventoryItem } from '../../lib/types';
import { Notice, PhotoInput, Segmented, StatusText } from '../components/ui';
import { useWorkspace } from '../workspace';
import { shrink } from './ScanInvoice';

interface CountLine {
  name: string;
  quantity: number | null;
  confidence: number;
  notes: string[];
  match: { product_id: string; name: string; kind: 'exact' | 'similar' } | null;
}

interface Row {
  line: CountLine;
  productId: string;
  counted: string;
  include: boolean;
}

export function StockCount({ products, onApplied }: { products: InventoryItem[]; onApplied: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const [mode, setMode] = useState<'photo' | 'text'>('photo');
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState('');
  const [rows, setRows] = useState<Row[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState({ message: '', error: false });
  const byId = new Map(products.map((product) => [product.id, product]));

  const read = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setStatus({ message: mode === 'photo' ? 'Reading the count sheet…' : 'Reading your counts…', error: false });
    try {
      let result: { lines: CountLine[] };
      if (mode === 'photo') {
        if (!file) throw new Error('Take or choose a photo of the count sheet first.');
        const body = new FormData();
        const blob = await shrink(file);
        body.append('file', blob, blob === file ? file.name : file.name.replace(/\.\w+$/, '') + '.jpg');
        result = await request(businessPath('/inventory/counts/read'), { method: 'POST', body });
      } else {
        result = await request(businessPath('/inventory/counts/text'), { method: 'POST', json: { text } });
      }
      setRows(
        result.lines.map((line) => ({
          line,
          productId: line.match?.product_id ?? '',
          counted: line.quantity === null ? '' : String(line.quantity),
          include: Boolean(line.match) && line.quantity !== null,
        })),
      );
      setStatus({ message: `${number(result.lines.length)} line(s) read. Check each product and count, then apply.`, error: false });
    } catch (error) {
      setStatus({ message: error instanceof Error ? error.message : 'Could not read the counts.', error: true });
    } finally {
      setBusy(false);
    }
  };

  const update = (index: number, change: Partial<Row>) =>
    setRows((current) => current && current.map((row, at) => (at === index ? { ...row, ...change } : row)));

  const chosen = (rows ?? []).filter((row) => row.include && row.productId && row.counted !== '' && Number(row.counted) >= 0);

  const apply = async () => {
    setBusy(true);
    try {
      const result = await request<{ counted: number; changed: number }>(businessPath('/inventory/counts'), {
        method: 'POST',
        json: { counts: chosen.map((row) => ({ product_id: row.productId, counted: Number(row.counted) })) },
      });
      setRows(null);
      setFile(null);
      setText('');
      setStatus({ message: `Counted ${number(result.counted)} product(s); ${number(result.changed)} changed.`, error: false });
      await onApplied();
    } catch (error) {
      setStatus({ message: error instanceof Error ? error.message : 'Could not apply the counts.', error: true });
    } finally {
      setBusy(false);
    }
  };

  if (rows) {
    return (
      <div className="form-grid" id="count-review">
        <p className="body-sm muted">Pick the product for each line and correct any count. Only ticked lines are applied.</p>
        <ul className="count-lines">
          {rows.map((row, index) => {
            const product = byId.get(row.productId);
            const difference = product && row.counted !== '' ? Number(row.counted) - product.quantity_on_hand : null;
            return (
              <li key={index}>
                <label className="checkbox">
                  <input type="checkbox" checked={row.include} onChange={(event) => update(index, { include: event.target.checked })} />
                  <span>
                    <strong>{row.line.name}</strong>
                    {row.line.confidence < 0.7 ? ' (hard to read: check it)' : ''}
                  </span>
                </label>
                <div className="form-row">
                  <label className="field">
                    Product
                    <select
                      className="select"
                      value={row.productId}
                      onChange={(event) => update(index, { productId: event.target.value, include: Boolean(event.target.value) })}
                    >
                      <option value="">Not in stock records (add it first)</option>
                      {products.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field">
                    Counted
                    <input
                      className="input"
                      type="number"
                      inputMode="decimal"
                      min="0"
                      step="any"
                      value={row.counted}
                      onChange={(event) => update(index, { counted: event.target.value })}
                    />
                  </label>
                </div>
                {product ? (
                  <span className="field-hint">
                    Records say {number(product.quantity_on_hand)} {product.unit}
                    {difference ? `: ${difference > 0 ? '+' : ''}${number(difference)} after counting` : ': no change'}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
        <div className="button-row">
          <button className="btn btn-primary" type="button" disabled={busy || !chosen.length} onClick={() => void apply()}>
            Apply {number(chosen.length)} count(s)
          </button>
          <button className="btn btn-ghost" type="button" onClick={() => setRows(null)}>
            Start again
          </button>
        </div>
        <StatusText message={status.message} error={status.error} />
      </div>
    );
  }

  return (
    <form className="form-grid" id="count-form" onSubmit={(event) => void read(event)}>
      <Segmented
        label="How to add the count"
        value={mode}
        onChange={setMode}
        options={[
          { value: 'photo', label: 'Photo of count sheet' },
          { value: 'text', label: 'Type the counts' },
        ]}
      />
      {mode === 'photo' ? (
        <>
          <PhotoInput id="count-file" label="Your stock count sheet" file={file} onFile={setFile} />
          <Notice tone="info" icon="info">
            Write one product per line with the number you counted. The photo is made smaller, read by your AI provider and not stored.
            Nothing changes until you check the counts and apply them.
          </Notice>
        </>
      ) : (
        <label className="field">
          One product per line, the count last
          <textarea
            className="textarea"
            rows={6}
            placeholder={'Rice 5kg 12\nMilo 400g 30'}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <span className="field-hint">Read on our server without any AI. Free.</span>
        </label>
      )}
      <button className="btn btn-primary" type="submit" disabled={busy || (mode === 'photo' ? !file : !text.trim())}>
        Read the counts
      </button>
      <StatusText message={status.message} error={status.error} />
    </form>
  );
}
