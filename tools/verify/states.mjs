// Screenshot data states beyond the demo default. usage: node states.mjs <base> <outDir>
import { chromium } from 'playwright';
import fs from 'node:fs';
const [base, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const STATES = [
  { name: 'costs-all', email: 'demo@ferlance.test', file: 'shop_sales_2026.csv', range: 'all', views: ['overview', 'products', 'insights'] },
  { name: 'costs-30d', email: 'demo@ferlance.test', file: 'shop_sales_2026.csv', range: '30', views: ['overview', 'products', 'insights'] },
  { name: 'fresh', email: 'fresh@ferlance.test', views: ['overview', 'products', 'insights', 'lance', 'inventory', 'position', 'data'] },
  { name: 'costonly', email: 'costs@ferlance.test', range: '90', views: ['overview', 'products', 'insights'] },
];
const LOOKS = [['light', { width: 1440, height: 900 }, 'desktop'], ['dark', { width: 390, height: 844 }, 'phone']];
const errors = [];
const browser = await chromium.launch();
for (const s of STATES) for (const [theme, viewport, size] of LOOKS) {
  const ctx = await browser.newContext({ viewport, colorScheme: theme });
  await ctx.addInitScript((t) => localStorage.setItem('ferlance-theme', t), theme);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(`${s.name}: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && !/403/.test(m.text()) && errors.push(`${s.name}: ${m.text()}`));
  await page.request.post(`${base}/api/auth/login`, { data: { email: s.email, password: 'demo-pass-123' } });
  for (const v of s.views) {
    await page.goto(`${base}/app#${v}`, { waitUntil: 'networkidle' });
    if (s.file) {
      const value = await page.locator('#scope-dataset option', { hasText: s.file }).first().getAttribute('value');
      await page.locator('#scope-dataset').selectOption(value);
      await page.waitForLoadState('networkidle');
    }
    if (s.range && s.range !== 'all') { await page.locator('#scope-range').selectOption(s.range); await page.waitForLoadState('networkidle'); }
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${s.name}-${v}-${theme}-${size}.png`, fullPage: true });
  }
  await ctx.close();
}
await browser.close();
console.log(errors.length ? errors.join('\n') : 'no console errors');
