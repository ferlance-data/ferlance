# Changelog

All notable changes to Ferlance are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html). The version is kept in `frontend/package.json` and `backend/main.py`, which must match. Each release is tagged `vX.Y.Z` on its merge commit to `main`. The release plan is in `docs/PRD.md`.

## [Unreleased]

## [1.22.0] - 2026-11-25

The phone app, and guide videos that play on every phone.

### Added
- **Mobile app** (`mobile/`, Expo SDK 58) for the everyday jobs:
  - **Today:** sales, costs and the change from last month, plus what to do next.
  - **Debts:** new credit sales, recording payments, and WhatsApp or SMS reminders.
  - **Record:** MoMo messages pasted in, or a notebook page photographed or typed, with every line checked before it is added.
  - **Ask Lance.**
  - **Guides:** they open on the first sign-in.

  It shares the guide text, money formatting, reminder wording and API types with the website, straight from `frontend/src`. It runs free in Expo Go; see `mobile/README.md`.
- **Phone sign-in** at `/api/auth/mobile/login`, `/refresh` and `/logout`. The refresh token travels in the JSON body and is kept in the phone's secure store. It rotates on every use, with the same one-shot grace for a lost response. Phone sessions have their own `mobile` scope, so a website cookie can't be refreshed there and a phone token can't be used as a cookie. Disabling an account ends phone sessions too.

### Changed
- The guide videos are now H.264 MP4 instead of VP9 WebM. They play on every phone, older iPhones included, and they're a quarter of the size: about 1.6 MB for all seven, down from 5.8 MB.
- All seven videos were re-recorded, fixing three problems:
  - The phone number in the credit video was typed twice.
  - The welcome tour no longer covers the page.
  - The AI explanation panel is hidden, because the recording server has no AI key.

## [1.21.0] - 2026-11-25

Guides: short videos of the real app showing when, why and how to use each feature.

### Added
- **Help & guides** (`/app/help`, in the menu above Settings). There are seven guides: your first minute, selling on credit, invoices and receipts, from your exercise book, keeping stock right, your books and MoMo statements, and getting ready for a loan. Each has a short silent video of the real app, when to use the feature, why it helps, the steps, and a link to the page.
- **Welcome tour.** On the first visit to the workspace a modal plays the "first minute" video, with links to all the guides or "Not now". It shows once per browser and is skipped if storage is blocked.
- **How it works** on the landing page. Scenario tabs show each video in a phone frame next to its when, why and steps. The section has a link in the menu and the footer, and a "Watch how it works" button in the hero.
- `tools/demo/record.mjs` re-records the videos from a seeded local server: a Playwright script with captions, a Chrome screencast and VP9 WebM output, about 5.8 MB for all seven. See `tools/demo/README.md`.

## [1.20.0] - 2026-11-25

Create in a modal, a grouped menu, and dashboards that agree with the books.

### Changed
- **Create in a modal.** Each page now shows what already exists first; a **New…** button opens the form in a modal (a bottom sheet on phones). Escape closes it, and a modal closes only when saving succeeds. This applies to:
  - invoices, quotes and receipts, and "Your details"
  - debt-book credit, and where customers pay
  - notebook pages, which now also list the pages already added
  - inventory (add product, stock in or out, scan invoice, stocktake)
  - financial-position balances
  - data imports (the modal stays open to show the result)
  - statement imports
  - staff
  - regular payments and budgets
  - manual journals and the chart of accounts
- **The menu is grouped:** Analyse; Selling and stock; Money and books. Within each group the most-used pages come first.
- **Dashboards count MoMo payments you make as costs, not revenue,** matching the books. The "Books and dashboards compared" card no longer needs to explain the difference.

### Added
- `GET /pages`: the notebook pages added, newest first.

## [1.19.0] - 2026-11-24

Planning extras (PRD §9, G9).

### Added
- **Planning page, Recurring tab:** regular payments such as rent and subscriptions. They never post on their own. Each month shows as **due**, and you confirm the amount actually paid, or skip that month. Confirmed months post Expense / paid-from account, and Undo reverses them. Payments can't be confirmed before their date.
- **Budgets tab:** a budget per month for sales, cost of goods sold and each kind of expense, against the actual figures from the books, with the percentage used. Overspends are flagged.
- **Downloads tab:**
  - **Year-end pack** (owner and accountant): a zip of CSVs with the trial balance, profit and loss, balance sheet, the year's journal, debtors, creditors and stock valuation, plus a README listing the books start date, the period lock and any unchecked tax rules.
  - **Download all my data** (owner): every kind of record as CSV.
  - Spreadsheet formulas are neutralised in both.

### Not yet
- **Branches** (several shops under one business) touch nearly every table, so they're planned as their own release.

## [1.18.0] - 2026-11-24

Credit-readiness report (PRD §9, G7).

### Added
- **Credit report page:** the last 12 months as a lender would see them, including sales and profit by month, net margin, months with sales, what customers owe and how late, and stock turnover. Every figure comes from the books.
- **Evidence levels:** sales are split into those matched to an imported MoMo or bank statement (strongest), those from MoMo messages, and self-reported. Lenders see the split.
- **Readiness score** out of 100, made of six parts: track record, evidence, profitability, steady sales, collecting debts and complete books. Each part shows its points, the reason, and what would raise it. It's not a credit decision.
- **Share with a lender** (owner only, after ticking consent): creates a link to a **frozen copy**, not live access, valid for 7, 14 or 30 days.
  - **The lender's page** is plain, printable HTML with no scripts. Every value is escaped, the page has a strict content security policy, and search engines are told not to index it.
  - **What the lender sees** is the summary only: no line items or customer names.
  - **Verification:** a code is shown to both the owner and the lender.
  - **Control:** every view is logged with its time, and you can withdraw the link at any time.

### Not yet
- Lender partnerships and a revenue model are business decisions (PRD §9.6).
- A Data Protection Act review of sharing is still to be done.

## [1.17.0] - 2026-11-24

Ghana tax and payroll basics (PRD §9, G6). **Every rate needs an accountant's check.**

### Added
- **Dated tax rules (`backend/tax.py`), taken from GRA and SSNIT pages in November 2026.** Each rule records its start and end dates, its sources and its notes, and every figure Ferlance calculates names the rule it used:
  - **VAT:** from 1 January 2026, VAT 15%, NHIL 2.5% and GETFund 2.5% on the same price (20% in total, COVID-19 levy repealed). Before 2026, the old compound regime (about 21.9%).
  - **PAYE** for residents: the monthly bands from 1 September 2026 (first GH₵588 free, up to 35% above GH₵50,000), and the earlier bands, partly from secondary sources.
  - **SSNIT:** employee 5.5% and employer 13% of basic salary, capped at GH₵69,000 a month. The Tier 1 and Tier 2 split is unconfirmed, so the total is booked to one account.
  - **Withholding tax** for residents: goods 3%, works 5%, services 7.5%; non-residents 20%.
- **Accountant checks:** each business sees "Needs accountant check" on every rule until its owner or accountant confirms it (stored with who and when). Summaries and payrolls warn when they use unchecked rules.
- **VAT invoices:** a "Charge VAT and levies" option. The tax is added on top of the lines, booked to "VAT and levies payable" rather than to sales, and printed on a "TAX INVOICE" PDF with the subtotal and each levy.
- **Withholding tax on supplier payments:** the supplier's debt goes down by the full amount, the supplier receives the rest, and the tax kept back is owed to GRA.
- **Payroll for small teams:**
  - Staff with a monthly basic salary and allowances.
  - Monthly runs calculate SSNIT, then PAYE on gross pay minus the employee's SSNIT, then net pay.
  - A run stays a draft until you post it from your chosen account. Wages and employer SSNIT become costs, and PAYE and both SSNIT shares are owed. You can void a run and run the month again.
  - A PDF payslip per employee.
  - Salaries are visible to owners and accountants only.
- **What's owed for a period:** VAT and levies charged, withholding tax kept back, and PAYE and SSNIT by month, to help you file. Ferlance does not file with GRA or SSNIT.

### Not yet
- Input VAT on purchases isn't captured, so VAT is output only.
- GRA E-VAT isn't integrated.
- Non-resident PAYE, benefits in kind, bonuses and reliefs aren't handled.
- The SSNIT tier split needs confirming.

## [1.16.0] - 2026-11-24

MoMo and bank reconciliation (PRD §9, G5).

### Added
- **Reconcile page.** Import a statement as CSV or XLSX for MTN Mobile Money, Telecel Cash, AT Money or the bank:
  - Title rows above the column names are skipped.
  - Columns are recognised by common names (transaction ID, fees, balance before and after, money in and out). Otherwise you choose which column is which.
  - Dates are read day/month first, as written in Ghana, unless the file is clearly month/day.
  - The file is checked against itself: each balance must follow from the one before, so a missing page or reversed order is flagged.
  - Re-importing an overlapping month adds nothing.
- **Importing never adds to the books by itself.** Each line is matched against what the books already hold: SMS imports and sales by payment method, debt payments and receipts, manual journals, and other statements' bookings. It matches by transaction ID, then by exact amount within ±2 days, one to one, and only suggests when several fit. Matching is worked out on every visit, so leaving an import out later simply unmatches its lines.
- **Add the rest to the books** from a fixed list:
  - a sale already imported whose payment method was unknown (clears "Sales receipts to allocate")
  - a payment already recorded
  - a new sale, spending by kind, or other income
  - owner money in or out
  - a transfer between your own accounts (it matches across two statements)
  - a debt payment, which goes into the debt book

  Fees and levies are booked as MoMo and bank charges when you say so. Every booking can be undone.
- **Every cedi explained:** statement closing balance against the books on the same day. The difference is broken down into the opening gap, lines not in the books, fees not booked, and book entries with no statement line. "Unexplained" is 0 in tests.
- **Permissions:** importing and booking need `manage_books` (owner and accountant); everyone can view.

### Not yet
- Real MTN, Telecel, AT and bank export layouts haven't been seen; the tests use clearly labelled synthetic files, and the column-mapping step covers what isn't recognised. A redacted real export of each would let us confirm them.
- PDF statements aren't supported yet (CSV or XLSX only).
- E-Levy and other levies aren't calculated; they're booked as they appear on the statement.

## [1.15.0] - 2026-11-24

Notebook pages (PRD §9, G4): the exercise book, read into the records.

### Added
- **Notebook pages:** photograph a page, or type it in for free with no AI. The AI decides whether it's a **sales**, **debts** or **expenses** page (you can change it), reads the date and every written row, and flags doubtful lines. Nothing is added until each line is checked: tick, edit or untick it, then press **Add**. The photo is shrunk on the phone, which strips its location, and is never stored.
- **Where the lines go:**
  - A sales page becomes a normal import, on the dashboards and in the books.
  - An expenses page becomes spending, sorted into rent, transport, airtime and so on.
  - A debts page creates one debt-book entry per customer.
- **Safeguards:**
  - A page can be added only once.
  - The exact same lines added again carry a warning.
  - Future dates are refused.
  - Each photo uses one AI call from the daily cap, refunded if the read fails.
- **Accuracy on a live run** (gemini-2.5-flash-lite, a synthetic page in a script font): 24 of 24 fields right in 3.5 s. It read "12/11/2026" as day/month and skipped the total line.

### Not yet
- Accuracy on real handwriting needs a set of real pages, used with the owner's consent; the script font is only a stand-in.
- Stock-count pages still go through **Scan invoice** on Inventory.

## [1.14.0] - 2026-11-24

Invoices, quotes and receipts (PRD §9, G3).

### Added
- **Invoices page:** create an invoice, quote or receipt in cedis from stock products or free-text lines, with a live total.
- **Numbering:** INV-, QUO- and RCT- numbers per business, with no gaps. A voided document keeps its number.
- **Share PDF:** one-page A4 PDFs, about 25 KB, with your address, phone, TIN, footer and the MoMo pay-to line. They print ₵ and Ghanaian letters (ɛ, ɔ, ŋ) correctly using a bundled DejaVu font. On phones the PDF opens the share sheet (WhatsApp); elsewhere it downloads.
- **In the books:**
  - An invoice is a debt-book entry, so part-payments, overdue status, reminders and the ledger all follow.
  - A receipt is a sale paid on the spot, to cash, MoMo or bank.
  - A quote posts nothing until you click **Make invoice**.
  - Stock lines leave stock, and you can't sell more than you have.
  - Voiding voids the payments, returns the stock and reverses cost of goods sold.

### Not yet
- GRA E-VAT: whether to integrate with GRA or only produce compliant invoices is still open (PRD §9.6), and needs GRA's documentation and an accountant.

## [1.13.0] - 2026-11-24

A separate admin suite, and a calmer dark theme.

### Added
- **Admin console at `/admin`,** a separate app with its own sign-in (later its own subdomain). It's split from the workspace at every level:
  - admin tokens use their own type
  - a separate refresh cookie (`ferlance_admin_refresh` on `/api/admin/auth`)
  - refresh sessions scoped to `admin`

  A workspace token never opens the admin API, and an admin token never opens a business. `/app/admin` redirects to `/admin`, and the workspace menu no longer shows Admin.
- **Admin accounts** (`POST /api/admin/auth/signup`) can be created only for emails in `FERLANCE_ADMIN_EMAILS`, with passwords of 12+ characters; each one is logged in the admin log. A listed person who already runs a business can instead sign in at `/admin` with that account. A pure admin account is pointed to `/admin` if it tries the workspace sign-in.

### Changed
- **Dark theme:** neutral graphite instead of green-tinted ink, with a near-black page, grey surfaces and off-white text (about 15:1 contrast; secondary text over 7:1). Primary buttons are light, and AI touches use a soft blue.
- **Larger text** in both themes: body 16 px (was 15), small text 14 px (was 13).

## [1.12.0] - 2026-11-22

Deployment on a single AWS server, and a nightly backup that can be restored.

### Added
- Deployment: a `Dockerfile` (it builds the frontend with Node, then serves it from Python) and a `.dockerignore` that keeps `.env` and local data out of the image.
- `deploy/aws/user-data.sh`: a one-paste setup for an EC2 server. It adds swap, installs Docker and Caddy, builds the app, and serves free HTTPS at `<ip>.sslip.io`. It also installs `ferlance-update`, `ferlance-start` and `ferlance-restore`, and uses an instance role instead of stored AWS keys.
- `render.yaml`: a paid Render alternative with a persistent disk.
- `docs/DEPLOY.md`: which host to choose and why (including the AWS free-plan time limit), a click-by-click AWS walkthrough, and how to restore.
- **Nightly restorable backup:** with each daily export, a consistent SQLite snapshot and the uploaded and processed files go to `exports/_backup/dt=<day>/`, with a checksummed manifest written last. Admin → Data export shows the last backup. `ferlance-restore <day>` checks the checksums and swaps the data in, keeping the old copy.

### Security
- In production (`FERLANCE_COOKIE_SECURE=true`), the server now refuses to start with the development secret key or one shorter than 32 characters.

## [1.11.0] - 2026-11-22

The debt book (PRD §9, G2): the notebook by the till, made quick.

### Added
- **Debt book page.** Recording a credit sale or a supplier credit takes a name and an amount; the phone, a note and a pay-by date are optional. Names are remembered, so "Akosua" and "akosua" are one person.
- **Part-payments** by cash, MTN MoMo, Telecel Cash, AT Money or bank. Paying more than is owed is refused.
- **Voids instead of deletes.** Voiding a debt also voids its payments, the history is kept, and the ledger entries are reversed.
- **Ageing:** not due yet, then 1–30, 31–60, 61–90 and over 90 days late. With no pay-by date, a debt counts as late 30 days after it started.
- **Reminders** open the owner's own WhatsApp or SMS with the balance and the "where to pay" MoMo details filled in. Nothing is sent automatically. Messages are in English, with a **draft** Twi version that a native speaker still needs to check.
- **MoMo matching.** Incoming MoMo messages that may pay an open debt are suggested by matching phone number or name; the owner confirms each one. A matched message settles the debt and is not counted as a second sale. If its import is later left out, the payment goes on hold.
- **In the books:**
  - A new credit sale posts Receivables / Sales.
  - A sale already in an import clears "Sales receipts to allocate" instead.
  - Supplier credit for recorded stock clears "Payments to allocate"; for anything else it is booked as an expense.
  - Payments move money in or out of cash, MoMo or bank.
  - Debts dated before the books start only set the opening receivable or payable.
  - The debt book's totals equal the ledger's receivables and payables (tested).
- **Opening balances** propose only the part of a receivables or payables balance that isn't already in the debt book.

### Not yet
- The Twi reminder needs a native speaker's review.
- Offline entry waits for the mobile app (#9, deferred).

## [1.10.0] - 2026-11-22

The quiet ledger (PRD §9, G1): real double-entry books, kept automatically from what the business already records. They're shown beside the existing reports; the dashboards don't change yet.

### Added
- **Books page.** Profit and loss, "what the business owns and owes" (balance sheet) and "money in and out" (cash flow) in plain words, for any dates. A "Books and dashboards compared" card names every difference from the dashboards.
- **The ledger.**
  - Amounts are kept in pesewas, per currency.
  - SQLite triggers refuse any entry that doesn't balance, and any change or delete of a posted entry.
  - Corrections are reversing entries.
- **A Ghana chart of accounts:** cash, MTN Mobile Money, Telecel Cash, AT Money, bank, receivables, stock, payables, VAT and levies, loans, owner capital and drawings, sales, cost of goods sold, and common costs (rent, transport, data and airtime, electricity and water, wages, MoMo and bank charges).
- **Posting rules,** each with a test:
  - Sales lines go to cash, a MoMo wallet or the bank by their payment method. If the method is unknown, they go to "Sales receipts to allocate".
  - MoMo payments made are booked as spending.
  - Cost-only lines are booked as expenses.
  - Stock purchases, sales, counts and opening stock are valued once and keep that value.
  - A file posted to stock takes cost of goods sold from stock, line by line, so nothing is counted twice.
  - Leaving a file out reverses its entries.
- **"Where you stand on day one."** The owner picks the day the books start and confirms opening balances suggested from Financial position. Sales before that day stay on the dashboards only, and opening stock comes from the stock records, so nothing is counted twice.
- **For your accountant:**
  - the journal with debits and credits
  - manual journals
  - a period lock (changes are logged with who made them, and late corrections land on the first open day)
  - the chart of accounts (add and rename)
  - a CSV journal export, with spreadsheet formulas neutralised
- **New permission, `manage_books`,** for owners and accountants. Managers can read the books but not post to them.

### Not yet
- The CSV export is a plain journal. Importing it into QuickBooks Online or Xero has not been checked against their templates.
- The chart of accounts and posting rules need an accountant's sign-off before v2.0.0 makes the ledger the source of truth.
- The dashboards still count MoMo payments made as revenue. The books don't, and the comparison card names the difference.

### Added
- `docs/PRD.md` §9 drafts Phase 2, "Ghana-first books" (v2.x). It covers:
  - a quiet double-entry ledger
  - a debt book
  - WhatsApp invoices
  - reading exercise-book pages
  - MoMo and bank reconciliation
  - Ghana tax and payroll basics
  - a credit-readiness report
  - WhatsApp and local languages

  It is benchmarked against QuickBooks, Xero and Wave.

## [1.9.0] - 2026-11-22

Daily data export to AWS S3 (PRD #3).

### Added
- **Daily per-business export.** Each business's sales records, imports, products and stock ledger go to S3 as Parquet once a day, under `exports/business_id=<id>/dt=<date>/`, which Athena and Glue can query directly. It is off until `FERLANCE_EXPORT_BUCKET` (or `FERLANCE_EXPORT_DIR` for a local folder) is set.
- The exporter only needs `s3:PutObject` on the export prefix. Objects are SSE-S3 encrypted, and credentials come from the standard AWS environment variables.
- `manifest.json` is written last in each day's folder, with the run id and every file's row count and size. A folder with no manifest, or one that doesn't match its files, holds an interrupted run.
- **Admin → Data export** shows where exports go and each business's latest run, with errors and any setup problem. "Export now" starts a background re-run of today's export (only one at a time) and is recorded in the admin log.
- A file whose processed records can't be read is left out of that day's sales export and named, instead of failing the business's whole export.
- `export_runs` records every run. A failed business is retried at the next check (every 15 minutes), up to 3 times a day.

### Changed
- New dependencies: `pyarrow` and `boto3`. Both load only when an export runs, so the app uses no extra memory when exports are off.

## [1.8.0] - 2026-11-22

Better retrieval for Ask Lance (PRD §5.6, #8), measured before it was changed.

### Added
- `tools/eval/rag_eval.py`: a repeatable retrieval evaluation (10 questions over about 600 records), scored on precision@10, hit@10 and p95 latency. `--vectors` runs the hybrid-embeddings experiment.

### Changed
- **Ask Lance now finds the right records more often.** Precision@10 went from 0.78 to 0.90, still at about 4 ms. The new index:
  - holds record values only (field names like "product" used to match every row)
  - drops common question words
  - respects the date range in scope
  - matches word forms ("payments" finds "payment")
- The old index is cleared on upgrade and rebuilt automatically, file by file, on the next question.

### Not adopted
- **A vector or hybrid index.** Embeddings through OpenRouter scored 0.91, about the same, but added about 3 s per question and 22 s of indexing per 600 rows. See the PRD for the numbers.

## [1.7.0] - 2026-11-22

Inventory ↔ sales sync (PRD §5.5, #2).

### Added
- **Inventory → Link sales to stock.** Every product name in your sales files is listed with the units sold. For each one, choose the stock product it is, or mark it "Not a stock item".
  - Names already matching a product exactly are recognised automatically.
  - Similar names are suggested but never chosen for you.
  - This handles each shop's own spelling ("RICE BAG 5KG" is "Rice 5kg").
- **Data imports → Post to stock.** Takes a file's linked sales out of stock as sale movements. It is your choice per file, and sales files still never change stock on their own.
  - **Once only:** a file can be posted once.
  - **Never below zero:** if posting would take a product below zero, nothing is posted and you're told what is short, for example "Cooking oil 1L (short 3)", so you can record the purchase or a stocktake first.
  - **Skipped lines are reported:** lines with unlinked names, ignored names or no quantity.
- **Leaving a posted file out of analysis reverses its stock movements** with equal and opposite adjustments, so the ledger stays complete. It can be posted again later.
- **Last stocktake differences:** per product, what the shelf count found against the records, with its value.
- **Advice uses the links:** stock levels, restock and slow-stock advice follow linked names, and a product sold under several names is counted once.

### Fixed
- The stock movements list labelled every non-manual movement "Stocktake import". It now names scanned invoices, sales files and reversals.

## [1.6.0] - 2026-11-22

Scan invoices into stock (PRD §5.4, #1).

### Added
- **Inventory → Scan invoice.** Take or choose a photo (or a PDF) of a supplier invoice, delivery note or stock list. Ferlance reads the product lines into a draft:
  - name, quantity and unit cost
  - SKU and expiry, where printed
- **Type the lines** instead (for example "Rice 5kg, 10, 70"): read on the server without AI, and free.
- **Review before anything changes.** For each line, add it to an existing product, create a new one, or skip it with a reason.
  - Exact SKU or name matches are pre-filled. A similar name is only suggested ("Did you mean…?"), never pre-selected.
  - Lines where quantity × unit price doesn't match the printed total, or with no quantity, are flagged "Check this line".
- **"Add to stock" applies the whole draft in one transaction.** One bad line changes nothing, and a second tap is refused, so purchases are never doubled. Skipped lines are kept with their reason. Expiry dates go into the movement note.
- **Photos are shrunk on the phone to about 1600 px before upload.** That saves data and strips location data. The photo is read by the AI provider and not stored.

### Notes
- **Provider.** The default is `google/gemini-2.5-flash-lite` on the existing OpenRouter key: about $0.0003 a page and about 2.5 s. Change it with `FERLANCE_OCR_MODEL`. Each scan counts against the daily AI cap, and failed scans are refunded.
- **Measured accuracy** on generated pharmacy invoices (clean, tilted 4°, blurred): 18 of 18 fields read correctly on each, and the delivery fee was correctly left out.
- **PDFs** need at least $0.50 of OpenRouter credit (a provider rule). Below that, the app asks for a photo instead.
- **Stock and expiry.** Inventory has no expiry tracking yet, so expiry is kept in the movement note only.

## [1.5.0] - 2026-11-22

Onboarding and the admin console (PRD §5.3, 4.1 and 4.3–4.4).

### Added
- **First-run import on Overview.** Until the first file is in, the setup guide lets a new owner pick the currency and either upload a file or paste MoMo alerts there and then, without going to another page.
- **Admin page** (`/app/admin`), visible only to platform administrators:
  - setup progress across all businesses: imported, stock, balances, asked Lance, invited a teammate (counts only)
  - users, with search, platform role and disable/enable
  - businesses, with search and counts of people, files, products, balances and chats (never their records)
  - a log of every admin change
- **Disabling an account** signs the person out everywhere at once: refresh sessions are revoked and access tokens are refused on the next request. Login is refused until the account is re-enabled. Admins can't disable themselves, the last admin, or admins listed in `FERLANCE_ADMIN_EMAILS`.

### Changed
- The admin card moved from Settings to the Admin page.
- Role changes are recorded in the audit log, and the last administrator can't be demoted.

## [1.4.0] - 2026-11-22

Team access (PRD §5.3, 4.2): owners give managers and accountants their own sign-in.

### Added
- Business roles: **owner**, **manager** and **accountant**. The server enforces them on every business route through declared permissions.
  - Accountants can see everything, record balances and use AI, but can't change sales or stock.
  - Managers can do everything except manage the team or rename the business.
- Invite links from Settings → Team. They are single-use, expire after 7 days and can be cancelled, and are shared by copy and paste (for example on WhatsApp).
  - New people sign up through the link without creating a business. Existing users sign in through it.
  - The token is removed from the address bar once it has been read.
- The owner can change a member's role or remove them, and it takes effect on their next request.
- A business switcher in the sidebar for people who belong to more than one business.
- A daily cap on uncached AI calls per business (`FERLANCE_AI_DAILY_LIMIT`, default 100), shared by Ask Lance and the explanations.
- The Data and Inventory pages show a clear read-only notice instead of forms the user's role can't use.

### Changed
- Renaming the business moved to `PATCH /api/businesses/{id}` (owner only). `PATCH /api/auth/profile` now updates only your own name.
- `/api/auth/me` also returns `businesses`, with your role in each.
- Refresh tokens: a token rotated in the last 60 seconds can be used once more, if its replacement was never used. This stops users on flaky connections being signed out when a refresh response is lost. Signed-out tokens never get this grace.

### Fixed
- The landing page's privacy copy still described the removed Brave web research.

## [1.3.0] - 2026-11-22

Analytics visuals (PRD §5.2, #6): circular, animated and responsive, accessible, and with no chart library.

### Added
- Donut charts:
  - "Where your revenue comes from", on Overview and Products
  - "Where your profit comes from", on Products, when costs are complete
  - Each shows the top five products plus Other. Tap or hover a slice to see its share.
- "How complete your records are" on Overview: progress rings for product, cost, quantity and customer coverage, each saying what it unlocks. `/analytics` now returns `coverage`.
- A validated categorical chart palette (`--chart-cat-1`…`5`, `--chart-other`) for both themes.
- Bar chart: tooltips work on touch, and a "Show as table" view is added.

### Changed
- The setup guide's progress bar is now a progress ring.
- Bars, slices and rings animate in once (0.3 s or less, transform and opacity only). Nothing animates under reduced motion.

## [1.2.0] - 2026-11-22

Insights that say what to do. Free outside context replaces paid search.

### Added
- **What to do now:** ranked, plain-language suggestions on Insights (all of them) and Overview (top 3), calculated from the business's own records without AI:
  - which product to sell more of
  - products selling less, or no longer selling
  - products losing money, with the price that would break even
  - margins being squeezed, with the price that restores the old margin
  - stock about to run out, with how much to order (matched to inventory by exact name)
  - money tied up in slow stock
  - dependence on one product or one customer
  - the busiest day of the week
- Each suggestion explains **why it may be happening**, labelled *likely* or *possible*: price vs volume, fewer vs smaller sales, regular buyers who stopped (named for the owner only), out of stock, the same pattern last year, or Ghanaian holidays and seasons. It also lists **what to do**.
- **Tap for details:** a sheet shows the numbers, reasons and actions. When an AI key is configured, it also shows Lance's short explanation, cached so repeat taps are free.
- A Ghana calendar (`ghana_calendar.py`) of statutory holidays, Easter, Eid and Ramadan (approximate), the festive season, back-to-school periods and weather seasons.
- Free, keyless news context from the GDELT index (`news_context.py`). It is used for explanations and by Ask Lance, rate-limited and best effort.
- "Get sharper suggestions" lists the missing columns (cost, quantity, customer, history) that would unlock more advice.

### Changed
- Ask Lance's search tool is now `news_search` (free GDELT headlines). It replaces the paid SerpAPI web search.

### Removed
- Brave Search web research: the Settings card, `/integrations/brave-search`, `/performance-research`, and stored Brave keys, which are deleted on upgrade.
- The `SERPAPI_KEY` setting.

## [1.1.0] - 2026-11-22

The design system and interface refinement (PRD §5.1, #7). It keeps the existing identity and makes it accessible, touch-friendly and lighter. See `docs/DESIGN_SYSTEM.md`.

### Added
- A component token tier for button, input, pill, card, table, dialog, toast and nav item, plus spacing, motion and z-index scales.
- A colour lint in `npm run check`. Colour literals are allowed only in token declarations.
- `docs/DESIGN_SYSTEM.md`: tiers, rules, the measured contrast table, the component inventory and fonts.
- A phone layout for data tables: each row becomes a labelled card, so no column is hidden off-screen.
- 44 px touch targets on touch screens. Compact controls get an invisible hit area, so desktop density is unchanged.

### Changed
- Fonts are self-hosted and preloaded, subset to Latin-1, the cedi sign and Ghanaian letters (ɛ ɔ ŋ ɖ ƒ ɣ ʋ). That is 92.6 KB from our own origin, against about 152 KB from two Google origins.
- Contrast was measured in both themes and fixed:
  - muted text is 4.5:1 on muted surfaces
  - AI-labelled text is 4.5:1
  - input borders and the focus ring are 3:1
  - landing grey text is 5.3:1
- Chart revenue and cost colours were re-picked per theme with a palette validator (colour-blind separation, and 3:1 against the surface).
- The smallest text is now 12 px. The 10, 10.5 and 11 px sizes are gone.

### Fixed
- On phones, the icon-only Print and New chat buttons had no accessible name.
- The setup progress bar had no accessible name.
- The Ask Lance conversation could be scrolled but not reached by keyboard.


## [1.0.1] - 2026-11-22

Migration follow-ups (PRD F0.1–F0.3). A first visit to the workspace now downloads about 108 KB instead of about 383 KB.

### Added
- Responses are gzip-compressed: bundles, HTML and API JSON. Auth responses are left uncompressed, so token sizes cannot leak (BREACH).
- The sign-in dialog prefetches the workspace bundle, so the app opens from cache after sign-in. This is skipped when the browser asks to save data.
- Each dataset reports its record date span (`period`). Existing files are backfilled once at startup.
- `docs/PRD.md`: product requirements for the v1.x update phase. It replaces `docs/UPDATE_PLAN.md` and keeps the original brief as an appendix.
- `docs/PERSONAS.md`: four cited Ghanaian SME personas and the per-change persona check.
- `docs/SKILLS_AUDIT.md`: an audit of the Claude Code skills and connectors used for development.
- `docs/HANDOFF.md` and `tools/verify/`: the session handoff, and the parity and e2e verification scripts used for the migration.
- This changelog.

### Changed
- Third-party code ships in its own `vendor` chunk. It keeps its cache across app-only releases, so returning users re-download about 11 KB instead of the whole bundle.
- `react-router` is replaced by a small in-house router (`src/lib/router.tsx`). It saves about 11 KB gzip and keeps the same behaviour: modified clicks open new tabs, `aria-current` on active links, back/forward, legacy `#page` redirects, and transition-based page loads.
- The Product name column now toggles between A→Z and Z→A, like the other columns.

### Fixed
- After switching file with a preset range such as "Last 30 days", the previous file's date window no longer shows briefly. Presets now resolve from the file's stored date span before the first request, and the extra request is gone.
- Opening a scoped page other than Overview, Products or Insights first (for example Ask Lance) no longer anchors presets to today instead of the latest record.

## [1.0.0] - 2026-11-21

The first versioned release. The frontend was migrated to React 19, TypeScript (strict) and Vite with feature parity (PR #12).

### Added
- React single-page workspace at `/app/*` with React Router pages. Old `#page` links redirect.
- TanStack Query caching. Scoped reads put the resolved file and date scope in the cache key.
- A typed API client. The access token is held in memory only, and concurrent 401s share one refresh.
- Error boundaries contain page crashes. Ask Lance threads persist across navigation.
- Hashed assets are served with immutable caching. Entry HTML is served `no-cache`.

### Changed
- The landing page keeps static markup, with a small TypeScript module for its interactions.

### Removed
- The pre-React frontend (`frontend/legacy/`).

### Known issues
- The workspace shell is about 100 KB gzip on first load, up from 29 KB.
- The old date window briefly renders after a file switch with a preset range.
- The Product name column never sorts Z→A. This was kept for parity.

[Unreleased]: https://github.com/ferlance-data/ferlance/compare/v1.8.0...HEAD
[1.8.0]: https://github.com/ferlance-data/ferlance/compare/v1.7.0...v1.8.0
[1.7.0]: https://github.com/ferlance-data/ferlance/compare/v1.6.0...v1.7.0
[1.6.0]: https://github.com/ferlance-data/ferlance/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ferlance-data/ferlance/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ferlance-data/ferlance/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ferlance-data/ferlance/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ferlance-data/ferlance/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ferlance-data/ferlance/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/ferlance-data/ferlance/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/ferlance-data/ferlance/releases/tag/v1.0.0
