// Small UI primitives shared by every view. Class names match src/styles/*.css.

import type { ReactNode } from 'react';
import { Icon, type IconName } from '../../lib/icons';

export type Tone = '' | 'success' | 'warning' | 'error' | 'info' | 'ai' | 'dot';

export function Pill({ tone = '', icon, children }: { tone?: Tone; icon?: IconName; children: ReactNode }) {
  return (
    <span className={`pill${tone ? ` pill-${tone}` : ''}`}>
      {icon ? <Icon name={icon} /> : null}
      {children}
    </span>
  );
}

/** Percentage change badge. With `invert`, a fall is good (e.g. costs). */
export function Delta({ change, invert = false }: { change: number | null | undefined; invert?: boolean }) {
  if (change === null || change === undefined) return null;
  const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'flat';
  const good = invert ? direction === 'down' : direction === 'up';
  const tone = direction === 'flat' ? 'flat' : good ? 'up' : 'down';
  return (
    <span className={`delta delta-${tone}`}>
      {direction === 'up' ? '▲' : direction === 'down' ? '▼' : '•'} {Math.abs(change).toFixed(1)}%
    </span>
  );
}

export function Kpi({
  label,
  value,
  foot = null,
  text = false,
  icon,
}: {
  label: ReactNode;
  value: ReactNode;
  foot?: ReactNode;
  /** Render the value as prose (smaller type), e.g. "Needs costs". */
  text?: boolean;
  icon?: IconName;
}) {
  return (
    <div className="kpi">
      <span className="kpi-label">
        {icon ? <Icon name={icon} /> : null}
        {label}
      </span>
      <span className={`kpi-value${text ? ' text' : ''}`} title={typeof value === 'string' ? value : undefined}>
        {value}
      </span>
      <span className="kpi-foot">{foot}</span>
    </div>
  );
}

export function EmptyState({ title, message, action = null }: { title: ReactNode; message?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      {message ? <span>{message}</span> : null}
      {action}
    </div>
  );
}

export function SkeletonRows({ count = 3, height = 18 }: { count?: number; height?: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="skeleton" style={{ height: `${height}px`, margin: '8px 0' }} />
      ))}
    </>
  );
}

export function Notice({ tone = 'warning', icon = 'alert', children }: { tone?: 'warning' | 'error' | 'success' | 'info'; icon?: IconName; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`}>
      <Icon name={icon} />
      <span>{children}</span>
    </div>
  );
}

/** Inline status line under a form. */
export function StatusText({ message, error = false, id }: { message?: string | null; error?: boolean; id?: string }) {
  return (
    <p className={`status-text${error ? ' error' : ''}`} id={id} role="status" aria-live="polite">
      {message || ''}
    </p>
  );
}

/**
 * Segmented control. `mode="pressed"` is a toggle group (aria-pressed);
 * `mode="tabs"` is a tablist (aria-selected) whose panels the caller renders.
 */
export function Segmented<Value extends string>({
  options,
  value,
  onChange,
  label,
  mode = 'pressed',
  id,
}: {
  options: { value: Value; label: ReactNode }[];
  value: Value;
  onChange: (value: Value) => void;
  label: string;
  mode?: 'pressed' | 'tabs';
  id?: string;
}) {
  return (
    <div className="segmented" id={id} role={mode === 'tabs' ? 'tablist' : 'group'} aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role={mode === 'tabs' ? 'tab' : undefined}
          aria-pressed={mode === 'pressed' ? option.value === value : undefined}
          aria-selected={mode === 'tabs' ? option.value === value : undefined}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export interface Column<Row> {
  label: string;
  value: (row: Row) => ReactNode;
  num?: boolean;
  /** Sort key passed to `onSort` when the header is clicked. */
  sort?: string;
}

export interface SortState {
  key: string;
  dir: 'asc' | 'desc';
}

/**
 * Data table; shows an empty state when there are no rows. Pass sortState + onSort for sortable headers.
 * On phones (base.css, `.table-stack`) each row becomes a labelled card and the sort buttons a wrapping row,
 * so no column is hidden off-screen. Explicit roles keep table semantics when CSS changes the display type.
 */
export function DataTable<Row>({
  columns,
  rows,
  rowKey,
  empty = 'Nothing to show yet.',
  sortState = null,
  onSort,
}: {
  columns: Column<Row>[];
  rows: Row[];
  rowKey: (row: Row, index: number) => string | number;
  empty?: string;
  sortState?: SortState | null;
  onSort?: (key: string) => void;
}) {
  if (!rows.length) return <EmptyState title={empty} />;
  return (
    <table className="table table-stack" role="table">
      <thead role="rowgroup">
        <tr role="row">
          {columns.map((column) => {
            const sorted = sortState && column.sort && sortState.key === column.sort;
            return (
              <th
                key={column.label}
                className={column.num ? 'num' : ''}
                scope="col"
                role="columnheader"
                aria-sort={sorted ? (sortState.dir === 'asc' ? 'ascending' : 'descending') : undefined}
              >
                {column.sort && onSort ? (
                  <button type="button" onClick={() => onSort(column.sort as string)}>
                    {column.label}
                    {sorted ? (sortState.dir === 'asc' ? ' ↑' : ' ↓') : ''}
                  </button>
                ) : (
                  column.label
                )}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody role="rowgroup">
        {rows.map((row, index) => (
          <tr key={rowKey(row, index)} role="row">
            {columns.map((column) => (
              <td key={column.label} className={column.num ? 'num' : ''} role="cell" data-label={column.label}>
                {column.value(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Shown in place of forms the signed-in user's role cannot use (the server refuses them anyway). */
export function ReadOnlyNotice({ role, what }: { role: string; what: string }) {
  return (
    <Notice tone="info" icon="info">
      {`As ${role === 'accountant' ? 'an accountant' : `a ${role}`} you can view ${what}, but not change it. Ask the business owner if you need to.`}
    </Notice>
  );
}
