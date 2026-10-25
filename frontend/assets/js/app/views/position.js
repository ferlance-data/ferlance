// Financial position: dated balances rolled into a point-in-time statement.

import { request } from '../api.js';
import { $, formatDate, h, icon, isoDate, kpi, money, mount, notice, pill, setStatus, table, toast } from '../dom.js';
import { POSITION_LABELS, printPositionReport } from '../reports.js';
import { businessPath, state } from '../state.js';

const GROUPS = {
  cash: 'Assets', bank: 'Assets', receivables: 'Assets', inventory: 'Assets', fixed_assets: 'Assets', other_assets: 'Assets',
  payables: 'Liabilities', loans: 'Liabilities', other_liabilities: 'Liabilities',
  owner_capital: 'Equity', retained_earnings: 'Equity', other_equity: 'Equity',
};
let report = null;

export const view = {
  title: 'Financial position',
  description: 'What the business owns and owes on any date, built from the balances you record.',
  scoped: false,
  actions: () => [h('button', { class: 'btn btn-secondary', type: 'button', onclick: () => report && printPositionReport(report) }, icon('printer'), h('span', { class: 'btn-label' }, 'Print statement'))],
  init,
  load,
};

function renderGroups(result) {
  mount($('#position-groups'), [['Assets', result.assets, result.totals.assets], ['Liabilities', result.liabilities, result.totals.liabilities], ['Equity', result.equity, result.totals.equity]].map(([title, items, total]) => h(
    'div',
    { class: 'card statement-group' },
    h('div', { class: 'card-header' }, h('h3', {}, title), h('span', { class: 'num' }, money(total))),
    h('div', { class: 'table-wrap', style: { marginTop: '8px' } }, table(
      [
        { label: 'Account', value: (item) => h('div', { class: 'file-cell' }, h('strong', {}, item.account_name), h('small', {}, POSITION_LABELS[item.category] || item.category)) },
        { label: 'Balance date', value: (item) => (item.as_of_date < result.as_of_date ? h('span', {}, formatDate(item.as_of_date), ' ', pill('Carried forward', 'warning')) : formatDate(item.as_of_date)) },
        { label: 'Balance', num: true, value: (item) => money(item.amount) },
      ],
      items,
      { empty: `No ${title.toLowerCase()} recorded on or before this date.` },
    )),
  )));
}

function render(result) {
  report = result;
  const totals = result.totals;
  mount($('#position-kpis'), [
    kpi({ label: 'Total assets', value: money(totals.assets), iconName: 'coins' }),
    kpi({ label: 'Total liabilities', value: money(totals.liabilities), iconName: 'receipt' }),
    kpi({ label: 'Equity', value: money(totals.equity), iconName: 'scale' }),
    kpi({ label: totals.complete ? 'Assets − liabilities − equity' : 'Known difference (partial)', value: money(totals.balance_difference), iconName: 'check' }),
  ]);
  mount($('#position-check'), totals.complete ? (totals.balanced ? pill('Statement balances', 'success', 'check') : pill('Does not balance', 'error', 'alert')) : pill('Partial statement', 'warning', 'alert'));
  const warnings = [];
  if (result.missing_categories.length) warnings.push(notice(`Missing categories: ${result.missing_categories.map((item) => item.label).join(', ')}. Record each, including zero balances, for a complete statement.`));
  if (result.stale_balances.length) warnings.push(notice(`${result.stale_balances.length} balance(s) are carried forward from earlier dates.`, 'warning', 'info'));
  mount($('#position-warnings'), warnings);
  renderGroups(result);
}

async function loadHistory() {
  const items = await request(businessPath('/financial-position/history'));
  state.setup.balances = items.length > 0;
  mount($('#position-history'), table(
    [
      { label: 'Balance date', value: (item) => formatDate(item.as_of_date) },
      { label: 'Account', value: (item) => item.account_name },
      { label: 'Category', value: (item) => `${GROUPS[item.category] || ''} · ${POSITION_LABELS[item.category] || item.category}` },
      { label: 'Balance', num: true, value: (item) => money(item.amount) },
      { label: 'Note', value: (item) => item.note || '—' },
      { label: 'Recorded by', value: (item) => item.recorded_by },
    ],
    items,
    { empty: 'No balances recorded yet. Start with cash on hand and your bank balance.' },
  ));
}

async function load() {
  const asOf = $('#position-date').value;
  const [result] = await Promise.all([request(businessPath(`/financial-position?as_of=${encodeURIComponent(asOf)}`)), loadHistory()]);
  render(result);
}

function init() {
  const today = isoDate(new Date());
  $('#position-date').value = today;
  $('#balance-date').value = today;
  mount($('#balance-category'), ['Assets', 'Liabilities', 'Equity'].map((group) => h('optgroup', { label: group }, Object.entries(POSITION_LABELS).filter(([key]) => GROUPS[key] === group).map(([key, label]) => h('option', { value: key }, label)))));
  $('#position-date').addEventListener('change', () => load().catch((error) => toast(error.message, { error: true })));
  $('#balance-category').addEventListener('change', (event) => {
    $('#balance-amount').min = GROUPS[event.target.value] === 'Equity' ? '' : '0';
  });
  $('#balance-category').dispatchEvent(new Event('change'));
  $('#balance-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = $('#balance-form button[type="submit"]');
    button.disabled = true;
    try {
      const saved = await request(businessPath('/financial-position/balances'), {
        method: 'POST',
        json: {
          as_of_date: $('#balance-date').value,
          category: $('#balance-category').value,
          account_name: $('#balance-account').value,
          amount: Number($('#balance-amount').value),
          note: $('#balance-note').value,
        },
      });
      ['#balance-account', '#balance-amount', '#balance-note'].forEach((selector) => { $(selector).value = ''; });
      if (saved.as_of_date > $('#position-date').value) $('#position-date').value = saved.as_of_date;
      await load();
      setStatus('#balance-status', `Saved ${POSITION_LABELS[saved.category]} for ${formatDate(saved.as_of_date)}.`);
    } catch (error) {
      setStatus('#balance-status', error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}
