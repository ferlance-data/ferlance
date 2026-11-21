# Ferlance personas

These four personas are used for the per-change persona check (see `docs/PRD.md`, *Process*). For each change we ask: **"Does the app provide ease, comfort and value to this Ghanaian SME?"**

**The personas are composites, not interviewees.** Each one is built from the published context below, Ferlance's own data contract and the benchmark products in `docs/ARCHITECTURE.md`. Any persona detail without a citation is an assumption, and should be tested with real users once Ferlance has them. Names are illustrative.

## Shared context (cited)

| Fact | Figure | Source |
| --- | --- | --- |
| Internet penetration | About 75% of the population (26.3 million users, Oct 2025) | [DataReportal, Digital 2026: Ghana][dr] |
| Mobile usage gap | 4G covers 99% of people, but a 62% usage gap persists | [GSMA Ghana report, Sep 2025][gsma] |
| Mobile OS | Android about 67–71%, iOS about 29–33% of mobile traffic (mid-2026) | [Statcounter][sc] |
| Data price | Average about GH₵6.30 per GB (regulator study, Apr 2024). Users still describe data as expensive. | [NCA, *The Cost of 1GB of Data in Ghana*][nca]; [Citi Newsroom][citi] |
| Power outages | 70.7% of Greater Accra businesses reported major or severe effects. Outages averaged about 4 per week (IEA survey, 2024). | [MyJoyOnline / IEA][iea] |
| Mobile money | GH¢3.01 trillion transacted in 2024, with over 24 million active users. The 1% E-Levy was abolished from 2 April 2025. | [MyJoyOnline / BoG][bog]; [GNA][elevy] |
| Literacy | 69.8% literate (age 6+, 2021 census). Greater Accra 87.9%, Savannah 32.8%. | [GSS via Graphic][lit]; [GNA][lit2] |
| Record keeping | Ghanaian SME studies repeatedly find weak bookkeeping knowledge, time and cost constraints, and low perceived value of records. Poor records are linked to weak access to finance. | [Musah, JABM][rk1]; [Heliyon 2024 (Ho)][rk2] |
| Finance gap | The Bank of Ghana estimates a US$4.8 billion annual SME financing gap and promotes lending based on digital records | [MyJoyOnline / BoG][gap] |
| E-VAT | VAT-registered businesses are being moved onto GRA electronic invoicing | [GRA E-VAT][evat]; [VATCalc][vatcalc] |

### What this means for every feature

1. **Android phone first.** The design should hold up at 360 px width, on mid-range hardware and on a slow 4G or 3G link. First-load weight is a feature: the 100 KB gzip workspace shell flagged in the handoff matters to these users.
2. **Data and power drop out.** Uploads and forms must survive a dropped connection without losing work, and nothing should need a long-lived session to finish.
3. **Plain language and numbers people can trust.** Use short labels and say "missing" instead of a silent zero. Mobile money is a first-class data source, not an add-on.
4. **Records are a means to an end.** People keep records to get paid, restock, file VAT or get a loan, not for their own sake. Features should pay off in one of those terms.

## 1. Akosua, market trader on MoMo

- **Business:** Sells provisions and household goods from a stall in a large urban market. She sells mostly for cash and MoMo, and has one helper.
- **Device and connectivity:** A budget Android phone, shared with family in the evenings. She buys small data bundles and is careful with them. Power at the stall is unreliable.
- **Literacy and language:** Reads Twi and enough English to manage SMS alerts. She prefers numbers and icons to paragraphs.
- **Tools today:** MoMo SMS alerts, an exercise book for credit customers, and memory.
- **Pain points:** She cannot tell profit from takings. Customer credit is forgotten. She does not know which goods earn the most. She would never sit down with a spreadsheet.
- **Ferlance touchpoints:** Pasting MoMo SMS, the Overview, instant questions and, later, the mobile app.
- **Success looks like:** After pasting a week of SMS she sees "you took GH¢X, your best seller is Y", in under a minute on her phone, using little data. No typing beyond the paste.

## 2. Kwame, pharmacy owner with stock

- **Business:** A licensed community pharmacy in a regional capital, with two staff and hundreds of SKUs. Many products have expiry dates, and he buys from several wholesalers.
- **Device and connectivity:** A mid-range Android phone and a shop desktop. Shop Wi-Fi or a router, with a UPS for outages.
- **Literacy and language:** Highly literate in English (a professional).
- **Tools today:** A paper stock book, wholesaler invoices, Excel for occasional stocktakes, and MoMo and POS for payments.
- **Pain points:** Stock-outs of fast movers, and expired stock written off. Typing in wholesaler invoices takes hours. Sales and stock records do not agree.
- **Ferlance touchpoints:** Inventory, stocktake import, OCR capture of invoices (#1), inventory↔product sync (#2) and low-stock alerts.
- **Success looks like:** He photographs a wholesaler invoice, checks the extracted lines and accepts them into stock in about two minutes. Sales and stock reconcile, and the low-stock list matches the shelf. He never has to wonder whether a number is a guess.

## 3. Efua, services firm with an accountant

- **Business:** A small events and logistics services firm in Accra with about 8 staff. It is VAT-registered and an external accountant does the books quarterly.
- **Device and connectivity:** A laptop at the office plus an iPhone. Reliable fibre, with dumsor backup from a generator.
- **Literacy and language:** Fluent English. Comfortable with dashboards but short of time.
- **Tools today:** Bank and MoMo statements, invoices in Word, and the accountant's Excel workbook.
- **Pain points:** She only learns the margin when the accountant reports, months late. She needs a financial position for a bank loan. VAT and E-VAT compliance takes effort.
- **Ferlance touchpoints:** Financial position, printable reports, insights with period comparison, and access for the accountant or admin (#4/#5).
- **Success looks like:** A clean monthly report she can send to the bank or the accountant, and numbers that match the accountant's to the cedi. Her accountant gets their own sign-in rather than sharing her password.

## 4. Yaw, growing retailer on Excel

- **Business:** Two electronics and accessories shops, with a third planned. He has a store manager at each shop, sells on Instagram and WhatsApp too, and has a few thousand sales lines a month.
- **Device and connectivity:** Android flagship, a laptop and good 4G. He works on the move between shops.
- **Literacy and language:** Fluent English. A confident Excel user.
- **Tools today:** One Excel workbook per shop, emailed weekly, and MoMo merchant and bank statements.
- **Pain points:** Merging workbooks by hand. The shops use different product names for the same SKU. He cannot see which shop or channel is growing, and is worried about double-counting re-sent files.
- **Ferlance touchpoints:** Data imports and folder imports, duplicate detection, Products, analytics visuals (#6), onboarding his managers (#4), Ask Lance and the mobile app (#9).
- **Success looks like:** Weekly files land automatically and duplicates are flagged. One product list across shops. Clear, fast charts on his phone between meetings, and the ability to add a manager without sharing his login.

## Running the persona check

For each change, answer for each persona that the change touches, in the PR description:

| Persona | Ease (fewer steps, clearer) | Comfort (works on their device, connection and literacy) | Value (pays off in money, time or trust) | Verdict |
| --- | --- | --- | --- | --- |

A "no" from any persona the change targets blocks the PR until it is fixed or explicitly accepted as a known gap.

[dr]: https://datareportal.com/reports/digital-2026-ghana
[gsma]: https://www.gsma.com/about-us/regions/africa/wp-content/uploads/2025/08/GSMA_Ghana-Report_September.pdf
[sc]: https://gs.statcounter.com/os-market-share/mobile/ghana
[nca]: https://www.nca.org.gh/wp-content/uploads/2024/07/The-Cost-of-1GB-of-Data-in-Ghana.pdf
[citi]: https://citinewsroom.com/2025/02/data-cost-in-ghana-remains-high-despite-low-cost-ranking/
[iea]: https://www.myjoyonline.com/dumsor-brought-untold-hardship-to-most-people-in-the-gt-accra-region-iea-survey/
[bog]: https://www.myjoyonline.com/mobile-money-transactions-hits-gh%c2%a23trn-as-digital-payments-surge-bog-report/
[elevy]: https://gna.org.gh/2025/03/parliament-abolishes-e-levy-returns-gh2-billion-to-ghanaians/
[lit]: https://www.graphic.com.gh/news/general-news/literacy-rate-now-69-8-per-cent.html
[lit2]: https://gna.org.gh/2022/02/2021-phc-over-60-per-cent-ghanaian-population-is-literate/
[rk1]: https://journal.stie-mce.ac.id/index.php/jabminternational/article/download/320/81
[rk2]: https://doaj.org/article/91d05f9c9fd4405badb9f2fae13c6c3f
[gap]: https://www.myjoyonline.com/bog-identifies-4-8bn-annual-sme-financing-gap-pushes-digital-data-driven-lending/
[evat]: https://gra.gov.gh/e-vat/
[vatcalc]: https://www.vatcalc.com/ghana/ghana-e-vat-electronic-invoicing-rollout/
