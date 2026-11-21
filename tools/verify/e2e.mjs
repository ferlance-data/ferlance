// End-to-end checks for paths the screenshot pass can't see.
// usage: node e2e.mjs http://127.0.0.1:8790   (backend with 4s access tokens + mock LLM)
import { chromium } from 'playwright';
const base = process.argv[2];
const results = [];
const check = (name, ok, extra = '') => { results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ` — ${extra}` : ''}`); };

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && !/403|503|401/.test(m.text()) && errors.push(m.text()));
const calls = [];
const statuses = [];
page.on('response', (r) => r.url().includes('/api/') && statuses.push(`${r.status()} ${new URL(r.url()).pathname}`));
page.on('request', (r) => r.url().includes('/api/') && calls.push(`${r.method()} ${new URL(r.url()).pathname}`));
await page.addInitScript(() => { window.__printed = 0; window.print = () => { window.__printed += 1; }; });

// Sign in through the landing dialog.
await page.goto(`${base}/?signin`, { waitUntil: 'networkidle' });
const dlg = page.locator('dialog[open]');
await dlg.getByLabel('Email').first().fill('demo@ferlance.test');
await dlg.getByLabel('Password').first().fill('demo-pass-123');
await dlg.getByRole('button', { name: 'Sign in' }).click();
await page.waitForURL(/\/app\/overview/);
check('landing sign-in lands on /app/overview', true);

// Print the financial report.
await page.getByRole('button', { name: /Print report/ }).click();
const report = await page.evaluate(() => ({ printed: window.__printed, text: document.getElementById('print-report').textContent, printing: document.body.classList.contains('printing') }));
check('overview print renders report and calls print()', report.printed === 1 && report.text.includes('FINANCIAL REPORT') && report.printing);
await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
check('afterprint cleans up', await page.evaluate(() => !document.body.classList.contains('printing') && document.getElementById('print-report').hidden));

// Ask Lance through the (mock) model, then reopen the saved conversation.
await page.getByRole('link', { name: 'Ask Lance' }).click();
await page.waitForURL(/\/app\/lance/);
const box = page.locator('textarea');
await box.fill('Which product sells best?');
await box.press('Enter');
await page.locator('.view-lance h3', { hasText: 'Best seller' }).waitFor({ timeout: 15000 });
check('Lance answer rendered as markdown', true);
check('model output cannot inject script', (await page.locator('.view-lance script').count()) === 0 && (await page.locator('.view-lance').textContent()).includes('<script>alert(1)</script>'));
await page.locator('.conversation').first().waitFor({ timeout: 5000 });
check('conversation appears in sidebar', (await page.locator('.conversation').count()) >= 1);
await page.getByRole('button', { name: 'New chat' }).click();
check('new chat clears thread', (await page.locator('.view-lance h3', { hasText: 'Best seller' }).count()) === 0);
await page.locator('.conversation').first().click();
await page.locator('.view-lance h3', { hasText: 'Best seller' }).waitFor({ timeout: 5000 });
check('reopening a conversation restores messages', (await page.locator('.conversation[aria-current="true"]').count()) === 1);

// Expired access token: wait past the 4s TTL, navigate client-side, expect one refresh + retry.
await page.waitForTimeout(5000);
const before = calls.filter((c) => c === 'POST /api/auth/refresh').length;
await page.getByRole('link', { name: 'Products' }).click();
await page.locator('#scope-range').selectOption('90'); // uncached key -> real request with the expired token
await page.locator('[data-view="products"] table.table').waitFor({ timeout: 10000 });
await page.waitForLoadState('networkidle');
const refreshes = calls.filter((c) => c === 'POST /api/auth/refresh').length - before;
check('expired token refreshes once and the view loads', refreshes === 1 && statuses.some((s) => s.startsWith('401 ') && s.endsWith('/analytics')), `${refreshes} refresh call(s)`);
check('still on /app/products (no sign-in redirect)', page.url().endsWith('/app/products'));

// Reload keeps the session (refresh cookie).
await page.reload({ waitUntil: 'networkidle' });
check('reload keeps the session', page.url().endsWith('/app/products') && (await page.locator('#page-title').textContent()) === 'Products');

// Scope change refetches analytics with dates.
const n = calls.length;
await page.locator('#scope-range').selectOption('30');
await page.waitForLoadState('networkidle');
check('scope change refetches with the new range', calls.slice(n).some((c) => c.endsWith('/analytics')));

// Inventory + position print.
for (const [link, button, marker] of [['Inventory', /Print report/, 'INVENTORY'], ['Financial position', /Print statement/, 'FINANCIAL POSITION']]) {
  await page.getByRole('link', { name: link }).click();
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: button }).click();
  check(`${link} print`, (await page.evaluate(() => document.getElementById('print-report').textContent)).includes(marker));
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
}

// Sign out.
await page.getByRole('button', { name: 'Sign out' }).click();
await page.waitForURL((url) => url.pathname === '/');
await page.goto(`${base}/app/overview`);
await page.waitForURL(/\?signin/, { timeout: 10000 });
check('after sign-out, /app redirects to sign-in', true);

check('no unexpected console/page errors', errors.length === 0, errors.join(' | '));
console.log(results.join('\n'));
await browser.close();
