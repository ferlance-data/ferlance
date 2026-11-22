// Dependency-free SVG donut for composition ("where does revenue come from").
//
// Rules from the dataviz method: at most five named slices plus "Other" (more never get new
// hues), colours follow a fixed validated order (--chart-cat-1..5), 2 px surface gaps
// between slices, text always in text colours, and the legend is a real table with values
// and shares, so nothing depends on colour alone. Slices fade and settle in on first paint
// using transform and opacity only, which is skipped under prefers-reduced-motion.

import { useId, useState } from 'react';
import '../../styles/charts.css';
import { money, plainPercent } from '../format';

export const MAX_SLICES = 5;

export interface Slice {
  label: string;
  value: number;
}

export interface DonutSlice extends Slice {
  share: number;
  color: string;
  other: boolean;
}

/** Top `max` positive slices in the given order, then everything else folded into "Other". */
export function foldSlices(items: Slice[], max = MAX_SLICES, total?: number): DonutSlice[] {
  const positive = items.filter((item) => item.value > 0);
  const kept = positive.slice(0, max);
  const sum = total && total > 0 ? total : positive.reduce((acc, item) => acc + item.value, 0);
  const rest = sum - kept.reduce((acc, item) => acc + item.value, 0);
  const slices: DonutSlice[] = kept.map((item, index) => ({ ...item, share: sum ? item.value / sum : 0, color: `var(--chart-cat-${index + 1})`, other: false }));
  if (rest > sum * 0.0005) slices.push({ label: 'Other', value: rest, share: sum ? rest / sum : 0, color: 'var(--chart-other)', other: true });
  return slices;
}

const SIZE = 160;
const STROKE = 22;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
const GAP = 2; // px of surface between slices

export function Donut({
  items,
  total,
  title,
  centerLabel,
  centerValue,
  formatValue = (value: number) => money(value),
  showLegend = true,
}: {
  items: Slice[];
  total?: number;
  title: string;
  centerLabel: string;
  centerValue: string;
  formatValue?: (value: number) => string;
  /** Hide the legend table visually when a ranked list next to the chart already shows the same values. */
  showLegend?: boolean;
}) {
  const slices = foldSlices(items, MAX_SLICES, total);
  const [active, setActive] = useState<number | null>(null);
  const tableId = useId();
  if (!slices.length) return null;

  const arcs = slices.map((slice, index) => {
    const start = slices.slice(0, index).reduce((sum, previous) => sum + previous.share, 0) * CIRCUMFERENCE;
    const length = slice.share * CIRCUMFERENCE;
    const visible = Math.max(length - (slices.length > 1 ? GAP : 0), 0.5);
    return { slice, index, dash: `${visible} ${CIRCUMFERENCE - visible}`, offset: -start };
  });
  const focus = active !== null ? slices[active] : null;

  return (
    <figure className={`donut${showLegend ? '' : ' donut-solo'}`}>
      <div className="donut-plot">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label={`${title}: ${slices.map((s) => `${s.label} ${plainPercent(s.share * 100, 0)}`).join(', ')}`} aria-describedby={tableId}>
          <circle className="donut-track" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} />
          <g transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}>
            {arcs.map(({ slice, index, dash, offset: dashOffset }) => (
              <circle
                key={slice.label}
                className={`donut-slice${active === index ? ' active' : ''}${active !== null && active !== index ? ' dim' : ''}`}
                style={{ stroke: slice.color, animationDelay: `${index * 40}ms` }}
                cx={SIZE / 2}
                cy={SIZE / 2}
                r={RADIUS}
                strokeDasharray={dash}
                strokeDashoffset={dashOffset}
                onPointerEnter={() => setActive(index)}
                onPointerLeave={() => setActive(null)}
                onPointerDown={() => setActive(index)}
              />
            ))}
          </g>
        </svg>
        <div className="donut-center" aria-hidden="true">
          <span className="donut-center-label">{focus ? focus.label : centerLabel}</span>
          <strong className="num">{focus ? plainPercent(focus.share * 100, 0) : centerValue}</strong>
        </div>
      </div>
      <table className={`donut-legend${showLegend ? '' : ' visually-hidden'}`} id={tableId}>
        <caption className="visually-hidden">{title}</caption>
        <thead className="visually-hidden">
          <tr>
            <th scope="col">Item</th>
            <th scope="col">Value</th>
            <th scope="col">Share</th>
          </tr>
        </thead>
        <tbody>
          {slices.map((slice, index) => (
            <tr
              key={slice.label}
              className={active === index ? 'active' : undefined}
              onPointerEnter={() => setActive(index)}
              onPointerLeave={() => setActive(null)}
            >
              <th scope="row">
                <span className="swatch" style={{ background: slice.color }} aria-hidden="true" />
                <span className="donut-legend-label">{slice.label}</span>
              </th>
              <td className="num">{formatValue(slice.value)}</td>
              <td className="num muted">{plainPercent(slice.share * 100, 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
