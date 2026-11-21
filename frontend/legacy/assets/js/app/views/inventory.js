// Inventory: catalogue, auditable stock ledger, and stocktake imports.

import { request } from '../api.js';
import { $, bindTabs, formatDateTime, h, icon, kpi, money, mount, number, pill, setStatus, table, toast } from '../dom.js';
import { printInventoryReport } from '../reports.js';
import { businessPath, state } from '../state.js';

let movements = [];
let editing = null;

export const view = {
  title: 'Inventory',
  description: 'Track stock with an auditable ledger. Sales imports never change stock — only the movements you record here do.',
  scoped: false,
  actions: () => [h('button', { class: 'btn btn-secondary', type: 'button', onclick: () => state.inventory && printInventoryReport(state.inventory, movements) }, icon('printer'), h('span', { class: 'btn-label' }, 'Print report'))],
  init,
  load,
};

export async function loadInventorySummary() {
  state.inventory = await request(businessPath('/inventory?include_archived=true'));
  return state.inventory;
}

function renderKpis() {
  const summary = state.inventory.summary;
  mount($('#inventory-kpis'), [
    kpi({ label: 'Active products', value: number(summary.product_count), iconName: 'inventory' }),
    kpi({ label: 'Units on hand', value: number(summary.units_on_hand, 2), iconName: 'products' }),
    kpi({ label: 'Low stock', value: number(summary.low_stock_count), foot: summary.low_stock_count ? pill('Reorder soon', 'warning') : pill('All stocked', 'success'), iconName: 'alert' }),
    kpi({ label: 'Stock value', value: summary.inventory_value_complete ? money(summary.inventory_value) : 'Incomplete', text: !summary.inventory_value_complete, foot: summary.inventory_value_complete ? 'At recorded unit cost' : `${number(summary.uncosted_stock_items.length)} item(s) need a unit cost`, iconName: 'coins' }),
  ]);
}

function statusFor(item) {
  if (!item.active) return pill('Archived');
  return item.low_stock ? pill('Low stock', 'warning') : pill('In stock', 'success');
}

function renderTable() {
  const query = $('#inventory-search').value.trim().toLocaleLowerCase();
  const showArchived = $('#inventory-archived').checked;
  const rows = state.inventory.items.filter((item) => (showArchived || item.active) && `${item.name} ${item.sku || ''}`.toLocaleLowerCase().includes(query));
  mount($('#inventory-table'), table(
    [
      { label: 'Product', value: (item) => h('div', { class: 'file-cell' }, h('strong', {}, item.name), h('small', {}, [item.sku, item.unit].filter(Boolean).join(' · '))) },
      { label: 'On hand', num: true, value: (item) => number(item.quantity_on_hand, 3) },
      { label: 'Reorder at', num: true, value: (item) => number(item.reorder_level, 3) },
      { label: 'Unit cost', num: true, value: (item) => (item.unit_cost === null ? '—' : money(item.unit_cost)) },
      { label: 'Value', num: true, value: (item) => (item.stock_value === null ? '—' : money(item.stock_value)) },
      { label: 'Status', value: statusFor },
      {
        label: '',
        value: (item) => h(
          'div',
          { class: 'row-actions' },
          h('button', { class: 'btn btn-ghost btn-sm btn-icon', type: 'button', title: `Edit ${item.name}`, 'aria-label': `Edit ${item.name}`, onclick: () => startEdit(item) }, icon('edit')),
          h('button', { class: 'btn btn-ghost btn-sm btn-icon', type: 'button', title: item.active ? 'Archive' : 'Restore', 'aria-label': `${item.active ? 'Archive' : 'Restore'} ${item.name}`, onclick: () => setActive(item, !item.active) }, icon(item.active ? 'archive' : 'refresh')),
        ),
      },
    ],
    rows,
    { empty: query ? 'No products match your search.' : 'Add a product or import a stocktake to start tracking stock.' },
  ));
}

function renderMovementOptions() {
  const select = $('#movement-product');
  const previous = select.value;
  mount(select, state.inventory.items.filter((item) => item.active).map((item) => h('option', { value: item.id }, `${item.name} · ${number(item.quantity_on_hand, 3)} ${item.unit}`)));
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
  $('#movement-submit').disabled = !select.value;
}

function renderMovements() {
  mount($('#movements-table'), table(
    [
      { label: 'When', value: (item) => formatDateTime(item.created_at) },
      { label: 'Product', value: (item) => item.product_name },
      { label: 'Type', value: (item) => pill(item.movement_type, item.quantity_delta < 0 ? '' : 'info') },
      { label: 'Change', num: true, value: (item) => h('span', { class: item.quantity_delta < 0 ? 'negative' : 'positive' }, `${item.quantity_delta > 0 ? '+' : ''}${number(item.quantity_delta, 3)} ${item.unit}`) },
      { label: 'Note', value: (item) => item.note || '—' },
      { label: 'By', value: (item) => (item.source === 'manual' ? item.recorded_by : 'Stocktake import') },
    ],
    movements,
    { empty: 'No stock movements recorded yet.' },
  ));
}

function render() {
  renderKpis();
  renderTable();
  renderMovementOptions();
  renderMovements();
}

async function load() {
  const [, history] = await Promise.all([loadInventorySummary(), request(businessPath('/inventory/movements?limit=100'))]);
  movements = history;
  render();
}

function selectTab(name) {
  $(`#inventory-tabs [data-tab="${name}"]`).click();
}

function resetProductForm() {
  editing = null;
  $('#product-form').reset();
  $('#product-unit').value = 'unit';
  $('#product-reorder').value = '0';
  $('#product-opening').value = '0';
  $('#product-opening-field').hidden = false;
  $('#product-submit').textContent = 'Add product';
  $('#product-cancel').hidden = true;
}

function startEdit(item) {
  editing = item.id;
  selectTab('product');
  $('#product-name').value = item.name;
  $('#product-sku').value = item.sku || '';
  $('#product-unit').value = item.unit;
  $('#product-cost').value = item.unit_cost ?? '';
  $('#product-reorder').value = item.reorder_level;
  $('#product-opening-field').hidden = true;
  $('#product-submit').textContent = `Save ${item.name}`;
  $('#product-cancel').hidden = false;
  $('#product-name').focus();
}

async function setActive(item, active) {
  try {
    await request(businessPath(`/inventory/products/${item.id}`), { method: 'PATCH', json: { active } });
    toast(active ? `${item.name} restored.` : `${item.name} archived.`);
    await load();
  } catch (error) {
    toast(error.message, { error: true });
  }
}

async function guarded(button, statusMessage, task) {
  button.disabled = true;
  setStatus('#inventory-status', statusMessage);
  try {
    await task();
  } catch (error) {
    setStatus('#inventory-status', error.message, true);
  } finally {
    button.disabled = false;
  }
}

function init() {
  bindTabs($('#inventory-tabs'), $('[data-view="inventory"]'), () => setStatus('#inventory-status', ''));
  $('#inventory-search').addEventListener('input', renderTable);
  $('#inventory-archived').addEventListener('change', renderTable);
  $('#product-cancel').addEventListener('click', resetProductForm);
  $('#movement-type').addEventListener('change', (event) => {
    const adjustment = event.target.value === 'adjustment';
    $('#movement-quantity').min = adjustment ? '' : '0.000001';
    $('#movement-quantity').placeholder = adjustment ? 'Positive adds, negative removes' : 'Enter a positive quantity';
  });

  $('#product-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const cost = $('#product-cost').value;
    const body = {
      name: $('#product-name').value,
      sku: $('#product-sku').value || null,
      unit: $('#product-unit').value,
      unit_cost: cost === '' ? null : Number(cost),
      reorder_level: Number($('#product-reorder').value),
    };
    guarded($('#product-submit'), 'Saving…', async () => {
      const wasEditing = editing;
      await request(businessPath(wasEditing ? `/inventory/products/${wasEditing}` : '/inventory/products'), {
        method: wasEditing ? 'PATCH' : 'POST',
        json: wasEditing ? body : { ...body, opening_stock: Number($('#product-opening').value) },
      });
      resetProductForm();
      await load();
      setStatus('#inventory-status', wasEditing ? 'Product saved.' : 'Product added.');
    });
  });

  $('#movement-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const productId = $('#movement-product').value;
    guarded($('#movement-submit'), 'Recording…', async () => {
      const result = await request(businessPath(`/inventory/products/${productId}/movements`), {
        method: 'POST',
        json: { movement_type: $('#movement-type').value, quantity: Number($('#movement-quantity').value), note: $('#movement-note').value },
      });
      $('#movement-quantity').value = '';
      $('#movement-note').value = '';
      await load();
      $('#movement-product').value = productId;
      setStatus('#inventory-status', `${result.name}: ${number(result.quantity_on_hand, 3)} ${result.unit} on hand.`);
    });
  });

  $('#stocktake-file').addEventListener('change', () => {
    $('#stocktake-submit').disabled = !$('#stocktake-file').files.length;
  });
  $('#stocktake-template').addEventListener('click', (event) => {
    event.preventDefault();
    const url = URL.createObjectURL(new Blob(['product,sku,unit,quantity_on_hand,unit_cost,reorder_level\n'], { type: 'text/csv;charset=utf-8' }));
    const link = h('a', { href: url, download: 'inventory-stocktake-template.csv' });
    link.click();
    URL.revokeObjectURL(url);
  });
  $('#stocktake-form').addEventListener('submit', (event) => {
    event.preventDefault();
    const file = $('#stocktake-file').files[0];
    if (!file) return;
    guarded($('#stocktake-submit'), 'Reconciling counted stock…', async () => {
      const body = new FormData();
      body.append('file', file);
      const result = await request(businessPath('/inventory/import'), { method: 'POST', body });
      $('#stocktake-form').reset();
      await load();
      setStatus('#inventory-status', `Stocktake imported: ${result.created} created, ${result.updated} updated, ${result.rows_imported} rows reconciled.`);
    });
  });
}
