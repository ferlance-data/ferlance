// Second e2e pass: drawer, custom range, view-only-this-file, admin, insights advice, Lance across navigation.
// usage: node e2e2.mjs http://127.0.0.1:8791   (admin email = demo, secret key set, 3s mock LLM)
import { chromium } from 'playwright';
const base = process.argv[2];
const results = [];
const check = (name, ok, extra = '') => results.push(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ` — ${extra}` : ''}`);
const browser = await chromium.launch();
const errors = [];
async function newPage(viewport) {
  const page = await (await browser.newContext({ viewport })).newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => m.type() === 'error' && !/40[13]/.test(m.text()) && errors.push(m.text()));
  await page.request.post(`${base}/api/auth/login`, { data: { email: 'demo@ferlance.test', password: 'demo-pass-123' } });
  return page;
}

// Phone drawer.
let page = await newPage({ width: 390, height: 844 });
await page.goto(`${base}/app/overview`, { waitUntil: 'networkidle' });
await page.locator('#menu-btn').click();
check('menu opens the drawer', await page.locator('.shell.nav-open').count() === 1 && await page.locator('#menu-btn').getAttribute('aria-expanded') === 'true');
await page.locator('#sidebar').getByRole('link', { name: 'Inventory' }).click();
await page.waitForURL(/\/app\/inventory/);
check('nav link navigates and closes the drawer', await page.locator('.shell.nav-open').count() === 0);
await page.locator('#menu-btn').click();
await page.locator('#sidebar-backdrop').click({ position: { x: 380, y: 400 } });
check('backdrop closes the drawer', await page.locator('.shell.nav-open').count() === 0);
await page.locator('#menu-btn').click();
await page.keyboard.press('Escape');
check('Escape closes the drawer', await page.locator('.shell.nav-open').count() === 0);
await page.context().close();

page = await newPage({ width: 1440, height: 900 });
const calls = [];
page.on('request', (r) => r.url().includes('/analytics') && calls.push(new URL(r.url()).search));

// Custom range.
await page.goto(`${base}/app/overview`, { waitUntil: 'networkidle' });
await page.locator('#scope-range').selectOption('custom');
check('custom shows date inputs prefilled from data bounds', await page.locator('#scope-custom').isVisible() && (await page.locator('#scope-from').inputValue()).length === 10);
await page.locator('#scope-from').fill('2026-09-01');
await page.locator('#scope-to').fill('2026-08-01');
await page.locator('#scope-apply').click();
check('from > to shows an error toast', await page.locator('.toast.error', { hasText: 'start date must be on or before' }).isVisible());
await page.locator('#scope-to').fill('2026-09-30');
await page.locator('#scope-apply').click();
await page.waitForLoadState('networkidle');
check('apply refetches with the custom dates', calls.some((q) => q.includes('from=2026-09-01') && q.includes('to=2026-09-30')));

// View only this file.
await page.goto(`${base}/app/data`, { waitUntil: 'networkidle' });
await page.getByRole('button', { name: /\d+ notes?/ }).first().click();
const viewOnly = page.getByRole('button', { name: 'View only this file' });
if (await viewOnly.count()) {
  const scopedRequest = page.waitForRequest((r) => r.url().includes('/analytics') && r.url().includes('dataset_id='), { timeout: 10000 }).catch(() => null);
  await viewOnly.first().click();
  await page.waitForURL(/\/app\/overview/);
  await scopedRequest;
  const scoped = await page.locator('#scope-dataset').inputValue();
  check('"View only this file" scopes Overview to that file', scoped !== 'all' && calls.some((q) => q.includes('dataset_id=')), `select=${scoped} calls=${calls.slice(-3).join(',')}`);
} else check('"View only this file" button found', false, 'not rendered after opening notes');

// Admin card + role select.
await page.goto(`${base}/app/settings`, { waitUntil: 'networkidle' });
const ownRow = page.locator('tr', { hasText: 'demo@ferlance.test' });
check('admin card renders for admin email', await ownRow.count() > 0);
check('own role select is disabled', await ownRow.locator('select').isDisabled());

// Insights advice: tap a suggestion, the detail sheet opens with reasons and actions, Escape closes it.
await page.goto(`${base}/app/insights`, { waitUntil: 'networkidle' });
const firstAdvice = page.locator('#advice-list .advice-card').first();
check('advice cards render', (await firstAdvice.count()) > 0);
await firstAdvice.click();
const sheet = page.locator('dialog[open].advice-sheet');
check('tapping a suggestion opens the detail sheet', await sheet.isVisible());
check('sheet lists what to do', (await sheet.locator('.advice-actions li').count()) > 0);
await page.keyboard.press('Escape');
check('Escape closes the sheet', (await page.locator('dialog[open].advice-sheet').count()) === 0);

// Lance: leave mid-answer (3s mock), come back, answer is there.
await page.goto(`${base}/app/lance`, { waitUntil: 'networkidle' });
await page.locator('#lance-input').fill('Which product sells best?');
await page.locator('#lance-input').press('Enter');
await page.getByRole('link', { name: 'Products' }).click();
await page.waitForTimeout(4000);
await page.getByRole('link', { name: 'Ask Lance' }).click();
await page.locator('.view-lance h3', { hasText: 'Best seller' }).waitFor({ timeout: 8000 }).catch(() => {});
check('Lance answer lands after navigating away and back', await page.locator('.view-lance h3', { hasText: 'Best seller' }).count() === 1);
check('thread keeps the question', await page.locator('.message-user', { hasText: 'Which product sells best?' }).count() === 1);

check('no unexpected console/page errors', errors.length === 0, errors.join(' | '));
console.log(results.join('\n'));
await browser.close();
