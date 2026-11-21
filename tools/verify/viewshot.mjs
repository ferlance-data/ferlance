// Screenshot one workspace view (light/dark × desktop/phone) and report console errors.
// usage: node tools/verify/viewshot.mjs <baseUrl> <view> <outDir>
// Logs in as the seeded demo user via the API (sets the refresh cookie), then opens /app/<view>.
import { chromium } from 'playwright';
import fs from 'node:fs';

const [base, view, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const SIZES = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };
const errors = [];
const browser = await chromium.launch();
for (const theme of ['light', 'dark']) {
  for (const [sizeName, viewport] of Object.entries(SIZES)) {
    const ctx = await browser.newContext({ viewport, colorScheme: theme });
    await ctx.addInitScript((t) => localStorage.setItem('ferlance-theme', t), theme);
    const page = await ctx.newPage();
    page.on('console', (m) => m.type() === 'error' && errors.push(`${theme}/${sizeName}: ${m.text()}`));
    page.on('pageerror', (e) => errors.push(`${theme}/${sizeName}: PAGEERROR ${e.message}`));
    const login = await page.request.post(`${base}/api/auth/login`, { data: { email: 'demo@ferlance.test', password: 'demo-pass-123' } });
    if (!login.ok()) throw new Error(`login failed ${login.status()}`);
    await page.goto(`${base}/app/${view}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${out}/${view}-${theme}-${sizeName}.png`, fullPage: true });
    await ctx.close();
  }
}
await browser.close();
console.log(errors.length ? `console errors:\n${errors.join('\n')}` : 'console errors: none');
console.log(`screenshots in ${out}; compare with your baseline dir/${view}-<theme>-<size>.png`);
