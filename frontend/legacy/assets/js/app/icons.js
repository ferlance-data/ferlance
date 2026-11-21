// Stroke icons (24px grid, Lucide-style). Strings are path data; objects are shapes.
const ICONS = {
  overview: [{ rect: [3, 3, 7, 9, 1] }, { rect: [14, 3, 7, 5, 1] }, { rect: [14, 12, 7, 9, 1] }, { rect: [3, 16, 7, 5, 1] }],
  products: ['M12.586 2.586A2 2 0 0 0 11.172 2H4a2 2 0 0 0-2 2v7.172a2 2 0 0 0 .586 1.414l8.704 8.704a2.426 2.426 0 0 0 3.42 0l6.58-6.58a2.426 2.426 0 0 0 0-3.42z', { circle: [7.5, 7.5, 1] }],
  insights: ['M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5', 'M9 18h6', 'M10 22h4'],
  sparkles: ['M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z', 'M20 3v4', 'M22 5h-4'],
  inventory: ['M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z', 'M12 22V12', 'm3.3 7 8.7 5 8.7-5', 'm7.5 4.27 9 5.15'],
  scale: ['m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z', 'm2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z', 'M7 21h10', 'M12 3v18', 'M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2'],
  database: [{ ellipse: [12, 5, 9, 3] }, 'M3 5V19A9 3 0 0 0 21 19V5', 'M3 12A9 3 0 0 0 21 12'],
  settings: ['M20 7h-9', 'M14 17H5', { circle: [17, 17, 3] }, { circle: [7, 7, 3] }],
  logout: ['M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4', 'm16 17 5-5-5-5', 'M21 12H9'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  x: ['M18 6 6 18', 'm6 6 12 12'],
  calendar: [{ rect: [3, 4, 18, 18, 2] }, 'M16 2v4', 'M8 2v4', 'M3 10h18'],
  search: [{ circle: [11, 11, 8] }, 'm21 21-4.3-4.3'],
  'arrow-right': ['M5 12h14', 'm12 5 7 7-7 7'],
  plus: ['M5 12h14', 'M12 5v14'],
  send: ['m5 12 7-7 7 7', 'M12 19V5'],
  upload: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm17 8-5-5-5 5', 'M12 3v12'],
  download: ['M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4', 'm7 10 5 5 5-5', 'M12 15V3'],
  printer: ['M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2', 'M6 9V3a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v6', { rect: [6, 14, 12, 8, 1] }],
  check: ['M20 6 9 17l-5-5'],
  alert: ['m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3', 'M12 9v4', 'M12 17h.01'],
  'trending-up': ['M22 7 13.5 15.5 8.5 10.5 2 17', 'M16 7h6v6'],
  'trending-down': ['M22 17 13.5 8.5 8.5 13.5 2 7', 'M16 17h6v-6'],
  info: [{ circle: [12, 12, 10] }, 'M12 16v-4', 'M12 8h.01'],
  file: ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z', 'M14 2v4a2 2 0 0 0 2 2h4'],
  at: [{ circle: [12, 12, 4] }, 'M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-4 8'],
  edit: ['M12 20h9', 'M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z'],
  archive: [{ rect: [2, 3, 20, 5, 1] }, 'M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8', 'M10 12h4'],
  refresh: ['M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16', 'M8 16H3v5'],
  coins: [{ circle: [8, 8, 6] }, 'M18.09 10.37A6 6 0 1 1 10.34 18', 'M7 6h1v4', 'm16.71 13.88.7.71-2.82 2.82'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', { circle: [9, 7, 4] }, 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  receipt: ['M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z', 'M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8', 'M12 17.5v-11'],
};

const NS = 'http://www.w3.org/2000/svg';

export function icon(name) {
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.75');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('icon');
  (ICONS[name] || ICONS.info).forEach((part) => {
    let node;
    if (typeof part === 'string') {
      node = document.createElementNS(NS, 'path');
      node.setAttribute('d', part);
    } else if (part.circle) {
      node = document.createElementNS(NS, 'circle');
      ['cx', 'cy', 'r'].forEach((key, index) => node.setAttribute(key, part.circle[index]));
    } else if (part.ellipse) {
      node = document.createElementNS(NS, 'ellipse');
      ['cx', 'cy', 'rx', 'ry'].forEach((key, index) => node.setAttribute(key, part.ellipse[index]));
    } else if (part.rect) {
      node = document.createElementNS(NS, 'rect');
      ['x', 'y', 'width', 'height', 'rx'].forEach((key, index) => node.setAttribute(key, part.rect[index]));
    }
    svg.append(node);
  });
  return svg;
}

/** Replace every `[data-icon]` placeholder under `root` with its SVG. */
export function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((holder) => {
    if (holder.querySelector('svg')) return;
    holder.prepend(icon(holder.dataset.icon));
  });
}
