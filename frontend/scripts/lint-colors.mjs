// Colour lint: colours come from design tokens (docs/DESIGN_SYSTEM.md).
// CSS: colour literals (#hex, rgb(), hsl()) may appear only in custom-property declarations (`--token: …`).
// TS/TSX: a string that is just a colour literal is flagged unless the line says `color-lint: allow`.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const src = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src');
const CSS_COLOR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\(/;
const TS_COLOR = /(['"`])(?:#[0-9a-fA-F]{3,8}|(?:rgb|rgba|hsl|hsla)\([^'"`]*\))\1/;

const files = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? files(full) : [full];
  });

const problems = [];
for (const file of files(src)) {
  const rel = path.relative(path.join(src, '..'), file);
  if (file.endsWith('.css')) {
    // Blank out comments but keep line numbers.
    const text = fs.readFileSync(file, 'utf8').replace(/\/\*[\s\S]*?\*\//g, (c) => c.replace(/[^\n]/g, ' '));
    text.split('\n').forEach((line, i) => {
      // Inline data: URIs encode '#' as %23, so they never match.
      if (CSS_COLOR.test(line) && !line.trim().startsWith('--')) problems.push(`${rel}:${i + 1}: ${line.trim()}`);
    });
  } else if (/\.(ts|tsx)$/.test(file) && !/\.test\.tsx?$/.test(file)) {
    fs.readFileSync(file, 'utf8')
      .split('\n')
      .forEach((line, i) => {
        if (TS_COLOR.test(line) && !line.includes('color-lint: allow')) problems.push(`${rel}:${i + 1}: ${line.trim()}`);
      });
  }
}

if (problems.length) {
  console.error(`Colour literals outside design tokens (use a var(--token); see docs/DESIGN_SYSTEM.md):\n${problems.join('\n')}`);
  process.exit(1);
}
console.log('lint-colors: ok');
