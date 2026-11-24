// Credit report: what a lender would see, the readiness score with what raises it, and links the
// owner can share (frozen, expiring, revocable, every view logged).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, formatDateTime, money } from '../../lib/format';
import { RadialProgress } from '../../lib/chart/RadialProgress';
import { toast } from '../../lib/toast';
import { DataTable, Notice, Pill, SkeletonRows, StatusText } from '../components/ui';
import { keys, useWorkspace } from '../workspace';

interface Part {
  name: string;
  points: number;
  out_of: number;
  why: string;
  raise: string | null;
}

interface Report {
  business: string;
  as_of: string;
  from: string;
  score: number;
  parts: Part[];
  disclaimer: string;
  monthly: { month: string; sales: number; profit: number }[];
  facts: {
    months_with_sales: number;
    sales: number;
    net_profit: number;
    net_margin_pct: number | null;
    evidence: { statement_matched: number; momo_sms: number; self_reported: number; statement_matched_pct: number; momo_sms_pct: number };
    receivables: { owed: number; late_share_pct: number };
    stock_turnover: number | null;
  };
}

interface Share {
  id: string;
  lender: string;
  code: string;
  expires_at: string;
  revoked_at: string | null;
  created_at: string;
  views: number;
  last_view: string | null;
  active: boolean;
}

function Sharing() {
  const { business, businessPath } = useWorkspace();
  const queryClient = useQueryClient();
  const shares = useQuery({ queryKey: keys.business(business.id, 'credit-shares'), queryFn: ({ signal }) => request<Share[]>(businessPath('/credit/shares'), { signal }) });
  const [lender, setLender] = useState('');
  const [days, setDays] = useState(14);
  const [consent, setConsent] = useState(false);
  const [link, setLink] = useState<{ url: string; code: string } | null>(null);
  const [error, setError] = useState('');

  async function create(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      const result = await request<{ url: string; code: string }>(businessPath('/credit/shares'), { method: 'POST', json: { days, lender, consent } });
      setLink(result);
      setConsent(false);
      await queryClient.invalidateQueries({ queryKey: keys.business(business.id, 'credit-shares') });
    } catch (failure) {
      setError((failure as Error).message);
    }
  }

  async function revoke(id: string) {
    if (!window.confirm('Withdraw this link? The lender will no longer be able to open it.')) return;
    await request(businessPath(`/credit/shares/${id}/revoke`), { method: 'POST' }).catch((failure: Error) => toast(failure.message, { error: true }));
    await queryClient.invalidateQueries({ queryKey: keys.business(business.id, 'credit-shares') });
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      toast('Link copied.');
    } catch {
      toast('Copy the link from the box.');
    }
  }

  return (
    <form className="card" id="credit-share" onSubmit={(event) => void create(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">Share with a lender</h2>
          <p className="card-subtitle">The lender gets a link to a copy of this summary as it is today. Not your records, not live access. You can withdraw it at any time.</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <label className="field">
          Lender (optional)
          <input className="input" maxLength={120} placeholder="e.g. a microfinance or bank name" value={lender} onChange={(event) => setLender(event.target.value)} />
        </label>
        <label className="field">
          Link works for
          <select className="select" value={days} onChange={(event) => setDays(Number(event.target.value))}>
            {[7, 14, 30].map((value) => (
              <option key={value} value={value}>
                {`${value} days`}
              </option>
            ))}
          </select>
        </label>
        <label className="field field-inline">
          <input type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} />
          I agree to share this summary of my business with the person I send the link to.
        </label>
        <div className="button-row">
          <button className="btn btn-primary" type="submit" disabled={!consent}>
            Create link
          </button>
          <StatusText message={error} error />
        </div>
        {link ? (
          <Notice tone="success" icon="check">
            <div className="form-grid">
              <span>{`Verification code ${link.code}. The lender sees the same code on the page.`}</span>
              <input className="input" readOnly value={link.url} aria-label="Share link" onFocus={(event) => event.target.select()} />
              <div className="button-row">
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => void copy(link.url)}>
                  Copy link
                </button>
                <a className="btn btn-ghost btn-sm" href={`https://wa.me/?text=${encodeURIComponent(`Summary of ${business.name}: ${link.url} (code ${link.code})`)}`} target="_blank" rel="noopener noreferrer">
                  Send on WhatsApp
                </a>
              </div>
            </div>
          </Notice>
        ) : null}
      </div>
      {shares.data?.length ? (
        <div className="card-body">
          <ul className="pending-invites" id="credit-share-list">
            {shares.data.map((item) => (
              <li key={item.id}>
                <span>{`${item.lender || 'Link'} · ${item.code} · ${item.views} view(s)${item.last_view ? `, last ${formatDateTime(item.last_view)}` : ''} · ${item.active ? `until ${formatDate(item.expires_at)}` : item.revoked_at ? 'withdrawn' : 'expired'}`}</span>
                {item.active ? (
                  <button className="btn btn-ghost btn-sm" type="button" onClick={() => void revoke(item.id)}>
                    Withdraw
                  </button>
                ) : (
                  <Pill>{item.revoked_at ? 'Withdrawn' : 'Expired'}</Pill>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </form>
  );
}

export default function Credit() {
  const { business, businessPath, can } = useWorkspace();
  const report = useQuery({ queryKey: keys.business(business.id, 'credit'), queryFn: ({ signal }) => request<Report>(businessPath('/credit'), { signal }) });
  const data = report.data;
  if (!data) return <SkeletonRows count={6} />;
  const facts = data.facts;
  return (
    <>
      <div className="card" id="credit-score">
        <div className="card-header">
          <div>
            <h2 className="card-title">Readiness score</h2>
            <p className="card-subtitle">How complete and well-evidenced your records are. Lenders decide for themselves; this is not a credit decision.</p>
          </div>
          <RadialProgress value={data.score} max={100} label="Readiness score" display={String(data.score)} size={64} />
        </div>
        <ul className="debt-list">
          {data.parts.map((part) => (
            <li className="debt-card" key={part.name}>
              <div className="debt-head">
                <div className="file-cell">
                  <strong>{part.name}</strong>
                  <small>{part.why}</small>
                </div>
                <span className="num">{`${part.points} / ${part.out_of}`}</span>
              </div>
              {part.raise ? <small className="muted">{`To raise it: ${part.raise}`}</small> : null}
            </li>
          ))}
        </ul>
      </div>

      <div className="card" id="credit-facts">
        <div className="card-header">
          <div>
            <h2 className="card-title">What a lender sees</h2>
            <p className="card-subtitle">{`${formatDate(data.from)} to ${formatDate(data.as_of)}`}</p>
          </div>
        </div>
        <dl className="books-totals card-body">
          <div>
            <dt>Sales</dt>
            <dd>{money(facts.sales)}</dd>
          </div>
          <div>
            <dt>Net profit</dt>
            <dd>{`${money(facts.net_profit)}${facts.net_margin_pct != null ? ` (${facts.net_margin_pct}%)` : ''}`}</dd>
          </div>
          <div>
            <dt>Months with sales</dt>
            <dd>{`${facts.months_with_sales} of 12`}</dd>
          </div>
          <div>
            <dt>Matched to statements</dt>
            <dd>{`${facts.evidence.statement_matched_pct}%`}</dd>
          </div>
          <div>
            <dt>From MoMo messages</dt>
            <dd>{`${facts.evidence.momo_sms_pct}%`}</dd>
          </div>
          <div>
            <dt>Customers owe (over 60 days late)</dt>
            <dd>{`${money(facts.receivables.owed)} (${facts.receivables.late_share_pct}%)`}</dd>
          </div>
        </dl>
        <div className="table-wrap">
          <DataTable
            columns={[
              { label: 'Month', value: (row) => row.month },
              { label: 'Sales', num: true, value: (row) => money(row.sales) },
              { label: 'Profit', num: true, value: (row) => money(row.profit) },
            ]}
            rows={data.monthly}
            rowKey={(row) => row.month}
          />
        </div>
        <p className="footnote card-body">{data.disclaimer}</p>
      </div>

      {can('manage_business') ? <Sharing /> : <Notice tone="info" icon="info">Only the business owner can share this summary.</Notice>}
    </>
  );
}
