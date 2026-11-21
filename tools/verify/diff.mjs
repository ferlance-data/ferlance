import fs from 'node:fs'; import { PNG } from 'pngjs'; import pixelmatch from 'pixelmatch';
const [a, b, outDir] = process.argv.slice(2); fs.mkdirSync(outDir, { recursive: true });
for (const f of fs.readdirSync(a).filter((x) => x.endsWith('.png'))) {
  if (!fs.existsSync(`${b}/${f}`)) { console.log(f, 'MISSING'); continue; }
  const A = PNG.sync.read(fs.readFileSync(`${a}/${f}`)), B = PNG.sync.read(fs.readFileSync(`${b}/${f}`));
  if (A.width !== B.width || A.height !== B.height) { console.log(f, `SIZE ${A.width}x${A.height} vs ${B.width}x${B.height}`); continue; }
  const d = new PNG({ width: A.width, height: A.height });
  const n = pixelmatch(A.data, B.data, d.data, A.width, A.height, { threshold: 0.1 });
  if (n) fs.writeFileSync(`${outDir}/${f}`, PNG.sync.write(d));
  console.log(f, n ? `${n} px (${(100 * n / (A.width * A.height)).toFixed(3)}%)` : 'identical');
}
