// Rendering shared across views: insight cards, ranked lists, dataset status, attention items.

import { Link } from 'react-router';
import { money, number, plainPercent } from '../../lib/format';
import { Icon, type IconName } from '../../lib/icons';
import type { Dataset, Insight } from '../../lib/types';
import { Pill, type Tone } from '../components/ui';

const SEVERITY: Record<string, [Tone, string]> = {
  positive: ['success', 'Positive'],
  attention: ['warning', 'Needs attention'],
  info: ['info', 'Info'],
};
const TYPE_LABEL: Record<string, string> = { summary: 'Summary', comparison: 'Comparison', anomaly: 'Signal', recommendation: 'Focus' };
const MONEY_KEYS = new Set(['total', 'revenue', 'current', 'previous', 'average_sale', 'gross_profit', 'cost', 'metric_value']);
const HIDDEN_KEYS = new Set(['metric_label', 'metric_value', 'direction', 'currency', 'product']);

function evidenceValue(key: string, value: unknown): string {
  if (typeof value === 'number' && MONEY_KEYS.has(key)) return money(value);
  if (key.endsWith('_pct') || key === 'percent') return value === null ? '—' : plainPercent(value as number, 2);
  if (typeof value === 'number') return number(value, 2);
  return String(value);
}

export function InsightCard({ item, compact = false }: { item: Insight; compact?: boolean }) {
  const [tone, label] = SEVERITY[item.severity] ?? (SEVERITY.info as [Tone, string]);
  const evidence = Object.entries(item.supporting_metric || {})
    .filter(([key, value]) => value !== null && value !== undefined && typeof value !== 'object' && !HIDDEN_KEYS.has(key))
    .slice(0, compact ? 3 : 8);
  return (
    <article className="insight">
      <div className="insight-head">
        <h3>{item.title}</h3>
        <span style={{ display: 'flex', gap: '6px' }}>
          <Pill>{TYPE_LABEL[item.type] || item.type}</Pill>
          <Pill tone={tone}>{label}</Pill>
        </span>
      </div>
      <p>{item.message}</p>
      {evidence.length ? (
        <div className="insight-evidence">
          {evidence.map(([key, value]) => (
            <span className="evidence" key={key}>
              <small>{key.replaceAll('_', ' ')}</small>
              <strong>{evidenceValue(key, value)}</strong>
            </span>
          ))}
        </div>
      ) : null}
      {!compact && item.limitations?.length ? <p className="insight-note">{item.limitations.join(' ')}</p> : null}
    </article>
  );
}

/** Ranked list items with a share-of-total bar, as used for products and customers. Render inside a <ul>/<ol>. */
export function RankItems<T>({
  items,
  name,
  value,
  total,
  sub,
  empty = 'Nothing to rank yet.',
}: {
  items: T[];
  name: (item: T) => string;
  value: (item: T) => number;
  total?: number | null;
  sub?: (item: T) => string;
  empty?: string;
}) {
  if (!items.length) return <li className="empty-state">{empty}</li>;
  const max = Math.max(...items.map((item) => Math.abs(value(item))), 1);
  return (
    <>
      {items.map((item, index) => (
        <li className="rank-item" key={`${name(item)}-${index}`}>
          <span className="rank-index">{String(index + 1).padStart(2, '0')}</span>
          <span className="rank-name">
            <strong title={name(item)}>{name(item)}</strong>
            <span className="share-bar">
              <i style={{ width: `${Math.max(2, (Math.abs(value(item)) / max) * 100)}%` }} />
            </span>
          </span>
          <span className="rank-value">
            {money(value(item))}
            <small>{sub ? sub(item) : total ? `${((value(item) / total) * 100).toFixed(1)}% of total` : ''}</small>
          </span>
        </li>
      ))}
    </>
  );
}

export function StatusPill({ dataset }: { dataset: Dataset }) {
  if (dataset.status === 'failed') return <Pill tone="error">Failed</Pill>;
  if (dataset.status === 'partial') return <Pill tone="warning">{`${number(dataset.rejected_rows)} rejected`}</Pill>;
  return <Pill tone="success">Processed</Pill>;
}

export interface AttentionEntry {
  tone: string;
  icon: IconName;
  title: string;
  /** In-app path such as pagePath('inventory'). */
  to?: string;
  detail?: string;
}

export function AttentionItem({ tone, icon, title, to, detail }: AttentionEntry) {
  return (
    <li className={`attention-item tone-${tone}`}>
      <span className="attention-icon">
        <Icon name={icon} />
      </span>
      <div>
        {to ? <Link to={to}>{title}</Link> : <strong>{title}</strong>}
        {detail ? <p>{detail}</p> : null}
      </div>
    </li>
  );
}
