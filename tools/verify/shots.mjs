// Screenshot every Ferlance view in light/dark at desktop/phone widths.
// usage: node shots.mjs <baseUrl> <outDir>
import { chromium } from 'playwright';
import fs from 'node:fs';

const [base, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const VIEWS = ['overview', 'products', 'insights', 'lance', 'inventory', 'position', 'data', 'settings'];
const SIZES = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };
const errors = [];

const browser = await chromium.launch();
for (const theme of ['light', 'dark']) {
  for (const [sizeName, viewport] of Object.entries(SIZES)) {
    const ctx = await browser.newContext({ viewport, colorScheme: theme });
    await ctx.addInitScript((t) => localStorage.setItem('ferlance-theme', t), theme);
    const page = await ctx.newPage();
    page.on('console', (m) => m.type() === 'error' && errors.push(`${theme}/${sizeName} ${page.url()}: ${m.text()}`));
    page.on('pageerror', (e) => errors.push(`${theme}/${sizeName} ${page.url()}: PAGEERROR ${e.message}`));
    await page.goto(`${base}/`, { waitUntil: 'networkidle' });
    if (theme === 'light') await page.screenshot({ path: `${out}/landing-${sizeName}.png`, fullPage: true });
    await page.goto(`${base}/?signin`, { waitUntil: 'networkidle' });
    const dlg = page.locator('dialog[open]');
    await dlg.getByLabel('Email').first().fill('demo@ferlance.test');
    await dlg.getByLabel('Password').first().fill('demo-pass-123');
    await dlg.getByRole('button', { name: 'Sign in' }).click();
    await page.waitForURL(/\/app/);
    for (const v of VIEWS) {
      await page.goto(`${base}/app#${v}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      await page.screenshot({ path: `${out}/${v}-${theme}-${sizeName}.png`, fullPage: true });
    }
    await ctx.close();
  }
}
await browser.close();
fs.writeFileSync(`${out}/console-errors.txt`, errors.join('\n'));
console.log(`done, ${errors.length} console errors`);
