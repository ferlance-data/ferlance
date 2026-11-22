// Small progress ring for "how far along" values: setup steps, record completeness.
// It is a meter: the value is always printed in the middle and exposed to assistive tech,
// so the ring is decoration. The arc settles in once; reduced motion skips that.

import '../../styles/charts.css';

const SIZE = 64;
const STROKE = 7;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export function RadialProgress({
  value,
  max = 100,
  label,
  display,
  tone = 'default',
  size = SIZE,
}: {
  value: number;
  max?: number;
  label: string;
  /** Text in the middle; defaults to a whole-number percentage. */
  display?: string;
  tone?: 'default' | 'good' | 'warn';
  size?: number;
}) {
  const ratio = max > 0 ? Math.min(Math.max(value / max, 0), 1) : 0;
  // Never round up to 100%: "100%" must mean complete, not 99.6%.
  const percent = ratio < 1 ? Math.min(Math.round(ratio * 100), 99) : 100;
  const shown = display ?? `${percent}%`;
  return (
    <div className={`radial radial-${tone}`} style={{ width: size, height: size }} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={value} aria-valuetext={shown}>
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
        <circle className="radial-track" cx={SIZE / 2} cy={SIZE / 2} r={RADIUS} />
        <circle
          className="radial-fill"
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          strokeDasharray={`${ratio * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
        />
      </svg>
      <span className="radial-value num" aria-hidden="true">
        {shown}
      </span>
    </div>
  );
}
