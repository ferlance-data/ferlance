// Inventory: catalogue, auditable stock ledger, and stocktake imports.

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDateTime, money, number } from '../../lib/format';
import { Icon, IconSlot } from '../../lib/icons';
import { printInventoryReport } from '../../lib/reports';
import { toast } from '../../lib/toast';
import type { InventoryItem, Movement } from '../../lib/types';
import { useBusinessQuery } from '../hooks';
import { DataTable, Kpi, ListHeader, Modal, Pill, Segmented, StatusText, ReadOnlyNotice } from '../components/ui';
import { PageActions } from '../page';
import { Reconciliation, SalesLinks } from './SalesLinks';
import { ScanInvoice } from './ScanInvoice';
import { keys, useWorkspace } from '../workspace';
import { buildStocktakeTemplate, filterProducts, resolveSelectedProduct, STOCKTAKE_TEMPLATE_FILENAME } from './inventory.logic';

type Tab = 'movement' | 'product' | 'stocktake' | 'scan';
type Busy = Tab | null;

interface ProductForm {
  name: string;
  sku: string;
  unit: string;
  cost: string;
  reorder: string;
  opening: string;
}

interface StocktakeResult {
  created: number;
  updated: number;
  rows_imported: number;
}

const EMPTY_PRODUCT: ProductForm = { name: '', sku: '', unit: 'unit', cost: '', reorder: '0', opening: '0' };

function ItemStatus({ item }: { item: InventoryItem }) {
  if (!item.active) return <Pill>Archived</Pill>;
  return item.low_stock ? <Pill tone="warning">Low stock</Pill> : <Pill tone="success">In stock</Pill>;
}

function downloadTemplate() {
  const url = URL.createObjectURL(new Blob([buildStocktakeTemplate()], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = STOCKTAKE_TEMPLATE_FILENAME;
  link.click();
  URL.revokeObjectURL(url);
}

/** Who or what recorded a movement, from its source. */
export function movementSource(source: string, recordedBy: string | null | undefined): string {
  if (source === 'manual') return recordedBy || 'Manual';
  if (source === 'capture') return 'Scanned invoice';
  if (source.startsWith('sales-reversal:')) return 'Sales file left out';
  if (source.startsWith('sales:')) return 'Sales file';
  return 'Stocktake import';
}

export default function Inventory() {
  const { user, business, businessPath, inventory, refreshInventory, can, role } = useWorkspace();
  const canWrite = can('write_data');
  const queryClient = useQueryClient();
  const movementsQuery = useBusinessQuery<Movement[]>('/inventory/movements?limit=100');
  // The summary lives in the workspace (it outlives this page): re-read it on every visit.
  useEffect(() => {
    void queryClient.invalidateQueries({ queryKey: keys.inventory(business.id) });
  }, [queryClient, business.id]);
  const movements = movementsQuery.data ?? [];

  const [search, setSearch] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [tab, setTab] = useState<Tab>('movement');
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<{ message: string; error: boolean }>({ message: '', error: false });
  const [busy, setBusy] = useState<Busy>(null);

  const [chosenProduct, setChosenProduct] = useState('');
  const [movementType, setMovementType] = useState('purchase');
  const [quantity, setQuantity] = useState('');
  const [note, setNote] = useState('');

  const [editing, setEditing] = useState<string | null>(null);
  const [editingName, setEditingName] = useState('');
  const [product, setProduct] = useState<ProductForm>(EMPTY_PRODUCT);
  const nameRef = useRef<HTMLInputElement>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const [hasFile, setHasFile] = useState(false);

  const items = inventory?.items ?? [];
  const activeItems = items.filter((item) => item.active);
  const productId = resolveSelectedProduct(items, chosenProduct);
  const adjustment = movementType === 'adjustment';

  const reload = async () => {
    await Promise.all([refreshInventory(), queryClient.invalidateQueries({ queryKey: keys.business(business.id) })]);
  };

  const showStatus = (message: string, error = false) => setStatus({ message, error });

  const guarded = async (form: Tab, message: string, task: () => Promise<void>) => {
    setBusy(form);
    showStatus(message);
    try {
      await task();
    } catch (error) {
      showStatus(error instanceof Error ? error.message : 'Request failed.', true);
    } finally {
      setBusy(null);
    }
  };

  const changeTab = (next: Tab) => {
    setTab(next);
    showStatus('');
  };

  const openAction = (next: Tab) => {
    if (next === 'product') resetProductForm();
    changeTab(next);
    setOpen(true);
  };

  const done = async (message: string) => {
    toast(message);
    setOpen(false);
    showStatus('');
  };

  const resetProductForm = () => {
    setEditing(null);
    setProduct(EMPTY_PRODUCT);
  };

  const startEdit = (item: InventoryItem) => {
    setEditing(item.id);
    setEditingName(item.name);
    setProduct({
      ...EMPTY_PRODUCT,
      name: item.name,
      sku: item.sku || '',
      unit: item.unit,
      cost: item.unit_cost === null ? '' : String(item.unit_cost),
      reorder: String(item.reorder_level ?? ''),
    });
    changeTab('product');
    setOpen(true);
    // Focus once the modal has rendered the product form.
    requestAnimationFrame(() => nameRef.current?.focus());
  };

  const setActive = async (item: InventoryItem, active: boolean) => {
    try {
      await request(businessPath(`/inventory/products/${item.id}`), { method: 'PATCH', json: { active } });
      toast(active ? `${item.name} restored.` : `${item.name} archived.`);
      await reload();
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Request failed.', { error: true });
    }
  };

  const submitProduct = (event: FormEvent) => {
    event.preventDefault();
    const body = {
      name: product.name,
      sku: product.sku || null,
      unit: product.unit,
      unit_cost: product.cost === '' ? null : Number(product.cost),
      reorder_level: Number(product.reorder),
    };
    void guarded('product', 'Saving…', async () => {
      const wasEditing = editing;
      await request(businessPath(wasEditing ? `/inventory/products/${wasEditing}` : '/inventory/products'), {
        method: wasEditing ? 'PATCH' : 'POST',
        json: wasEditing ? body : { ...body, opening_stock: Number(product.opening) },
      });
      resetProductForm();
      await reload();
      await done(wasEditing ? 'Product saved.' : 'Product added.');
    });
  };

  const submitMovement = (event: FormEvent) => {
    event.preventDefault();
    void guarded('movement', 'Recording…', async () => {
      const result = await request<InventoryItem>(businessPath(`/inventory/products/${productId}/movements`), {
        method: 'POST',
        json: { movement_type: movementType, quantity: Number(quantity), note },
      });
      setQuantity('');
      setNote('');
      setChosenProduct(productId);
      await reload();
      await done(`${result.name}: ${number(result.quantity_on_hand, 3)} ${result.unit} on hand.`);
    });
  };

  const submitStocktake = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    void guarded('stocktake', 'Reconciling counted stock…', async () => {
      const body = new FormData();
      body.append('file', file);
      const result = await request<StocktakeResult>(businessPath('/inventory/import'), { method: 'POST', body });
      form.reset();
      setHasFile(false);
      await reload();
      await done(`Stocktake imported: ${result.created} created, ${result.updated} updated, ${result.rows_imported} rows reconciled.`);
    });
  };

  const setField = (field: keyof ProductForm) => (event: { target: { value: string } }) =>
    setProduct((current) => ({ ...current, [field]: event.target.value }));

  const query = search.trim();
  const rows = inventory ? filterProducts(items, search, showArchived) : [];
  const summary = inventory?.summary;

  return (
    <>
      <PageActions>
        <button
          className="btn btn-secondary"
          type="button"
          onClick={() => inventory && printInventoryReport(inventory, movements, { business, user })}
        >
          <Icon name="printer" />
          <span className="btn-label">Print report</span>
        </button>
      </PageActions>

      <div className="kpi-grid" id="inventory-kpis">
        {summary ? (
          <>
            <Kpi label="Active products" value={number(summary.product_count)} icon="inventory" />
            <Kpi label="Units on hand" value={number(summary.units_on_hand, 2)} icon="products" />
            <Kpi
              label="Low stock"
              value={number(summary.low_stock_count)}
              foot={summary.low_stock_count ? <Pill tone="warning">Reorder soon</Pill> : <Pill tone="success">All stocked</Pill>}
              icon="alert"
            />
            <Kpi
              label="Stock value"
              value={summary.inventory_value_complete ? money(summary.inventory_value) : 'Incomplete'}
              text={!summary.inventory_value_complete}
              foot={
                summary.inventory_value_complete
                  ? 'At recorded unit cost'
                  : `${number(summary.uncosted_stock_items.length)} item(s) need a unit cost`
              }
              icon="coins"
            />
          </>
        ) : null}
      </div>

      <ListHeader title="Products" action={canWrite ? 'Add product' : undefined} onAction={() => openAction('product')}>
        {canWrite ? (
          <>
            <button className="btn btn-secondary" type="button" onClick={() => openAction('movement')}>
              Stock in / out
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => openAction('scan')}>
              Scan invoice
            </button>
            <button className="btn btn-ghost" type="button" onClick={() => openAction('stocktake')}>
              Stocktake
            </button>
          </>
        ) : null}
      </ListHeader>
      {!canWrite ? <ReadOnlyNotice role={role} what="stock" /> : null}
      {open ? (
        <Modal label="Stock" onClose={() => setOpen(false)}>
          <div className="card">
            <div className="card-header">
              <Segmented
                mode="tabs"
                id="inventory-tabs"
                label="Inventory actions"
                value={tab}
                onChange={changeTab}
                options={[
                  { value: 'movement', label: 'Record movement' },
                  { value: 'product', label: 'Add product' },
                  { value: 'stocktake', label: 'Stocktake' },
                  { value: 'scan', label: 'Scan invoice' },
                ]}
              />
            </div>
            <div className="card-body">
              {canWrite ? (
                <>
                  <form
                    className="form-grid"
                    id="movement-form"
                    data-panel="movement"
                    hidden={tab !== 'movement'}
                    onSubmit={submitMovement}
                  >
                    <label className="field">
                      Product
                      <select
                        className="select"
                        id="movement-product"
                        required
                        value={productId}
                        onChange={(event) => setChosenProduct(event.target.value)}
                      >
                        {activeItems.map((item) => (
                          <option key={item.id} value={item.id}>{`${item.name} · ${number(item.quantity_on_hand, 3)} ${item.unit}`}</option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      Type
                      <select
                        className="select"
                        id="movement-type"
                        value={movementType}
                        onChange={(event) => setMovementType(event.target.value)}
                      >
                        <option value="purchase">Stock received / purchase</option>
                        <option value="sale">Sale / stock issued</option>
                        <option value="adjustment">Adjustment (+/−)</option>
                      </select>
                    </label>
                    <label className="field">
                      Quantity
                      <input
                        className="input"
                        id="movement-quantity"
                        type="number"
                        min={adjustment ? undefined : '0.000001'}
                        step="any"
                        required
                        placeholder={adjustment ? 'Positive adds, negative removes' : 'Enter a positive quantity'}
                        value={quantity}
                        onChange={(event) => setQuantity(event.target.value)}
                      />
                    </label>
                    <label className="field">
                      Note <span className="field-hint">Supplier, reference or reason</span>
                      <input
                        className="input"
                        id="movement-note"
                        maxLength={500}
                        value={note}
                        onChange={(event) => setNote(event.target.value)}
                      />
                    </label>
                    <button className="btn btn-primary" id="movement-submit" type="submit" disabled={!productId || busy === 'movement'}>
                      Record movement
                    </button>
                  </form>

                  <form className="form-grid" id="product-form" data-panel="product" hidden={tab !== 'product'} onSubmit={submitProduct}>
                    <label className="field">
                      Product name
                      <input
                        className="input"
                        id="product-name"
                        ref={nameRef}
                        maxLength={200}
                        required
                        value={product.name}
                        onChange={setField('name')}
                      />
                    </label>
                    <div className="form-row">
                      <label className="field">
                        SKU
                        <input
                          className="input"
                          id="product-sku"
                          maxLength={100}
                          placeholder="Optional"
                          value={product.sku}
                          onChange={setField('sku')}
                        />
                      </label>
                      <label className="field">
                        Unit
                        <input
                          className="input"
                          id="product-unit"
                          maxLength={40}
                          required
                          value={product.unit}
                          onChange={setField('unit')}
                        />
                      </label>
                    </div>
                    <div className="form-row">
                      <label className="field">
                        Unit cost
                        <input
                          className="input"
                          id="product-cost"
                          type="number"
                          min="0"
                          step="0.01"
                          placeholder="Optional"
                          value={product.cost}
                          onChange={setField('cost')}
                        />
                      </label>
                      <label className="field">
                        Reorder level
                        <input
                          className="input"
                          id="product-reorder"
                          type="number"
                          min="0"
                          step="any"
                          required
                          value={product.reorder}
                          onChange={setField('reorder')}
                        />
                      </label>
                    </div>
                    <label className="field" id="product-opening-field" hidden={editing !== null}>
                      Opening stock
                      <input
                        className="input"
                        id="product-opening"
                        type="number"
                        min="0"
                        step="any"
                        value={product.opening}
                        onChange={setField('opening')}
                      />
                    </label>
                    <div className="button-row">
                      <button className="btn btn-primary" id="product-submit" type="submit" disabled={busy === 'product'}>
                        {editing ? `Save ${editingName}` : 'Add product'}
                      </button>
                      <button
                        className="btn btn-ghost"
                        id="product-cancel"
                        type="button"
                        hidden={editing === null}
                        onClick={resetProductForm}
                      >
                        Cancel edit
                      </button>
                    </div>
                  </form>

                  <form
                    className="form-grid"
                    id="stocktake-form"
                    data-panel="stocktake"
                    hidden={tab !== 'stocktake'}
                    onSubmit={submitStocktake}
                  >
                    <p className="body-sm muted">
                      Upload a counted stock CSV to create products or reconcile on-hand quantities. Each difference is recorded as an
                      auditable movement. Sales files never change stock.
                    </p>
                    <a
                      className="btn btn-ghost btn-sm"
                      id="stocktake-template"
                      href="#"
                      onClick={(event) => {
                        event.preventDefault();
                        downloadTemplate();
                      }}
                    >
                      <IconSlot name="download" />
                      Download CSV template
                    </a>
                    <label className="field">
                      Stocktake CSV
                      <input
                        className="input"
                        id="stocktake-file"
                        ref={fileRef}
                        type="file"
                        accept=".csv"
                        required
                        onChange={() => setHasFile(Boolean(fileRef.current?.files?.length))}
                      />
                    </label>
                    <button className="btn btn-primary" id="stocktake-submit" type="submit" disabled={!hasFile || busy === 'stocktake'}>
                      Import counted stock
                    </button>
                  </form>
                  <ScanInvoice
                    hidden={tab !== 'scan'}
                    products={items}
                    onApplied={async () => {
                      await refreshInventory();
                      setOpen(false);
                    }}
                  />
                </>
              ) : (
                <ReadOnlyNotice role={role} what="stock" />
              )}
              <StatusText id="inventory-status" message={status.message} error={status.error} />
            </div>
          </div>
        </Modal>
      ) : null}
      <div>
        <div className="card">
          <div className="toolbar">
            <label className="search">
              <IconSlot name="search" />
              <input
                className="input"
                id="inventory-search"
                type="search"
                placeholder="Search name or SKU"
                aria-label="Search inventory"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <label className="checkbox">
              <input
                id="inventory-archived"
                type="checkbox"
                checked={showArchived}
                onChange={(event) => setShowArchived(event.target.checked)}
              />
              Show archived
            </label>
          </div>
          <div className="table-wrap" id="inventory-table">
            {inventory ? (
              <DataTable
                columns={[
                  {
                    label: 'Product',
                    value: (item) => (
                      <div className="file-cell">
                        <strong>{item.name}</strong>
                        <small>{[item.sku, item.unit].filter(Boolean).join(' · ')}</small>
                      </div>
                    ),
                  },
                  { label: 'On hand', num: true, value: (item) => number(item.quantity_on_hand, 3) },
                  { label: 'Reorder at', num: true, value: (item) => number(item.reorder_level, 3) },
                  { label: 'Unit cost', num: true, value: (item) => (item.unit_cost === null ? '—' : money(item.unit_cost)) },
                  { label: 'Value', num: true, value: (item) => (item.stock_value === null ? '—' : money(item.stock_value)) },
                  { label: 'Status', value: (item) => <ItemStatus item={item} /> },
                  {
                    label: '',
                    value: (item) => (
                      <div className="row-actions" hidden={!canWrite}>
                        <button
                          className="btn btn-ghost btn-sm btn-icon"
                          type="button"
                          title={`Edit ${item.name}`}
                          aria-label={`Edit ${item.name}`}
                          onClick={() => startEdit(item)}
                        >
                          <Icon name="edit" />
                        </button>
                        <button
                          className="btn btn-ghost btn-sm btn-icon"
                          type="button"
                          title={item.active ? 'Archive' : 'Restore'}
                          aria-label={`${item.active ? 'Archive' : 'Restore'} ${item.name}`}
                          onClick={() => void setActive(item, !item.active)}
                        >
                          <Icon name={item.active ? 'archive' : 'refresh'} />
                        </button>
                      </div>
                    ),
                  },
                ]}
                rows={rows}
                rowKey={(item) => item.id}
                empty={query ? 'No products match your search.' : 'Add a product or import a stocktake to start tracking stock.'}
              />
            ) : null}
          </div>
        </div>
      </div>

      <SalesLinks products={items} />
      <Reconciliation />

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Stock movements</h2>
            <p className="card-subtitle">Opening stock, purchases, sales, adjustments and stocktakes — kept for audit</p>
          </div>
        </div>
        <div className="table-wrap" id="movements-table">
          {movementsQuery.data ? (
            <DataTable
              columns={[
                { label: 'When', value: (item) => formatDateTime(item.created_at) },
                { label: 'Product', value: (item) => item.product_name },
                { label: 'Type', value: (item) => <Pill tone={item.quantity_delta < 0 ? '' : 'info'}>{item.movement_type}</Pill> },
                {
                  label: 'Change',
                  num: true,
                  value: (item) => (
                    <span
                      className={item.quantity_delta < 0 ? 'negative' : 'positive'}
                    >{`${item.quantity_delta > 0 ? '+' : ''}${number(item.quantity_delta, 3)} ${item.unit}`}</span>
                  ),
                },
                { label: 'Note', value: (item) => item.note || '—' },
                { label: 'By', value: (item) => movementSource(item.source, item.recorded_by) },
              ]}
              rows={movements}
              rowKey={(item) => item.id}
              empty="No stock movements recorded yet."
            />
          ) : null}
        </div>
      </div>
    </>
  );
}
