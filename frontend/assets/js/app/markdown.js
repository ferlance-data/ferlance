// Minimal, safe Markdown for Lance answers: paragraphs, headings, lists, tables,
// **bold**, *italic* and `code`. Builds DOM nodes directly; never uses innerHTML.

import { h } from './dom.js';

function inline(text) {
  const nodes = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    const token = match[0];
    if (token.startsWith('**')) nodes.push(h('strong', {}, token.slice(2, -2)));
    else if (token.startsWith('`')) nodes.push(h('code', {}, token.slice(1, -1)));
    else nodes.push(h('em', {}, token.slice(1, -1)));
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());

export function renderMarkdown(source) {
  const blocks = [];
  const lines = String(source || '').replace(/\r\n/g, '\n').split('\n');
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      blocks.push(h(heading[1].length <= 2 ? 'h3' : 'h4', {}, inline(heading[2])));
      index += 1;
      continue;
    }
    if (/^\s*\|/.test(line) && index + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[index + 1])) {
      const header = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && /^\s*\|/.test(lines[index])) {
        rows.push(cells(lines[index]));
        index += 1;
      }
      blocks.push(
        h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
          h('thead', {}, h('tr', {}, header.map((cell) => h('th', {}, inline(cell))))),
          h('tbody', {}, rows.map((row) => h('tr', {}, row.map((cell) => h('td', {}, inline(cell)))))),
        )),
      );
      continue;
    }
    const listMatch = line.match(/^\s*([-*•]|\d+[.)])\s+/);
    if (listMatch) {
      const ordered = /\d/.test(listMatch[1]);
      const items = [];
      while (index < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[index])) {
        items.push(h('li', {}, inline(lines[index].replace(/^\s*([-*•]|\d+[.)])\s+/, ''))));
        index += 1;
      }
      blocks.push(h(ordered ? 'ol' : 'ul', {}, items));
      continue;
    }
    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !/^(#{1,4}\s|\s*([-*•]|\d+[.)])\s+|\s*\|)/.test(lines[index])) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(h('p', {}, inline(paragraph.join(' '))));
  }
  return blocks;
}
