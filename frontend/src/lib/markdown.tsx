// Minimal, safe Markdown for Lance answers: paragraphs, headings, lists, tables,
// **bold**, *italic* and `code`. Produces React elements, so text is always escaped;
// raw HTML in the source renders as literal text.

import type { ReactNode } from 'react';

function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) nodes.push(text.slice(last, start));
    const token = match[0];
    if (token.startsWith('**')) nodes.push(<strong key={start}>{token.slice(2, -2)}</strong>);
    else if (token.startsWith('`')) nodes.push(<code key={start}>{token.slice(1, -1)}</code>);
    else nodes.push(<em key={start}>{token.slice(1, -1)}</em>);
    last = start + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

const cells = (line: string): string[] =>
  line
    .trim()
    .replace(/^\||\|$/g, '')
    .split('|')
    .map((cell) => cell.trim());

const LIST_ITEM = /^\s*([-*•]|\d+[.)])\s+/;

export function renderMarkdown(source: string | null | undefined): ReactNode[] {
  const blocks: ReactNode[] = [];
  const lines = String(source || '')
    .replace(/\r\n/g, '\n')
    .split('\n');
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] as string;
    const key = index;
    if (!line.trim()) {
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const Tag = (heading[1] as string).length <= 2 ? 'h3' : 'h4';
      blocks.push(<Tag key={key}>{inline(heading[2] as string)}</Tag>);
      index += 1;
      continue;
    }
    if (/^\s*\|/.test(line) && index + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[index + 1] as string)) {
      const header = cells(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && /^\s*\|/.test(lines[index] as string)) {
        rows.push(cells(lines[index] as string));
        index += 1;
      }
      blocks.push(
        <div className="table-wrap" key={key}>
          <table className="table">
            <thead>
              <tr>
                {header.map((cell, cellIndex) => (
                  <th key={cellIndex}>{inline(cell)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td key={cellIndex}>{inline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const listMatch = line.match(LIST_ITEM);
    if (listMatch) {
      const ordered = /\d/.test(listMatch[1] as string);
      const items: ReactNode[] = [];
      while (index < lines.length && LIST_ITEM.test(lines[index] as string)) {
        items.push(<li key={index}>{inline((lines[index] as string).replace(LIST_ITEM, ''))}</li>);
        index += 1;
      }
      blocks.push(ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>);
      continue;
    }
    const paragraph = [line.trim()];
    index += 1;
    while (index < lines.length && (lines[index] as string).trim() && !/^(#{1,4}\s|\s*([-*•]|\d+[.)])\s+|\s*\|)/.test(lines[index] as string)) {
      paragraph.push((lines[index] as string).trim());
      index += 1;
    }
    blocks.push(<p key={key}>{inline(paragraph.join(' '))}</p>);
  }
  return blocks;
}

export function Markdown({ source }: { source: string | null | undefined }) {
  return <>{renderMarkdown(source)}</>;
}
