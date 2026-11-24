// Records the guide videos shown on the landing page and in the app (Help & guides).
//
// usage: node record.mjs <base-url> <out-dir>
//   1. start a local server on an empty data folder (see tools/demo/README.md)
//   2. python tools/verify/seed.py <base-url>      (creates demo@ferlance.test with demo data)
//   3. node tools/demo/record.mjs <base-url> frontend/public/assets/demo
//
// Each scenario is a scripted walk through the real app on a phone-sized screen, with captions
// that say why, when and how. Frames come from Chrome's screencast (CDP) and are encoded to a
// small VP9 WebM with Playwright's bundled ffmpeg; a poster image is saved for each.

import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const [base, outDir] = process.argv.slice(2);
if (!base || !outDir) {
  console.error('usage: node record.mjs <base-url> <out-dir>');
  process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });
const SIZE = { width: 390, height: 844 };
const EMAIL = 'demo@ferlance.test';
const PASSWORD = 'demo-pass-123';
const FFMPEG = fs
  .readdirSync(path.join(os.homedir(), '.cache/ms-playwright'))
  .filter((name) => name.startsWith('ffmpeg-'))
  .map((name) => path.join(os.homedir(), '.cache/ms-playwright', name, 'ffmpeg-linux'))
  .find((file) => fs.existsSync(file));

const OVERLAY_CSS = `
  #demo-caption{position:fixed;left:12px;right:12px;top:10px;z-index:2147483647;pointer-events:none;
    background:rgba(15,15,17,.92);color:#f1f1f3;border-radius:14px;padding:12px 14px;font:500 15px/1.4 system-ui,sans-serif;
    box-shadow:0 10px 30px rgba(0,0,0,.35);transition:opacity .25s}
  #demo-caption b{display:block;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#93c5fd;margin-bottom:4px}
  #demo-card{position:fixed;inset:0;z-index:2147483647;display:grid;place-content:center;gap:14px;padding:32px;text-align:center;
    background:#0f0f11;color:#f1f1f3;font:500 17px/1.45 system-ui,sans-serif}
  #demo-card h1{font-size:28px;margin:0}
  #demo-card p{margin:0;color:#babac2}
  #demo-card .when{color:#93c5fd}
  #demo-tap{position:fixed;z-index:2147483646;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;
    background:rgba(147,197,253,.45);border:2px solid #93c5fd;pointer-events:none;transition:opacity .4s}
`;

async function overlays(page) {
  await page.addStyleTag({ content: OVERLAY_CSS });
}

async function card(page, title, lines, ms = 3200) {
  await page.evaluate(
    ({ title, lines }) => {
      document.getElementById('demo-card')?.remove();
      const el = document.createElement('div');
      el.id = 'demo-card';
      el.innerHTML = `<h1></h1>${lines.map((line, i) => `<p class="${i === 0 ? 'when' : ''}"></p>`).join('')}`;
      el.querySelector('h1').textContent = title;
      el.querySelectorAll('p').forEach((p, i) => (p.textContent = lines[i]));
      (document.querySelector('dialog[open]') || document.body).appendChild(el);
    },
    { title, lines },
  );
  await page.waitForTimeout(ms);
  await page.evaluate(() => document.getElementById('demo-card')?.remove());
}

async function say(page, label, text, ms = 2600) {
  await page.evaluate(
    ({ label, text }) => {
      // An open modal <dialog> sits in the top layer, above everything: put the caption inside it.
      const host = document.querySelector('dialog[open]') || document.body;
      let el = document.getElementById('demo-caption');
      if (!el || el.parentElement !== host) {
        el?.remove();
        el = document.createElement('div');
        el.id = 'demo-caption';
        host.appendChild(el);
      }
      el.innerHTML = '<b></b><span></span>';
      el.querySelector('b').textContent = label;
      el.querySelector('span').textContent = text;
    },
    { label, text },
  );
  await page.waitForTimeout(ms);
}

async function tap(page, locator) {
  const target = locator.first();
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  if (box) {
    await page.evaluate(({ x, y }) => {
      const dot = document.createElement('div');
      dot.id = 'demo-tap';
      dot.style.left = `${x}px`;
      dot.style.top = `${y}px`;
      (document.querySelector('dialog[open]') || document.body).appendChild(dot);
      setTimeout(() => dot.remove(), 700);
    }, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
    await page.waitForTimeout(350);
  }
  await target.click();
  await page.waitForTimeout(500);
}

async function type(page, locator, text) {
  const target = locator.first();
  await target.scrollIntoViewIfNeeded();
  await target.click();
  await target.pressSequentially(text, { delay: 45 });
  await page.waitForTimeout(250);
}

async function go(page, view) {
  await page.goto(`${base}/app/${view}`);
  await page.waitForLoadState('networkidle');
  await overlays(page);
  await page.waitForTimeout(600);
}

async function api(context, method, url, data) {
  const login = await context.request.post(`${base}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
  const token = (await login.json()).access_token;
  const me = await (await context.request.get(`${base}/api/auth/me`, { headers: { Authorization: `Bearer ${token}` } })).json();
  const response = await context.request.fetch(`${base}/api/businesses/${me.businesses[0].id}${url}`, { method, headers: { Authorization: `Bearer ${token}` }, ...data });
  return response.json();
}

const SCENARIOS = [
  {
    slug: 'start',
    title: 'Your first minute',
    async run(page) {
      await go(page, 'overview');
      await card(page, 'Your first minute', ['When: every morning, before you open the shop.', 'Why: see how the business is really doing, in one place.']);
      await say(page, 'Overview', 'Sales, profit and what changed since the last period, worked out from your own records.');
      await page.mouse.wheel(0, 500);
      await say(page, 'What to do next', 'Ferlance points out what is selling, what is slowing down and what to restock: in plain words.', 3000);
      await go(page, 'insights');
      await say(page, 'Insights', 'Tap any suggestion to see the reasons and the next step.');
      await tap(page, page.locator('.advice-card'));
      await page.waitForTimeout(1600);
      await page.keyboard.press('Escape');
      await go(page, 'data');
      await say(page, 'Bring your records in', 'Import a spreadsheet or paste your MoMo messages. Every row is checked; nothing is dropped silently.');
      await tap(page, page.getByRole('button', { name: 'Import data' }));
      await page.waitForTimeout(1500);
      await page.keyboard.press('Escape');
      await card(page, 'That is the daily loop', ['Bring records in, read the advice, act.', 'Next: the guides for credit, invoices, stock and your books.'], 2600);
    },
  },
  {
    slug: 'credit',
    title: 'Selling on credit',
    async run(page) {
      await go(page, 'debts');
      await card(page, 'Selling on credit', ['When: a customer takes goods now and pays later.', 'Why: no more lost notebook debts. Ferlance remembers and reminds.']);
      await say(page, 'Debt book', 'Everyone who owes you, and how late they are.');
      await tap(page, page.getByRole('button', { name: 'New credit sale' }));
      await type(page, page.getByLabel('Customer'), 'Akosua Mensah');
      await type(page, page.getByLabel('Amount'), '120');
      await type(page, page.getByLabel('Phone (for reminders)'), '0244123456');
      await type(page, page.getByLabel('Note (optional)'), '2 bags of rice');
      await say(page, 'Two taps', 'Name and amount are enough. It goes into your books too.', 1800);
      await tap(page, page.getByRole('button', { name: 'Record debt' }));
      await page.waitForTimeout(1200);
      await say(page, 'Remind, politely', 'Send a WhatsApp or SMS reminder from your own phone, with where to pay by MoMo.');
      await tap(page, page.getByRole('button', { name: 'Remind' }));
      await page.waitForTimeout(2200);
      await say(page, 'When they pay', 'Record the payment, or let Ferlance match it to their MoMo message.', 2800);
      await card(page, 'Never lose a debt again', ['Record it when they take the goods.', 'Remind on WhatsApp. Match the MoMo payment.'], 2600);
    },
  },
  {
    slug: 'invoices',
    title: 'Invoices and receipts',
    async run(page) {
      await go(page, 'invoices');
      await card(page, 'Invoices and receipts', ['When: a customer or company asks for an invoice, a quote or a receipt.', 'Why: a proper PDF in cedis, with your details, in a minute.']);
      await tap(page, page.getByRole('button', { name: 'New invoice' }));
      await type(page, page.getByLabel('Customer'), 'Kofi Stores');
      await page.getByLabel('Item').first().selectOption({ index: 1 });
      await page.waitForTimeout(500);
      const qty = page.getByLabel('Qty').first();
      await qty.fill('');
      await type(page, qty, '2');
      await type(page, page.getByLabel('Price each'), '95');
      await say(page, 'Stock comes off', 'Pick an item from your stock and it leaves stock when the invoice is made.', 2400);
      await tap(page, page.getByRole('button', { name: 'Create invoice' }));
      await page.waitForTimeout(1500);
      await say(page, 'Share it', '"Share PDF" opens WhatsApp on your phone with the invoice attached.', 2800);
      await say(page, 'Getting paid', 'An unpaid invoice waits in the debt book until it is paid. A receipt is for a sale paid on the spot.', 3000);
      await card(page, 'Look professional, get paid', ['Invoice, quote or receipt: numbered, never skipped.', 'Turn a quote into an invoice in one tap.'], 2600);
    },
  },
  {
    slug: 'notebook',
    title: 'From your exercise book',
    async run(page) {
      await go(page, 'notebook');
      await card(page, 'From your exercise book', ['When: you keep sales, debtors or spending in a book.', 'Why: your paper records become real numbers, without retyping everything.']);
      await tap(page, page.getByRole('button', { name: 'Add a page' }));
      await say(page, 'Photo or type', 'Take a photo of the page and Ferlance reads it. Or type the lines: free, no AI.', 2600);
      await tap(page, page.getByRole('button', { name: 'Type it' }));
      await type(page, page.locator('#page-text'), 'Rice 5kg 2 190\nMilo 47.50\nSugar 1kg 3 36');
      await tap(page, page.getByRole('button', { name: 'Read the lines' }));
      await page.waitForTimeout(900);
      await say(page, 'Check every line', 'Fix any number, untick what should not be added. Nothing is saved until you press Add.', 3000);
      await tap(page, page.getByRole('button', { name: 'Add', exact: true }));
      await page.waitForTimeout(1500);
      await card(page, 'Your book, counted', ['Sales pages become sales. Debtors pages go to the debt book.', 'Spending pages are sorted into rent, transport and more.'], 2600);
    },
  },
  {
    slug: 'stock',
    title: 'Keeping stock right',
    async run(page) {
      await go(page, 'inventory');
      await card(page, 'Keeping stock right', ['When: goods arrive, go out, or you count the shelves.', 'Why: know what to restock before you run out, and spot losses.']);
      await say(page, 'Your products', 'Every product, what is on hand, and what needs reordering.', 2400);
      await tap(page, page.getByRole('button', { name: 'Stock in / out' }));
      await type(page, page.locator('#movement-quantity'), '10');
      await type(page, page.locator('#movement-note'), 'Delivery from supplier');
      await tap(page, page.getByRole('button', { name: 'Record movement' }));
      await page.waitForTimeout(1200);
      await say(page, 'Supplier invoices', '"Scan invoice" reads a delivery note photo into stock lines you check first.', 2800);
      await say(page, 'Count the shelves', '"Stocktake" compares your count with the records, and shows the differences.', 2800);
      await card(page, 'Stock you can trust', ['Every movement is kept, like a ledger.', 'Low stock is flagged before it runs out.'], 2600);
    },
  },
  {
    slug: 'books',
    title: 'Your books and MoMo statements',
    async run(page) {
      await go(page, 'books');
      await card(page, 'Your books, kept for you', ['When: month end, or when an accountant or lender asks.', 'Why: real profit and loss, without doing bookkeeping.']);
      await say(page, 'Books', 'Every import, MoMo message, invoice and stock movement goes into proper books automatically.', 3000);
      await page.mouse.wheel(0, 700);
      await say(page, 'Profit and what you own', 'Profit and loss, what you own and owe, and money in and out: in plain words.', 2800);
      await go(page, 'reconcile');
      await say(page, 'Check against MoMo and the bank', 'Import your MoMo or bank statement. Ferlance shows what the books already have and explains every cedi of difference.', 3600);
      await page.mouse.wheel(0, 500);
      await page.waitForTimeout(1500);
      await card(page, 'Books an accountant can use', ['Download the year-end pack from Planning.', 'Your accountant can sign in with their own account.'], 2600);
    },
  },
  {
    slug: 'loan',
    title: 'Getting ready for a loan',
    async run(page) {
      await go(page, 'credit');
      await card(page, 'Getting ready for a loan', ['When: you want a loan from a bank or microfinance.', 'Why: show your track record, with proof, in one link.']);
      await say(page, 'Readiness score', 'How complete and well-evidenced your records are. Each part says how to raise it.', 3000);
      await page.mouse.wheel(0, 600);
      await say(page, 'What the lender sees', 'Sales, profit and how much of it is backed by MoMo and bank statements.', 2600);
      await page.mouse.wheel(0, 900);
      await tap(page, page.getByText('I agree to share'));
      await tap(page, page.getByRole('button', { name: 'Create link' }));
      await page.waitForTimeout(1200);
      await say(page, 'You stay in control', 'The lender sees a copy of the summary, never your records. Withdraw the link any time.', 3000);
      await card(page, 'Records that open doors', ['Keep records for a few months, import your statements.', 'Then share one link with the lender.'], 2600);
    },
  },
];

/** Record a page with Chrome's screencast; returns stop(), which resolves to the timed frames. */
async function screencast(page) {
  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  cdp.on('Page.screencastFrame', (event) => {
    frames.push({ data: Buffer.from(event.data, 'base64'), time: event.metadata.timestamp });
    cdp.send('Page.screencastFrameAck', { sessionId: event.sessionId }).catch(() => undefined);
  });
  await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 85, maxWidth: SIZE.width, maxHeight: SIZE.height, everyNthFrame: 1 });
  return async () => {
    await cdp.send('Page.stopScreencast').catch(() => undefined);
    frames.push({ ...frames[frames.length - 1], time: Date.now() / 1000 });
    return frames;
  };
}

/** Write frames at a steady 25 fps (holding each until the next arrives) into a VP9 WebM. */
function encode(frames, target, fps = 25) {
  return new Promise((resolve, reject) => {
    const ffmpeg = spawn(FFMPEG, ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-c:v', 'mjpeg', '-r', String(fps), '-i', 'pipe:0',
      '-vf', `scale=${SIZE.width}:${SIZE.height}:force_original_aspect_ratio=decrease,pad=${SIZE.width}:${SIZE.height}:(ow-iw)/2:(oh-ih)/2:color=white`,
      '-c:v', 'libvpx-vp9', '-b:v', '260k', '-row-mt', '1', '-deadline', 'good', '-cpu-used', '4', '-pix_fmt', 'yuv420p', '-an', target]);
    let errors = '';
    ffmpeg.stderr.on('data', (chunk) => (errors += chunk));
    ffmpeg.on('close', (code) => (code === 0 ? resolve() : reject(new Error(errors || `ffmpeg exited ${code}`))));
    ffmpeg.stdin.on('error', () => undefined);
    const start = frames[0].time;
    const end = frames[frames.length - 1].time;
    let index = 0;
    for (let t = start; t <= end; t += 1 / fps) {
      while (index + 1 < frames.length && frames[index + 1].time <= t) index += 1;
      ffmpeg.stdin.write(frames[index].data);
    }
    ffmpeg.stdin.end();
  });
}

async function main() {
  const browser = await chromium.launch();
  const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
  const raw = path.join(path.resolve(outDir), '.raw');
  fs.mkdirSync(raw, { recursive: true });
  // Fixtures some guides rely on: a MoMo statement for reconciliation.
  const setup = await browser.newContext();
  const statement = 'TRANSACTION DATE,FROM NAME,TRANS. TYPE,AMOUNT,FEES,BAL BEFORE,BAL AFTER,TRANS ID\n' +
    '15/11/2026 09:12,Kojo Mensah,PAYMENT RECEIVED,150.00,0.00,1000.00,1150.00,DEMO-1\n16/11/2026 10:00,Agent 112,CASH OUT,200.00,2.00,1150.00,948.00,DEMO-2\n';
  const preview = await api(setup, 'POST', '/statements/preview', { multipart: { file: { name: 'momo.csv', mimeType: 'text/csv', buffer: Buffer.from(statement) } } });
  await api(setup, 'POST', '/statements', { multipart: { file: { name: 'momo.csv', mimeType: 'text/csv', buffer: Buffer.from(statement) }, account: 'momo_mtn', header_row: String(preview.header_row), mapping: JSON.stringify(preview.mapping) } });
  await setup.close();

  for (const scenario of SCENARIOS) {
    if (only && !only.includes(scenario.slug)) continue;
    const context = await browser.newContext({ viewport: SIZE, deviceScaleFactor: 1, colorScheme: 'light' });
    await context.request.post(`${base}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
    const page = await context.newPage();
    await page.goto(`${base}/app/overview`);
    await page.waitForLoadState('networkidle');
    const stop = await screencast(page);
    try {
      await scenario.run(page);
      await page.screenshot({ path: path.join(outDir, `${scenario.slug}.jpg`), type: 'jpeg', quality: 70 });
    } catch (error) {
      console.error(`${scenario.slug}: ${error.message}`);
      await page.screenshot({ path: path.join(raw, `${scenario.slug}-error.png`) });
    }
    const frames = await stop();
    await context.close();
    const target = path.join(outDir, `${scenario.slug}.webm`);
    await encode(frames, target);
    console.log(`${scenario.slug}: ${(fs.statSync(target).size / 1024).toFixed(0)} KB`);
  }
  await browser.close();
  fs.rmSync(raw, { recursive: true, force: true });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
