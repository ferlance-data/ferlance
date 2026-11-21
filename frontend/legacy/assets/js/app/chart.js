// Dependency-free SVG bar chart with an optional overlay line (revenue bars, cost line).

import { h, money, number } from './dom.js';

const NS = 'http://www.w3.org/2000/svg';
const HEIGHT = 260;
const PAD = { top: 12, right: 8, bottom: 26, left: 58 };

function svg(tag, attrs = {}) {
  const node = document.createElementNS(NS, tag);
  Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

function niceMax(value) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * magnitude >= value / 4) * magnitude;
  return Math.ceil(value / step) * step;
}

function shortLabel(period) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(period)) {
    return new Date(`${period}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  }
  if (/^\d{4}-\d{2}$/.test(period)) {
    return new Date(`${period}-01T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
  }
  return period.replace(/^\d{2}(\d{2})-/, "'$1 ");
}

/**
 * @param {HTMLElement} target
 * @param {{ period: string, value: number, transactions?: number }[]} bars
 * @param {{ line?: Map<string, number>, barLabel?: string, lineLabel?: string }} options
 */
export function renderBarChart(target, bars, { line = null, barLabel = 'Revenue', lineLabel = 'Cost' } = {}) {
  target.replaceChildren();
  target._chartObserver?.disconnect();
  if (!bars.length) {
    target.append(h('div', { class: 'empty-state' }, h('strong', {}, 'No records in this period'), h('span', {}, 'Try a wider date range or a different file.')));
    return;
  }
  const draw = () => {
    const width = Math.max(target.clientWidth, 280);
    const innerWidth = width - PAD.left - PAD.right;
    const innerHeight = HEIGHT - PAD.top - PAD.bottom;
    const values = bars.map((bar) => bar.value);
    const lineValues = line ? bars.map((bar) => line.get(bar.period) ?? null) : [];
    const max = niceMax(Math.max(...values.map(Math.abs), ...lineValues.filter((value) => value !== null).map(Math.abs), 0));
    const y = (value) => PAD.top + innerHeight - (Math.max(value, 0) / max) * innerHeight;
    const band = innerWidth / bars.length;
    const barWidth = Math.max(2, Math.min(42, band * 0.64));

    const root = svg('svg', { viewBox: `0 0 ${width} ${HEIGHT}`, role: 'img', 'aria-label': `${barLabel} chart with ${bars.length} periods` });
    for (let tick = 0; tick <= 4; tick += 1) {
      const value = (max / 4) * tick;
      const ty = y(value);
      root.append(svg('line', { class: 'grid-line', x1: PAD.left, x2: width - PAD.right, y1: ty, y2: ty }));
      const label = svg('text', { class: 'axis', x: PAD.left - 8, y: ty + 3.5, 'text-anchor': 'end' });
      label.textContent = money(value, { compact: true });
      root.append(label);
    }
    const labelEvery = Math.ceil(bars.length / Math.max(1, Math.floor(innerWidth / 70)));
    const barNodes = bars.map((bar, index) => {
      const cx = PAD.left + band * index + band / 2;
      const top = y(bar.value);
      const node = svg('rect', {
        class: 'bar',
        x: cx - barWidth / 2,
        y: top,
        width: barWidth,
        height: Math.max(1, PAD.top + innerHeight - top),
        rx: Math.min(4, barWidth / 3),
      });
      root.append(node);
      if (index % labelEvery === 0) {
        const label = svg('text', { class: 'axis', x: cx, y: HEIGHT - 8, 'text-anchor': 'middle' });
        label.textContent = shortLabel(bar.period);
        root.append(label);
      }
      return node;
    });
    if (line) {
      const points = bars
        .map((bar, index) => [PAD.left + band * index + band / 2, line.get(bar.period)])
        .filter(([, value]) => value !== undefined && value !== null);
      if (points.length) {
        root.append(svg('path', { class: 'cost-line', d: points.map(([px, value], index) => `${index ? 'L' : 'M'}${px},${y(value)}`).join(' ') }));
        if (points.length <= 40) points.forEach(([px, value]) => root.append(svg('circle', { class: 'cost-dot', cx: px, cy: y(value), r: 3 })));
      }
    }
    const tooltip = h('div', { class: 'chart-tooltip', hidden: true });
    const hit = svg('rect', { x: PAD.left, y: PAD.top, width: innerWidth, height: innerHeight, fill: 'transparent' });
    hit.addEventListener('mousemove', (event) => {
      const box = root.getBoundingClientRect();
      const scale = width / box.width;
      const index = Math.min(bars.length - 1, Math.max(0, Math.floor(((event.clientX - box.left) * scale - PAD.left) / band)));
      const bar = bars[index];
      barNodes.forEach((node, nodeIndex) => node.classList.toggle('active', nodeIndex === index));
      const rows = [h('div', {}, h('span', {}, barLabel), h('span', {}, money(bar.value)))];
      if (line && line.has(bar.period)) rows.push(h('div', {}, h('span', {}, lineLabel), h('span', {}, money(line.get(bar.period)))));
      if (bar.transactions !== undefined) rows.push(h('div', {}, h('span', {}, 'Records'), h('span', {}, number(bar.transactions))));
      tooltip.replaceChildren(h('b', {}, bar.period), ...rows);
      tooltip.hidden = false;
      tooltip.style.left = `${(PAD.left + band * index + band / 2) / scale}px`;
      tooltip.style.top = `${y(bar.value) / scale}px`;
    });
    hit.addEventListener('mouseleave', () => {
      tooltip.hidden = true;
      barNodes.forEach((node) => node.classList.remove('active'));
    });
    root.append(hit);
    target.replaceChildren(root, tooltip);
  };
  draw();
  let lastWidth = target.clientWidth;
  target._chartObserver = new ResizeObserver(() => {
    if (Math.abs(target.clientWidth - lastWidth) > 8) {
      lastWidth = target.clientWidth;
      draw();
    }
  });
  target._chartObserver.observe(target);
}
