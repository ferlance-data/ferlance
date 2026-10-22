# Ferlance Data Contract

Ferlance accepts CSV and XLSX files for business records. Headers are matched case-insensitively after spaces, punctuation, and underscores are removed. For example, `Order Date`, `order_date`, and `ORDER-DATE` are treated as the same header.

Every row must contain:

- A date column.
- At least one financial column: revenue/amount, total cost/expense, or unit cost.

Rows with a valid date and at least one financial value are accepted even when optional business fields are missing. Invalid dates, non-numeric financial values, rows with no financial value, and duplicate transaction IDs are rejected with a row-level warning. Blank optional values are kept blank and do not make the entire file fail. Identical rows without transaction IDs are preserved because they may be separate legitimate transactions; include a stable unique transaction ID to enable duplicate detection.

Extra headers are tolerated. They do not cause rejection, but only the normalized fields described below currently feed analytics. Fields such as `category`, `branch`, `department`, `cost_center`, `region`, `environment`, `status`, `payment_terms`, `unit_price`, `tax_usd`, `shipping_usd`, `variance_usd`, and `variance_pct` are not yet used as standalone metrics.

## Sales and revenue

Use this category for transactions, invoices, POS exports, mobile-money sales, or other income records.

| Business meaning | Accepted headers |
| --- | --- |
| Transaction date | `transaction_date`, `date`, `sale_date`, `transactiondate`, `order_date`, `usage_date`, `expense_date`, `invoice_date` |
| Revenue | `amount`, `sales_amount`, `revenue`, `total`, `sale_amount`, `sales`, `income`, `gross_sales` |
| Transaction ID | `transaction_id`, `id`, `transactionid`, `sale_id` |
| Product or service | `product`, `product_name`, `item`, `item_name`, `item_description`, `service_name`, `project_name` |
| Customer | `customer`, `customer_name`, `client`, `client_name` |
| Quantity | `quantity`, `qty`, `units`, `usage_quantity` |
| Unit cost | `unit_cost`, `cost_per_unit`, `unit_cost_usd`, `cost_per_unit_usd` |

Recommended example:

```csv
transaction_id,transaction_date,amount,product,customer,quantity
TX-1001,2026-01-15,1250.50,Rice,Ama Retail,10
TX-1002,2026-01-16,875.00,Beans,,7
```

Missing product or customer values do not reject the sale. Revenue and transaction metrics still include the row; product and customer metrics include only rows with the relevant value.

## Operating costs and expenses

Cost-only files are supported. They are accepted as costs with zero revenue, so they do not inflate sales totals. Unit cost is multiplied by quantity when quantity is supplied (or treated as one unit when quantity is absent). Aggregate profit after recorded costs is shown only when every accepted record in the selected period has a cost and revenue is present; missing costs are never silently treated as zero.

| Business meaning | Accepted headers |
| --- | --- |
| Cost or expense | `cost`, `cost_amount`, `expense`, `expense_amount`, `actual_cost`, `actual_cost_usd`, `total_cost`, `total_cost_usd`, `net_charged_cost`, `net_charged_cost_usd`, `unblended_cost_usd`, `budgeted_cost_usd`, `subtotal_usd` |
| Unit cost | `unit_cost`, `cost_per_unit`, `unit_cost_usd`, `cost_per_unit_usd` |
| Date | Any accepted date header above, including `expense_date` and `order_date` |
| Record ID | `expense_id`, `id`, `po_number`, `invoice_line_id`, `transaction_id` |
| Supplier or provider | `vendor_name`, `cloud_provider` |
| Description or service | `item_description`, `service_name`, `project_name`, `product` |
| Quantity | `quantity`, `qty`, `units`, `usage_quantity` |

Examples of supported cost exports include:

```csv
expense_id,date,project_name,actual_cost_usd
EXP-1,2026-01-15,Store renovation,450.00
```

```csv
po_number,order_date,vendor_name,item_description,quantity,total_cost_usd
PO-1001,2026-01-15,Acme Supplies,Packaging,100,325.00
```

```csv
invoice_line_id,usage_date,cloud_provider,service_name,usage_quantity,net_charged_cost_usd
LINE-1,2026-01-15,Cloud Provider,Compute,42,18.75
```

## Budgets and project planning

Budget exports are accepted when they contain a date and a recognized financial value. `budgeted_cost_usd` is treated as cost data. A budget file should include a project, cost center, category, or description so it can be identified in records even if it does not have a product or customer.

Recommended headers:

```csv
project_name,date,cost_center,expense_category,budgeted_cost_usd
Store renovation,2026-01-15,OPERATIONS,Construction,12000.00
```

Actual-versus-budget files can include both `budgeted_cost_usd` and `actual_cost_usd`. The current normalized record keeps the recognized cost value; use separate files when the distinction between planned and actual spend must remain independently reportable.

## Values and dates

- Financial values may include currency symbols, currency codes, commas, decimals, and accounting negatives such as `(125.50)`.
- Store currency consistently within a file. Currency symbols are stripped during parsing; USD is detected from headers containing `USD`, otherwise GHS is the default. If multiple currencies occur in a report, totals are not converted and the report displays a warning.
- Accepted date formats are `YYYY-MM-DD`, `DD/MM/YYYY`, `MM/DD/YYYY`, and `YYYY/MM/DD`.
- XLSX files use the first worksheet and the first row as headers.
- CSV files should be UTF-8; UTF-8 BOM files are supported.
- A date is strongly recommended for transaction, cost, procurement, and budget rows because trends and cross-dataset comparisons must be time-grounded. The universal engine retains date-less records such as manufacturing BOM lines, but downstream time-based analytics cannot use them. Add an `effective_date` column when a BOM needs temporal analysis; Ferlance does not fabricate dates.

## What the metrics can use

- Revenue, transaction count, average sale, and date trends require only a valid date and revenue/amount.
- Product metrics require a product, item, service, or project value on the relevant row.
- Customer metrics require a customer, client, vendor, or provider value on the relevant row.
- Units sold require quantity on every product row. Missing quantities do not reject records; units are reported as unavailable for incomplete product data.
- Aggregate profit after recorded costs requires revenue and a recognized total or unit cost on every accepted record in the selected period. It is calculated as revenue minus recorded costs; the legacy API field is named `gross_profit`, but this is not a formal accounting gross-profit measure because cost types are not separated.
- Cost trends are withheld when any accepted record in the selected period is missing cost; missing costs are not plotted or treated as zero.
- Per-item profit/loss, margin, and ROI require a product and a recognized cost on every product record. ROI is profit after recorded item cost divided by recorded item cost; it is unavailable for zero-cost or zero-revenue items and excludes costs not assigned to the item, taxes, and financing.
- Quarterly trends use calendar quarters (`Q1` through `Q4`) and are available alongside daily, weekly, monthly, and yearly views.
- Cross-dataset Ask Lance analytics keep different currencies in separate groups. No consolidated amount or comparison is provided without an explicit exchange-rate conversion.
- Inventory metrics are not inferred from quantity sold. They require future stock or inventory movement data.

## Ask Lance and intelligent rankings

The workspace dashboard provides product rankings that can be switched between:

- Most revenue
- Most transactions
- Most profit
- Most loss
- Most return on cost (shown in the item table)

Profit and loss rankings are shown only when every product record in the selected period has a recognized cost. This prevents the system from treating missing cost as zero profit. The dashboard also generates grounded insights automatically, including item losses and the highest recorded item return. Period tabs switch trends among day, week, month, quarter, and year; date filters can further constrain the report. **Print financial report** prepares a print-friendly report for the currently selected dataset and date range, with financial summary, trend, item and customer tables, insights, upload quality, and limitations. Separate dataset uploads are not consolidated into one report.

The Catalogue workspace lists every distinct product name in the selected dataset across all dates, with search and sorting by name, revenue, or available profit. It is derived from uploaded transaction rows; it is not an editable product master and does not represent stock on hand, SKU, or current list price.

The Inventory workspace is a separate business-scoped product master and movement ledger. It supports SKUs, units, optional recorded unit costs, reorder levels, opening stock, purchases/receipts, sales/stock issues, signed adjustments, archive/restore, recent movement history, and printable snapshots. A CSV stocktake requires `product` and `quantity_on_hand`; optional columns are `sku`, `unit`, `unit_cost`, and `reorder_level`. Each stocktake is processed atomically: new product rows create opening stock, while existing products record the difference between the counted quantity and the ledger quantity. A failed row rejects the entire import. Ordinary sales/cost dataset uploads never modify inventory automatically, and inventory purchases are not automatically booked as financial expenses or cost of goods sold.

On-hand stock is calculated from the movement ledger, and sales/issue movements that would make a product's stock negative are rejected. Archived products leave the active list and reorder alerts but remain in total on-hand units and stock valuation until their balance is reconciled. Displayed stock value multiplies on-hand units by the product's currently recorded unit cost; it is withheld when any product with stock has no unit cost. This is an operational estimate, not FIFO/weighted-average accounting valuation, a general ledger, or a multi-location stock balance. Physical counts, costs, and movements still need reconciliation; batches, expiry tracking, reservations, and multiple warehouses are not modeled.

## External performance research

The Insights workspace can connect a business's Brave Search API key. Once configured, Ferlance automatically evaluates the selected report period and searches when it detects a period-over-period business revenue decline or a product loss. It refreshes research when the selected dataset or date filter changes; users can also request a fresh search. Queries include the product label, market (Ghana), report dates, and terms relating to seasonality, weather, environmental conditions, festivals, holidays, and market conditions. They do not include transaction rows, amounts, or customer information.

Configure a persistent `FERLANCE_SECRET_KEY` of at least 32 characters before saving a provider credential. Ferlance encrypts the key in its business-scoped integration table and does not return it to the browser. Rotating the application secret invalidates saved encrypted credentials, which must then be entered again. Brave Search requires a valid API key and internet access; provider usage may incur charges.

Retrieved pages are shown as linked sources. If an LLM provider is available, Ask Lance gives a contextual assessment with source citations; if it is unavailable, the sources are still shown with an explicit analysis error. External information is a research lead only: the search does not prove why a business result changed, may be outdated or irrelevant, and should be checked against internal records. The report can include the findings and source links that are currently loaded for its selected dataset and date filter.

## Dated financial-position balances

The Financial position workspace records append-only manual balances for named accounts in these categories: cash, bank, receivables, inventory, fixed assets, other assets, payables, loans, other liabilities, owner capital, retained earnings/accumulated loss, and other equity. Inventory value is manually entered separately from the unit-count inventory ledger.

For an `as_of` date, each named account is represented by its latest entry on or before that date. Entries after the report date are excluded, and carried-forward entries are flagged as stale. Missing categories are not assumed to be zero; totals remain partial and the statement is not marked complete. Record zero for categories that do not apply if you want all-category completeness checking. The assets-versus-liabilities-and-equity difference is shown, but a complete or balanced operational snapshot is not a substitute for a general ledger, statutory statement, or accountant review.

Ask Lance uses the same calculated snapshot as the dashboard. It sends the user's question and structured metrics to OpenRouter, not the raw uploaded file. Add the key to the local `.env` file and restart the server:

```dotenv
OPENROUTER_KEY=your_openrouter_key_here
OPENROUTER_MODEL=deepseek/deepseek-v4.1-flash
OPENROUTER_URL=https://openrouter.ai/api/v1/chat/completions
OPENROUTER_MODELS=inclusionai/ling-3.1-flash,openai/gpt-oss-20b,upstage/solar-mini4,allam-2-7b,openai/gpt-oss-120b
OPENROUTER_MAX_TOKENS=800
OPENROUTER_TIMEOUT_SECONDS=8
```

Without a configured key, Ask Lance reports that it is unavailable; deterministic dashboard metrics continue to work. Lance is instructed to stay grounded in the supplied metrics and to identify unavailable data instead of inventing it.

Ask Lance conversations are saved per authenticated user and business. Each conversation is pinned to the selected dataset so follow-up questions stay grounded in the same records. The interface shows the saved conversation list, ordered user and Lance messages, timestamps, and a New chat action.

Conversation API endpoints:

- `POST /api/businesses/{business_id}/ask-lance` creates or continues a conversation. Send `{ "question": "...", "conversation_id": "..." }`; omit `conversation_id` to start a new chat.
- `GET /api/businesses/{business_id}/ask-lance/conversations` lists the signed-in user's saved conversations.
- `GET /api/businesses/{business_id}/ask-lance/conversations/{conversation_id}` returns one conversation and its ordered messages.

Conversation history is tenant-scoped and is never shared between businesses or users. Ask Lance now uses a business-wide retrieval-augmented generation (RAG) context: accepted rows from every processed dataset are indexed in a local SQLite FTS5 index, relevant rows are retrieved from that index, and aggregate analytics are calculated across all accepted business records. The model receives the calculated cross-dataset snapshot, retrieved evidence, and a limited recent message history; raw uploaded files are not sent to OpenRouter.

The selected dataset remains an anchor for the conversation label and date filters, but it no longer limits Lance's knowledge. A question can compare sales, costs, budgets, procurement, and other processed data belonging to the same business. RAG retrieval is rebuilt automatically for datasets that are not yet indexed, so existing uploads become available without re-uploading them.

## Upload status

- `processed`: every row was accepted.
- `partial`: at least one row was accepted and at least one row was rejected.
- `failed`: no rows were accepted, or the file is empty, unreadable, or missing both a date and a financial column.

The upload history always records source rows, accepted rows, rejected rows, warnings, and errors so a business can trace what happened to its source data.