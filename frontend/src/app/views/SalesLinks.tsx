// Inventory ↔ sales: link the names used in sales files to stock products, and see what the
// last stocktake found. Posting a file's sales to stock lives on the Data page.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { money, number } from '../../lib/format';
import { request } from '../../lib/api';
import { toast } from '../../lib/toast';
import type { InventoryItem } from '../../lib/types';
import { DataTable, Pill, type Column } from '../components/ui';
import { useWorkspace } from '../workspace';

interface SalesName {
  sales_name: string;
  units: number;
  lines: number;
  missing_quantity: number;
  product_id: string | null;
  status: 'matched' | 'linked' | 'ignored' | 'unlinked';
  suggestion: { product_id: string; name: string } | null;
}

interface Variance {
  id: string;
  name: string;
  variance: number;
  value: number | null;
  created_at: string;
}

const IGNORE = '__ignore__';
const STATUS: Record<SalesName['status'], [string, 'success' | 'info' | '' | 'warning']> = {
  matched: ['Same name', 'success'],
  linked: ['Linked', 'info'],
  ignored: ['Not stock', ''],
  unlinked: ['Not linked', 'warning'],
};

export function SalesLinks({ products }: { products: InventoryItem[] }) {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const key = ['links', business.id];
  const query = useQuery({ queryKey: key, queryFn: ({ signal }) => request<{ names: SalesName[]; unlinked: number }>(businessPath('/inventory/links'), { signal }) });
  const editable = can('write_data');

  async function save(row: SalesName, value: string) {
    try {
      await request(businessPath('/inventory/links'), {
        method: 'PUT',
        json: value === IGNORE ? { sales_name: row.sales_name, ignore: true } : { sales_name: row.sales_name, product_id: value || null },
      });
      await queryClient.invalidateQueries({ queryKey: key });
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  const rows = query.data?.names ?? [];
  if (!rows.length) return null;
  const columns: Column<SalesName>[] = [
    {
      label: 'Name in your sales',
      value: (row) => (
        <div className="file-cell">
          <strong>{row.sales_name}</strong>
          <small>{row.missing_quantity ? `${number(row.units)} units · ${number(row.missing_quantity)} line(s) without a quantity` : `${number(row.units)} units sold`}</small>
        </div>
      ),
    },
    {
      label: 'Status',
      value: (row) => {
        const [label, tone] = STATUS[row.status];
        return <Pill tone={tone}>{label}</Pill>;
      },
    },
    {
      label: 'Stock product',
      value: (row) => (
        <select
          className="select"
          aria-label={`Stock product for ${row.sales_name}`}
          disabled={!editable}
          value={row.status === 'ignored' ? IGNORE : row.product_id ?? ''}
          onChange={(event) => void save(row, event.target.value)}
        >
          <option value="">{row.suggestion ? `Choose… (maybe ${row.suggestion.name})` : 'Choose…'}</option>
          {products.map((item) => (
            <option key={item.id} value={item.id}>
              {item.active ? item.name : `${item.name} (archived)`}
            </option>
          ))}
          <option value={IGNORE}>Not a stock item</option>
        </select>
      ),
    },
  ];

  return (
    <div className="card" id="sales-links">
      <div className="card-header">
        <div>
          <h2 className="card-title">Link sales to stock</h2>
          <p className="card-subtitle">
            {query.data?.unlinked
              ? `${number(query.data.unlinked)} name(s) in your sales are not linked to a stock product yet`
              : 'Every name in your sales is linked, matched or marked as not stock'}
          </p>
        </div>
      </div>
      <div className="table-wrap">
        <DataTable columns={columns} rows={rows} rowKey={(row) => row.sales_name} />
      </div>
      <p className="footnote card-body">Linked sales count towards stock advice. To take a file's sales out of stock, use “Post to stock” on Data imports.</p>
    </div>
  );
}

export function Reconciliation() {
  const { business, businessPath } = useWorkspace();
  const query = useQuery({ queryKey: ['reconciliation', business.id], queryFn: ({ signal }) => request<Variance[]>(businessPath('/inventory/reconciliation'), { signal }) });
  const rows = (query.data ?? []).filter((row) => row.variance !== 0);
  if (!rows.length) return null;
  const columns: Column<Variance>[] = [
    { label: 'Product', value: (row) => <strong>{row.name}</strong> },
    { label: 'Counted vs records', num: true, value: (row) => `${row.variance > 0 ? '+' : ''}${number(row.variance, 2)}` },
    { label: 'Value', num: true, value: (row) => (row.value === null ? '—' : money(row.value)) },
  ];
  return (
    <div className="card" id="reconciliation">
      <div className="card-header">
        <div>
          <h2 className="card-title">Last stocktake differences</h2>
          <p className="card-subtitle">Where the shelf count did not match the records. Shortfalls can mean theft, waste or unrecorded sales.</p>
        </div>
      </div>
      <div className="table-wrap">
        <DataTable columns={columns} rows={rows} rowKey={(row) => row.id} />
      </div>
    </div>
  );
}
