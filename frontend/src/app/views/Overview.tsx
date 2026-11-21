import { useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import { BarChart, type Bar } from '../../lib/chart/BarChart';
import { money, number, plainPercent, plural, setCurrency } from '../../lib/format';
import { Icon, IconSlot } from '../../lib/icons';
import { printFinancialReport } from '../../lib/reports';
import { analysableDatasets } from '../../lib/scope';
import type { Analytics, CostPoint, Dataset, InsightsResponse, InventoryResponse, Period, TrendPoint } from '../../lib/types';
import { Delta, EmptyState, Kpi, Segmented, SkeletonRows } from '../components/ui';
import { useScopedQuery } from '../hooks';
import { PageActions } from '../page';
import { pagePath } from '../routes';
import { useScope, useWorkspace } from '../workspace';
import { AttentionItem, InsightCard, RankItems, type AttentionEntry } from './shared';

type Comparison = Analytics['comparison'];
type TrendPeriod = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly';

const PERIOD_LABEL: Record<TrendPeriod, string> = { daily: 'day', weekly: 'week', monthly: 'month', quarterly: 'quarter', yearly: 'year' };
const PERIODS: { value: TrendPeriod; label: string }[] = [
  { value: 'daily', label: 'Day' },
  { value: 'weekly', label: 'Week' },
  { value: 'monthly', label: 'Month' },
  { value: 'quarterly', label: 'Quarter' },
  { value: 'yearly', label: 'Year' },
];

export default function Overview() {
  const { user, business, datasets, inventory } = useWorkspace();
  const { hasData } = useScope();
  const analyticsQuery = useScopedQuery<Analytics>('/analytics', { updatesBounds: true, enabled: hasData });
  const insightsQuery = useScopedQuery<InsightsResponse & { available_period?: Period }>('/insights', { enabled: hasData, silent: true });
  const [trendPeriod, setTrendPeriod] = useState<TrendPeriod>('weekly');

  const analytics = hasData ? analyticsQuery.data : undefined;
  // A failed insights request is treated as "no insights" (the read is silent).
  const insights = hasData && !insightsQuery.isError ? (insightsQuery.data ?? null) : null;
  const insightsPending = hasData && insightsQuery.isPending;
  if (analytics) setCurrency(analytics.currency);

  return (
    <>
      <PageActions>
        <button className="btn btn-secondary" type="button" id="print-financial" disabled={!analytics} onClick={() => analytics && printFinancialReport(analytics, insights, { business, user })}>
          <Icon name="printer" />
          <span className="btn-label">Print report</span>
        </button>
      </PageActions>
      <div id="overview-setup">
        <SetupGuide />
      </div>
      <div className="kpi-grid" id="overview-kpis">
        {!hasData ? <EmptyKpis datasets={datasets} /> : analytics ? <Kpis result={analytics} /> : Array.from({ length: 4 }, (_, index) => <div className="kpi" key={index}><SkeletonRows count={2} height={16} /></div>)}
      </div>
      <div className="grid-main">
        <TrendCard analytics={analytics} hasData={hasData} datasets={datasets} period={trendPeriod} onPeriod={setTrendPeriod} />
        <div className="card attention-card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Needs attention</h2>
              <p className="card-subtitle">Signals worth a look today</p>
            </div>
          </div>
          <div className="card-body">
            <ul className="attention-list" id="attention-list">
              {analytics || !hasData ? attentionEntries(analytics, insights, inventory, datasets).map((entry, index) => <AttentionItem key={index} {...entry} />) : null}
            </ul>
          </div>
        </div>
      </div>
      <Rankings analytics={analytics} />
      <div className="grid-2">
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Latest insights</h2>
              <p className="card-subtitle">Calculated from your records — no guesswork</p>
            </div>
            <Link className="btn btn-ghost btn-sm" to={pagePath('insights')}>
              All insights
              <IconSlot name="arrow-right" />
            </Link>
          </div>
          <div className="card-body">
            <div className="insight-stack" id="overview-insights">
              {!hasData ? (
                <EmptyState title="No insights yet" message="Insights are calculated from your imported records." />
              ) : !analytics || insightsPending ? null : insights?.insights?.length ? (
                insights.insights.slice(0, 3).map((item, index) => <InsightCard key={index} item={item} compact />)
              ) : (
                <EmptyState title="No insights for this period" message="Try a wider date range." />
              )}
            </div>
          </div>
        </div>
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">Stock at a glance</h2>
              <p className="card-subtitle">From your inventory ledger</p>
            </div>
            <Link className="btn btn-ghost btn-sm" to={pagePath('inventory')}>
              Inventory
              <IconSlot name="arrow-right" />
            </Link>
          </div>
          <div className="card-body">
            <StockStats inventory={inventory} />
          </div>
        </div>
      </div>
      <details className="data-notes" id="overview-notes" hidden={!analytics?.warnings?.length}>
        <summary>Data notes</summary>
        <ul id="overview-notes-list">
          {(analytics?.warnings || []).map((note, index) => (
            <li key={index}>{note}</li>
          ))}
        </ul>
      </details>
    </>
  );
}

/* ---------- Setup guide ---------- */
function SetupGuide() {
  const { business, datasets, inventory, setup } = useWorkspace();
  const dismissKey = `ferlance-setup-dismissed:${business.id}`;
  const [hidden, setHidden] = useState(false);
  const steps: { done: boolean; title: string; detail: string; to: string; action: string }[] = [
    { done: analysableDatasets(datasets).length > 0, title: 'Import your sales records', detail: 'A spreadsheet export or pasted Mobile Money alerts.', to: pagePath('data'), action: 'Import' },
    { done: (inventory?.summary.product_count || 0) > 0, title: 'Add the products you stock', detail: 'Get low-stock alerts and a stock value.', to: pagePath('inventory'), action: 'Add products' },
    { done: setup.balances, title: 'Record your cash and bank balances', detail: 'Unlock a statement of financial position.', to: pagePath('position'), action: 'Record' },
    { done: setup.conversations, title: 'Ask Lance a question', detail: '“Which products made the most profit last month?”', to: pagePath('lance'), action: 'Ask' },
  ];
  const complete = steps.filter((step) => step.done).length;
  let dismissed = false;
  try {
    dismissed = localStorage.getItem(dismissKey) === '1';
  } catch {
    /* storage unavailable */
  }
  if (hidden || complete === steps.length || (dismissed && complete > 0)) return null;
  const hide = () => {
    try {
      localStorage.setItem(dismissKey, '1');
    } catch {
      /* ignore */
    }
    setHidden(true);
  };
  return (
    <section className="setup" aria-label="Setup guide">
      <div>
        <p className="eyebrow">Setup guide</p>
        <h2>{complete ? 'Keep going — your numbers get sharper with each step.' : `Welcome to Ferlance, ${business.name}.`}</h2>
        <p>Four short steps turn your records into a full picture of the business.</p>
        <div className="setup-progress" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={complete}>
          <i style={{ width: `${(complete / steps.length) * 100}%` }} />
        </div>
        <p className="footnote" style={{ marginTop: '8px' }}>{`${complete} of ${steps.length} complete`}</p>
        {complete ? (
          <button className="btn btn-ghost btn-sm" type="button" style={{ marginTop: '10px', marginLeft: '-10px' }} onClick={hide}>
            Hide guide
          </button>
        ) : null}
      </div>
      <ol className="setup-steps">
        {steps.map((step) => (
          <li className={`setup-step${step.done ? ' done' : ''}`} key={step.title}>
            <span className="setup-check">{step.done ? <Icon name="check" /> : null}</span>
            <div>
              <strong>{step.title}</strong>
              <p>{step.detail}</p>
            </div>
            {step.done ? null : (
              <Link className="btn btn-secondary btn-sm" to={step.to}>
                {step.action}
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ---------- KPIs ---------- */
function CompareFoot({ comparison, metricKey, invert = false }: { comparison: Comparison | undefined; metricKey: string; invert?: boolean }): ReactNode {
  if (!comparison?.available) return <span>{comparison?.previous_period ? 'No earlier period to compare' : 'Choose a date range to compare'}</span>;
  const metric = comparison.metrics?.[metricKey];
  if (!metric || metric.change_pct === null) return <span>No comparable value</span>;
  const previous = metricKey === 'transactions' ? number(metric.previous) : money(metric.previous, { compact: true });
  return (
    <>
      <Delta change={metric.change_pct} invert={invert} />
      <span>{`vs ${previous}`}</span>
    </>
  );
}

function Kpis({ result }: { result: Analytics }) {
  const comparison = result.comparison;
  if (result.profile?.domain === 'cost') {
    const { kpis } = result;
    return (
      <>
        <Kpi label="Total cost" value={money(kpis.total_cost)} foot={<CompareFoot comparison={comparison} metricKey="cost" invert />} icon="receipt" />
        <Kpi label="Records" value={number(kpis.transactions)} foot={<CompareFoot comparison={comparison} metricKey="transactions" />} icon="file" />
        <Kpi label="Average cost" value={money(kpis.transactions ? kpis.total_cost / kpis.transactions : 0)} foot="Per record" icon="coins" />
        <Kpi label="Largest cost item" value={kpis.top_product || '—'} text foot="By recorded cost" icon="products" />
      </>
    );
  }
  const profitRevenue = Number(result.profit.revenue) || 0;
  return (
    <>
      <Kpi label="Revenue" value={money(result.kpis.total_revenue)} foot={<CompareFoot comparison={comparison} metricKey="revenue" />} icon="trending-up" />
      {result.profit.available ? (
        <Kpi
          label="Profit after costs"
          value={money(result.profit.gross_profit)}
          foot={
            <>
              <CompareFoot comparison={comparison} metricKey="gross_profit" />
              <span>{`· ${plainPercent(profitRevenue ? ((result.profit.gross_profit ?? 0) / profitRevenue) * 100 : 0)} margin`}</span>
            </>
          }
          icon="coins"
        />
      ) : (
        <Kpi label="Profit after costs" value="Needs costs" text foot="Add a cost column to every record" icon="coins" />
      )}
      <Kpi label="Sales" value={number(result.kpis.transactions)} foot={<CompareFoot comparison={comparison} metricKey="transactions" />} icon="receipt" />
      <Kpi label="Average sale" value={money(result.kpis.average_sale)} foot={<CompareFoot comparison={comparison} metricKey="average_sale" />} icon="users" />
    </>
  );
}

function EmptyKpis({ datasets }: { datasets: Dataset[] }) {
  const allExcluded = analysableDatasets(datasets).length > 0;
  return (
    <>
      {['Revenue', 'Profit after costs', 'Sales', 'Average sale'].map((label) => (
        <Kpi key={label} label={label} value="—" foot={allExcluded ? 'All files are switched off' : 'Import data to see this'} />
      ))}
    </>
  );
}

/* ---------- Trend ---------- */
function TrendCard({ analytics, hasData, datasets, period, onPeriod }: { analytics: Analytics | undefined; hasData: boolean; datasets: Dataset[]; period: TrendPeriod; onPeriod: (value: TrendPeriod) => void }) {
  const isCost = analytics?.profile?.domain === 'cost';
  let bars: Bar[] = [];
  let line: Map<string, number> | null = null;
  if (analytics) {
    const raw = analytics.trend[isCost ? `cost_${period}` : period] || [];
    bars = isCost
      ? (raw as CostPoint[]).map((item) => ({ period: item.period, value: item.cost, transactions: (item as CostPoint & { transactions?: number }).transactions }))
      : (raw as TrendPoint[]).map((item) => ({ period: item.period, value: item.revenue, transactions: item.transactions }));
    const costSeries = !isCost ? ((analytics.trend[`cost_${period}`] || []) as CostPoint[]) : [];
    line = costSeries.length ? new Map(costSeries.map((item) => [item.period, item.cost])) : null;
  }
  const title = isCost ? 'Cost trend' : line ? 'Revenue and cost' : 'Revenue trend';
  const allExcluded = analysableDatasets(datasets).length > 0;
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title" id="trend-title">{title}</h2>
          <p className="card-subtitle" id="trend-subtitle">{`Grouped by ${PERIOD_LABEL[period]}${analytics ? ` · ${plural(bars.length, 'period')}` : ''}`}</p>
        </div>
        <Segmented id="trend-periods" label="Trend grouping" options={PERIODS} value={period} onChange={onPeriod} />
      </div>
      <div className="card-body">
        {!hasData ? (
          <div className="chart" id="trend-chart">
            {allExcluded ? (
              <EmptyState
                title="Every file is switched off"
                message="Turn at least one file back on in Data imports to see your numbers."
                action={<Link className="btn btn-primary btn-sm" to={pagePath('data')}>Open data imports</Link>}
              />
            ) : (
              <EmptyState
                title="Your trend appears here"
                message="Import a sales file to see revenue over time."
                action={
                  <Link className="btn btn-primary btn-sm" to={pagePath('data')}>
                    <Icon name="upload" />
                    Import data
                  </Link>
                }
              />
            )}
          </div>
        ) : analytics ? (
          <BarChart className="chart" id="trend-chart" bars={bars} line={line} barLabel={isCost ? 'Cost' : 'Revenue'} lineLabel="Cost" />
        ) : (
          <div className="chart" id="trend-chart" />
        )}
        <div className="chart-legend" id="trend-legend">
          {hasData && analytics ? (
            <>
              <span>
                <i style={{ background: 'var(--chart-revenue)' }} />
                {isCost ? 'Cost' : 'Revenue'}
              </span>
              {line ? (
                <span>
                  <i style={{ background: 'var(--chart-cost)' }} />
                  Recorded cost
                </span>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/* ---------- Needs attention ---------- */
interface LossRow {
  product: string;
  gross_profit: number;
  revenue: number;
}

function attentionEntries(analytics: Analytics | undefined, insights: InsightsResponse | null, inventory: InventoryResponse | null, datasets: Dataset[]): AttentionEntry[] {
  const items: AttentionEntry[] = [];
  const lowStock = (inventory?.items || []).filter((item) => item.active && item.low_stock);
  lowStock.slice(0, 3).forEach((item) =>
    items.push({ tone: 'warning', icon: 'inventory', title: `${item.name} is low on stock`, detail: `${number(item.quantity_on_hand, 2)} ${item.unit} on hand · reorder at ${number(item.reorder_level, 2)}`, to: pagePath('inventory') }),
  );
  if (lowStock.length > 3) items.push({ tone: 'warning', icon: 'inventory', title: `${lowStock.length - 3} more products are low on stock`, to: pagePath('inventory') });
  const rankings = analytics?.products?.rankings as { loss?: LossRow[] } | undefined;
  (rankings?.loss || []).slice(0, 2).forEach((item) =>
    items.push({ tone: 'error', icon: 'trending-down', title: `${item.product} sold below cost`, detail: `Loss of ${money(Math.abs(item.gross_profit))} on ${money(item.revenue)} revenue`, to: pagePath('products') }),
  );
  (insights?.insights || [])
    .filter((item) => item.title === 'Product decline')
    .slice(0, 2)
    .forEach((item) => items.push({ tone: 'warning', icon: 'trending-down', title: item.message, to: pagePath('insights') }));
  if (insights?.revenue_change?.direction === 'down' && insights.revenue_change.percent !== null) {
    items.unshift({
      tone: 'warning',
      icon: 'trending-down',
      title: `Revenue fell ${Math.abs(insights.revenue_change.percent).toFixed(1)}% on the previous period`,
      detail: `${money(insights.revenue_change.current)} vs ${money(insights.revenue_change.previous)}`,
      to: pagePath('insights'),
    });
  }
  datasets
    .filter((item) => item.included && item.warnings.some((warning) => warning.includes('identical to')))
    .slice(0, 2)
    .forEach((item) => items.push({ tone: 'warning', icon: 'file', title: `${item.filename} may be a duplicate`, detail: 'Switch one copy off in Data imports to avoid double counting.', to: pagePath('data') }));
  datasets
    .filter((item) => item.status === 'partial' && item.included)
    .slice(0, 2)
    .forEach((item) => items.push({ tone: 'info', icon: 'file', title: `${plural(item.rejected_rows, 'row')} rejected in ${item.filename}`, detail: 'Every rejected row is listed with its reason.', to: pagePath('data') }));
  if (!items.length) items.push({ tone: 'ok', icon: 'check', title: 'Nothing needs attention right now', detail: 'No losses, declines, duplicate files or low stock detected.' });
  return items.slice(0, 6);
}

/* ---------- Rankings ---------- */
function Rankings({ analytics }: { analytics: Analytics | undefined }) {
  const isCost = analytics?.profile?.domain === 'cost';
  const products = analytics?.products;
  const customers = analytics?.customers;
  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title" id="top-title">{isCost ? 'Largest cost items' : 'Top products'}</h2>
            <p className="card-subtitle">Ranked by revenue in this period</p>
          </div>
          <Link className="btn btn-ghost btn-sm" to={pagePath('products')}>
            View all
            <IconSlot name="arrow-right" />
          </Link>
        </div>
        <div className="card-body flush">
          <ol className="rank-list" id="top-products">
            {!analytics ? (
              <li className="empty-state">Products appear once you import sales.</li>
            ) : products?.available ? (
              <RankItems
                items={products.items.slice(0, 5)}
                name={(item) => item.product}
                value={(item) => item.metric_value}
                total={isCost ? analytics.kpis.total_cost : analytics.kpis.total_revenue}
                sub={products.profit_available ? (item) => `${money(item.gross_profit, { compact: true })} profit · ${plainPercent(item.margin_pct)}` : undefined}
              />
            ) : (
              <li className="empty-state">{products?.reason || 'No product column found.'}</li>
            )}
          </ol>
        </div>
      </div>
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title" id="customers-title">{isCost ? 'Top suppliers' : 'Top customers'}</h2>
            <p className="card-subtitle" id="customers-subtitle">
              {customers?.available ? `${plural(customers.number_of_customers ?? 0, isCost ? 'supplier' : 'customer')} · ${number(customers.repeat_customers)} repeat` : 'Highest value relationships'}
            </p>
          </div>
        </div>
        <div className="card-body flush">
          <ol className="rank-list" id="top-customers">
            {!analytics ? (
              <li className="empty-state">Customers appear once you import sales.</li>
            ) : customers?.available ? (
              <RankItems items={customers.top_customers.slice(0, 5)} name={(item) => item.customer} value={(item) => item.metric_value} sub={(item) => plural(item.transactions, 'record')} />
            ) : (
              <li className="empty-state">{customers?.reason || 'No customer column found.'}</li>
            )}
          </ol>
        </div>
      </div>
    </div>
  );
}

/* ---------- Stock ---------- */
function StockStats({ inventory }: { inventory: InventoryResponse | null }) {
  const summary = inventory?.summary;
  if (!summary || !summary.product_count) {
    return (
      <div className="mini-stats" id="overview-stock" style={{ display: 'block' }}>
        <EmptyState
          title="No stock tracked yet"
          message="Add products in Inventory to get low-stock alerts."
          action={<Link className="btn btn-secondary btn-sm" to={pagePath('inventory')}>Set up inventory</Link>}
        />
      </div>
    );
  }
  const stats: [string, string][] = [
    ['Products', number(summary.product_count)],
    ['Units on hand', number(summary.units_on_hand, 2)],
    ['Low stock', number(summary.low_stock_count)],
    ['Stock value', summary.inventory_value_complete ? money(summary.inventory_value) : 'Needs unit costs'],
  ];
  return (
    <div className="mini-stats" id="overview-stock">
      {stats.map(([label, value]) => (
        <div className="mini-stat" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}
