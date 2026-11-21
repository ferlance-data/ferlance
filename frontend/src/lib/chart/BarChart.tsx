// Dependency-free SVG bar chart with an optional overlay line (revenue bars, cost line).

import { useLayoutEffect, useRef, useState } from 'react';
import { money, number } from '../format';

const HEIGHT = 260;
const PAD = { top: 12, right: 8, bottom: 26, left: 58 };

export interface Bar {
  period: string;
  value: number;
  transactions?: number;
}

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = ([1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= value / 4) ?? 10) * magnitude;
  return Math.ceil(value / step) * step;
}

export function shortLabel(period: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) {
    return new Date(`${period}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  }
  if (/^\d{4}-\d{2}$/.test(period)) {
    return new Date(`${period}-01T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
  }
  return period.replace(/^\d{2}(\d{2})-/, "'$1 ");
}

/** Track an element's width, ignoring sub-8px jitter so tiny layout shifts don't redraw. */
function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) return;
    setWidth(node.clientWidth);
    const observer = new ResizeObserver(() => {
      setWidth((current) => (Math.abs(node.clientWidth - current) > 8 ? node.clientWidth : current));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export function BarChart({
  bars,
  line = null,
  barLabel = 'Revenue',
  lineLabel = 'Cost',
  className = 'chart',
  id,
}: {
  bars: Bar[];
  line?: Map<string, number> | null;
  barLabel?: string;
  lineLabel?: string;
  className?: string;
  id?: string;
}) {
  const [ref, measured] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);

  if (!bars.length) {
    return (
      <div className={className} id={id} ref={ref}>
        <div className="empty-state">
          <strong>No records in this period</strong>
          <span>Try a wider date range or a different file.</span>
        </div>
      </div>
    );
  }

  const width = Math.max(measured, 280);
  const innerWidth = width - PAD.left - PAD.right;
  const innerHeight = HEIGHT - PAD.top - PAD.bottom;
  const values = bars.map((bar) => bar.value);
  const lineValues = line ? bars.map((bar) => line.get(bar.period) ?? null) : [];
  const max = niceMax(Math.max(...values.map(Math.abs), ...lineValues.filter((value): value is number => value !== null).map(Math.abs), 0));
  const y = (value: number) => PAD.top + innerHeight - (Math.max(value, 0) / max) * innerHeight;
  const band = innerWidth / bars.length;
  const barWidth = Math.max(2, Math.min(42, band * 0.64));
  const labelEvery = Math.ceil(bars.length / Math.max(1, Math.floor(innerWidth / 70)));
  const cx = (index: number) => PAD.left + band * index + band / 2;

  const points = line
    ? bars.map((bar, index) => [cx(index), line.get(bar.period)] as const).filter((point): point is readonly [number, number] => point[1] !== undefined && point[1] !== null)
    : [];

  const onMove = (event: React.MouseEvent<SVGRectElement>) => {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const box = svg.getBoundingClientRect();
    const scale = width / box.width;
    setActive(Math.min(bars.length - 1, Math.max(0, Math.floor(((event.clientX - box.left) * scale - PAD.left) / band))));
  };

  const activeBar = active !== null ? bars[active] : undefined;
  const scale = measured ? width / measured : 1;

  return (
    <div className={className} id={id} ref={ref}>
      <svg viewBox={`0 0 ${width} ${HEIGHT}`} role="img" aria-label={`${barLabel} chart with ${bars.length} periods`}>
        {[0, 1, 2, 3, 4].map((tick) => {
          const value = (max / 4) * tick;
          const ty = y(value);
          return (
            <g key={tick}>
              <line className="grid-line" x1={PAD.left} x2={width - PAD.right} y1={ty} y2={ty} />
              <text className="axis" x={PAD.left - 8} y={ty + 3.5} textAnchor="end">
                {money(value, { compact: true })}
              </text>
            </g>
          );
        })}
        {bars.map((bar, index) => {
          const top = y(bar.value);
          return (
            <g key={bar.period}>
              <rect
                className={`bar${active === index ? ' active' : ''}`}
                x={cx(index) - barWidth / 2}
                y={top}
                width={barWidth}
                height={Math.max(1, PAD.top + innerHeight - top)}
                rx={Math.min(4, barWidth / 3)}
              />
              {index % labelEvery === 0 ? (
                <text className="axis" x={cx(index)} y={HEIGHT - 8} textAnchor="middle">
                  {shortLabel(bar.period)}
                </text>
              ) : null}
            </g>
          );
        })}
        {points.length ? (
          <>
            <path className="cost-line" d={points.map(([px, value], index) => `${index ? 'L' : 'M'}${px},${y(value)}`).join(' ')} />
            {points.length <= 40 ? points.map(([px, value]) => <circle key={px} className="cost-dot" cx={px} cy={y(value)} r={3} />) : null}
          </>
        ) : null}
        <rect x={PAD.left} y={PAD.top} width={innerWidth} height={innerHeight} fill="transparent" onMouseMove={onMove} onMouseLeave={() => setActive(null)} />
      </svg>
      <div
        className="chart-tooltip"
        hidden={!activeBar}
        style={activeBar && active !== null ? { left: `${cx(active) / scale}px`, top: `${y(activeBar.value) / scale}px` } : undefined}
      >
        {activeBar ? (
          <>
            <b>{activeBar.period}</b>
            <div>
              <span>{barLabel}</span>
              <span>{money(activeBar.value)}</span>
            </div>
            {line && line.has(activeBar.period) ? (
              <div>
                <span>{lineLabel}</span>
                <span>{money(line.get(activeBar.period))}</span>
              </div>
            ) : null}
            {activeBar.transactions !== undefined ? (
              <div>
                <span>Records</span>
                <span>{number(activeBar.transactions)}</span>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </div>
  );
}
