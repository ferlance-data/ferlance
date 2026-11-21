import { useState } from 'react';
import { Link } from 'react-router';
import { money, number, plainPercent, setCurrency } from '../../lib/format';
import { IconSlot } from '../../lib/icons';
import type { Analytics, ProductRow } from '../../lib/types';
import { DataTable, EmptyState, Segmented, SkeletonRows, type Column, type SortState } from '../components/ui';
import { useScopedQuery } from '../hooks';
import { pagePath } from '../routes';
import { useScope } from '../workspace';
import { deriveProducts, nextSort, shareOf, type ProductFilter } from './products.logic';

const FILTERS: { value: ProductFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'profit', label: 'Profitable' },
  { value: 'loss', label: 'Losing money' },
];

export default function Products() {
  const { hasData } = useScope();
  const query = useScopedQuery<Analytics>('/analytics', { updatesBounds: true, enabled: hasData });
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<ProductFilter>('all');
  const [sort, setSort] = useState<SortState>({ key: 'metric_value', dir: 'desc' });
  const analytics = hasData ? query.data : undefined;
  if (analytics) setCurrency(analytics.currency);
  const products = analytics?.products;
  const derived = products?.available ? deriveProducts(products.items, search, filter, sort) : null;

  return (
    <>
      <div className="card">
        <div className="toolbar">
          <label className="search">
            <IconSlot name="search" />
            <input className="input" id="products-search" type="search" placeholder="Search products" aria-label="Search products" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <Segmented id="products-filter" label="Filter products" options={FILTERS} value={filter} onChange={setFilter} />
          <span className="toolbar-meta muted" id="products-count">
            {products?.available && derived ? `${number(derived.rows.length)} of ${number(products.items.length)}` : ''}
          </span>
        </div>
        <div className="table-wrap" id="products-table">
          {!hasData ? (
            <EmptyState
              title="No products yet"
              message="Import a sales file with a product column."
              action={
                <Link className="btn btn-primary btn-sm" to={pagePath('data')}>
                  Import data
                </Link>
              }
            />
          ) : !analytics ? (
            <div style={{ padding: '8px 14px' }}>
              <SkeletonRows count={6} />
            </div>
          ) : !products?.available || !derived ? (
            <EmptyState title="No products found" message={products?.reason || 'Add a product, item or service column to your imports.'} />
          ) : (
            <>
              <DataTable
                columns={columnsFor(analytics, derived.total)}
                rows={derived.rows}
                rowKey={(item) => item.product}
                empty={search.trim() || filter !== 'all' ? 'No products match.' : 'No products in this period.'}
                sortState={sort}
                onSort={(key) => setSort((current) => nextSort(current, key))}
              />
              {!products.profit_available && analytics.profile?.domain !== 'cost' ? (
                <p className="footnote" style={{ padding: '10px 14px' }}>
                  Profit, margin and ROI appear when every product record includes a cost or unit cost.
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>
      <p className="footnote">Products are recognised from the product, item or service column of your imports. Stock levels live in Inventory and are never inferred from sales files.</p>
    </>
  );
}

function columnsFor(analytics: Analytics, total: number): Column<ProductRow>[] {
  const { products } = analytics;
  const profitable = Boolean(products.profit_available);
  const columns: (Column<ProductRow> | null)[] = [
    {
      label: 'Product',
      sort: 'product',
      value: (item) => {
        const share = shareOf(item, total);
        return (
          <div className="rank-name">
            <strong>{item.product}</strong>
            <span className="share-bar" title={`${share.percent.toFixed(1)}% of total`}>
              <i style={{ width: `${share.width}%` }} />
            </span>
          </div>
        );
      },
    },
    { label: products.metric_label ?? '', num: true, sort: 'metric_value', value: (item) => money(item.metric_value) },
    profitable ? { label: 'Cost', num: true, sort: 'cost', value: (item) => money(item.cost) } : null,
    profitable ? { label: 'Profit / loss', num: true, sort: 'gross_profit', value: (item) => <span className={(item.gross_profit ?? 0) < 0 ? 'negative' : ''}>{money(item.gross_profit)}</span> } : null,
    profitable ? { label: 'Margin', num: true, sort: 'margin_pct', value: (item) => plainPercent(item.margin_pct) } : null,
    profitable ? { label: 'ROI', num: true, sort: 'roi_pct', value: (item) => plainPercent(item.roi_pct) } : null,
    products.quantity_available ? { label: 'Units', num: true, sort: 'units_sold', value: (item) => number(item.units_sold, 2) } : null,
    { label: 'Records', num: true, sort: 'transactions', value: (item) => number(item.transactions) },
  ];
  return columns.filter((column): column is Column<ProductRow> => column !== null);
}
