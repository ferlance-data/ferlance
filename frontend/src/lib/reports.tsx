// Printable reports. Each builder renders into #print-report, then the browser prints it.

import type { ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { createRoot, type Root } from 'react-dom/client';
import { formatDate, formatDateTime, money, number, plainPercent } from './format';
import type { Analytics, Business, InsightsResponse, InventoryResponse, Movement, PositionBalance, PositionResult, User } from './types';

export const POSITION_LABELS: Record<string, string> = {
  cash: 'Cash on hand',
  bank: 'Cash at bank',
  receivables: 'Accounts receivable',
  inventory: 'Inventory at recorded cost',
  fixed_assets: 'Fixed assets',
  other_assets: 'Other assets',
  payables: 'Accounts payable',
  loans: 'Loans and borrowings',
  other_liabilities: 'Other liabilities',
  owner_capital: 'Owner capital',
  retained_earnings: 'Retained earnings / accumulated loss',
  other_equity: 'Other equity',
};

/** Who the report is for and by; passed in from the workspace context. */
export interface ReportContext {
  business: Business;
  user: User;
}

function Section({ title, headers, rows, note = null }: { title: string; headers: string[]; rows: ReactNode[][]; note?: string | null }) {
  return (
    <section>
      <h2>{title}</h2>
      {rows.length ? (
        <table>
          <thead>
            <tr>
              {headers.map((label) => (
                <th key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((value, cellIndex) => (
                  <td key={cellIndex}>{value}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="note">No data for this section.</p>
      )}
      {note ? <p className="note">{note}</p> : null}
    </section>
  );
}

function Header({ kind, title, lines }: { kind: string; title: string; lines: string[] }) {
  return (
    <header>
      <p>{`FERLANCE · ${kind}`}</p>
      <h1>{title}</h1>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </header>
  );
}

// The React root lives on the element so module reloads (dev HMR) reuse it instead of
// calling createRoot twice on the same container.
type ReportElement = HTMLElement & { __reportRoot?: Root };

function print(content: ReactNode) {
  const report = document.getElementById('print-report') as ReportElement | null;
  if (!report) return;
  report.__reportRoot ??= createRoot(report);
  const root = report.__reportRoot;
  flushSync(() => root.render(content));
  report.hidden = false;
  document.body.classList.add('printing');
  const done = () => {
    document.body.classList.remove('printing');
    report.hidden = true;
    window.removeEventListener('afterprint', done);
  };
  window.addEventListener('afterprint', done);
  window.print();
}

export function printFinancialReport(analytics: Analytics | null | undefined, insights: InsightsResponse | null | undefined, { business, user }: ReportContext) {
  if (!analytics) return;
  const isCost = analytics.profile?.domain === 'cost';
  const profit = analytics.profit;
  const comparison = analytics.comparison;
  const period = `${formatDate(analytics.period.from)} – ${formatDate(analytics.period.to)}`;
  const profitCost = Number(profit.cost ?? 0);
  const grossProfit = Number(profit.gross_profit ?? 0);
  const rows: ReactNode[][] = [
    ['Revenue', money(analytics.revenue.total)],
    ['Recorded costs', money(analytics.kpis.total_cost)],
    ['Profit after recorded costs', profit.available ? money(grossProfit) : `Unavailable — ${profit.reason}`],
    ['Return on recorded costs', profit.available && profitCost > 0 ? plainPercent((grossProfit / profitCost) * 100, 2) : 'Unavailable'],
    ['Average sale', money(analytics.revenue.average_sale)],
    ['Records', number(analytics.revenue.transactions)],
  ];
  const comparisonRows: ReactNode[][] =
    comparison?.available && comparison.metrics
      ? Object.entries(comparison.metrics).map(([key, metric]) => [
          key.replaceAll('_', ' '),
          metric.current === null ? '—' : key === 'transactions' ? number(metric.current) : money(metric.current),
          metric.previous === null ? '—' : key === 'transactions' ? number(metric.previous) : money(metric.previous),
          metric.change_pct === null ? '—' : plainPercent(metric.change_pct),
        ])
      : [];
  const products = analytics.products?.available ? analytics.products.items : [];
  const customers = analytics.customers?.available ? analytics.customers.top_customers : [];
  print(
    <>
      <Header
        kind="FINANCIAL REPORT"
        title={business.name}
        lines={[`Data: ${analytics.dataset?.filename || 'All business data'} · Period: ${period}`, `Prepared ${formatDateTime(new Date())} by ${user.email}`]}
      />
      <section>
        <h2>Summary</h2>
        <p>{analytics.summary}</p>
      </section>
      <Section
        title="Financial summary"
        headers={['Measure', 'Value']}
        rows={rows}
        note="Profit uses only the costs recorded in your imports. It is not a statutory income statement: overheads, tax, financing and currency conversion are not included."
      />
      {comparison?.available && comparison.previous_period ? (
        <Section
          title={`Compared with ${formatDate(comparison.previous_period.from)} – ${formatDate(comparison.previous_period.to)}`}
          headers={['Measure', 'This period', 'Previous period', 'Change']}
          rows={comparisonRows}
        />
      ) : null}
      <Section
        title="Item performance"
        headers={['Item', 'Revenue', 'Cost', 'Profit / loss', 'Margin', 'Units', 'Records']}
        rows={products.map((item) => [
          item.product,
          money(item.revenue),
          item.cost === undefined ? '—' : money(item.cost),
          item.gross_profit === undefined ? '—' : money(item.gross_profit),
          item.margin_pct === undefined ? '—' : plainPercent(item.margin_pct),
          item.units_sold ?? '—',
          number(item.transactions),
        ])}
      />
      <Section
        title={isCost ? 'Suppliers' : 'Customers'}
        headers={[isCost ? 'Supplier' : 'Customer', isCost ? 'Cost' : 'Revenue', 'Records']}
        rows={customers.map((item) => [item.customer, money(item.metric_value), number(item.transactions)])}
      />
      <Section title="Insights" headers={['Insight', 'Finding']} rows={(insights?.insights || []).map((item) => [item.title, item.message])} />
      {(analytics.warnings || []).length ? (
        <section>
          <h2>Data notes</h2>
          <ul>
            {analytics.warnings.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <p className="note">
        Prepared from accepted records in Ferlance. Verify source data and consult a qualified accountant before using this report for statutory or tax
        purposes.
      </p>
    </>,
  );
}

export function printInventoryReport(inventory: InventoryResponse, movements: Movement[], { business, user }: ReportContext) {
  const summary = inventory.summary;
  print(
    <>
      <Header kind="INVENTORY" title="Inventory report" lines={[`${business.name} · Prepared ${formatDateTime(new Date())} by ${user.email}`]} />
      <Section
        title="Stock overview"
        headers={['Measure', 'Value']}
        rows={[
          ['Active products', number(summary.product_count)],
          ['Units on hand', number(summary.units_on_hand, 3)],
          ['At or below reorder level', number(summary.low_stock_count)],
          ['Stock value', summary.inventory_value_complete ? money(summary.inventory_value) : 'Unavailable — some stock has no unit cost'],
        ]}
      />
      <Section
        title="Products"
        headers={['Product', 'SKU', 'On hand', 'Unit', 'Unit cost', 'Status']}
        rows={inventory.items.map((item) => [
          item.name,
          item.sku || '—',
          number(item.quantity_on_hand, 3),
          item.unit,
          item.unit_cost === null ? 'Not set' : money(item.unit_cost),
          !item.active ? 'Archived' : item.low_stock ? 'Low stock' : 'In stock',
        ])}
      />
      <Section
        title="Recent movements"
        headers={['Date', 'Product', 'Type', 'Change', 'Note']}
        rows={movements.map((item) => [
          formatDateTime(item.created_at),
          item.product_name,
          item.movement_type,
          `${item.quantity_delta > 0 ? '+' : ''}${number(item.quantity_delta, 3)} ${item.unit}`,
          item.note || '—',
        ])}
      />
      <p className="note">
        Quantities reflect recorded opening stock, purchases, sales, adjustments and stocktakes only. Verify physical counts before relying on this report.
      </p>
    </>,
  );
}

export function printPositionReport(result: PositionResult, { business, user }: ReportContext) {
  const groupRows = (items: PositionBalance[]) =>
    items.map((item) => [item.account_name, POSITION_LABELS[item.category] || item.category, money(item.amount), formatDate(item.as_of_date)]);
  const totals = result.totals;
  const headers = ['Account', 'Category', 'Balance', 'Balance date'];
  print(
    <>
      <Header
        kind="FINANCIAL POSITION"
        title="Statement of financial position"
        lines={[`${business.name} · As of ${formatDate(result.as_of_date)}`, `Prepared ${formatDateTime(new Date())} by ${user.email}`]}
      />
      <Section title="Assets" headers={headers} rows={groupRows(result.assets)} />
      <Section title="Liabilities" headers={headers} rows={groupRows(result.liabilities)} />
      <Section title="Equity" headers={headers} rows={groupRows(result.equity)} />
      <Section
        title="Totals"
        headers={['Measure', 'Value']}
        rows={[
          ['Total assets', money(totals.assets)],
          ['Total liabilities', money(totals.liabilities)],
          ['Total equity', money(totals.equity)],
          ['Assets − liabilities − equity', money(totals.balance_difference)],
          ['Completeness', totals.complete ? 'Every category has a balance' : `Partial — missing ${result.missing_categories.map((item) => item.label).join(', ')}`],
          ['Accounting equation', totals.balanced ? 'Balances' : 'Not verified as balanced'],
        ]}
      />
      <p className="note">
        Each account uses its latest balance on or before the report date. Missing balances are not assumed to be zero. This operational statement is not a
        substitute for accountant-reviewed financial statements.
      </p>
    </>,
  );
}
