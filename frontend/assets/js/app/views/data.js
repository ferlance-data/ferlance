// Data imports: file uploads, Mobile Money SMS, and the import history with
// per-file inclusion switches.

import { request } from '../api.js';
import { $, bindTabs, formatDateTime, h, money, mount, number, plural, setStatus, table, toast } from '../dom.js';
import { businessPath, setScope, state } from '../state.js';
import { statusPill } from './shared.js';

export const view = {
  title: 'Data imports',
  description: 'Bring in sales, cost and Mobile Money records. Every file is checked row by row, and nothing is dropped without a reason.',
  scoped: false,
  init,
  load,
};

let onDatasetsChanged = () => {};
export const setDatasetsListener = (listener) => { onDatasetsChanged = listener; };

export async function loadDatasets() {
  state.datasets = await request(businessPath('/datasets'));
  onDatasetsChanged();
  return state.datasets;
}

function renderResult(dataset, extra = null) {
  const failed = dataset.status === 'failed';
  const title = failed ? 'This file could not be imported' : dataset.status === 'partial' ? 'Imported with some rows rejected' : 'Every row imported';
  const messages = [...(dataset.errors || [])];
  mount(
    $('#import-result'),
    h(
      'div',
      { class: 'import-result' },
      h('div', { class: 'import-result-head' }, h('strong', {}, title), statusPill(dataset)),
      h('div', { class: 'import-counts' }, [['Rows found', dataset.source_rows], ['Accepted', dataset.accepted_rows], ['Rejected', dataset.rejected_rows]].map(([label, value]) => h('div', {}, h('span', {}, label), h('strong', {}, number(value))))),
      extra,
      messages.map((message) => h('div', { class: 'notice notice-error' }, message)),
      dataset.warnings?.length ? h('details', { class: 'import-warnings', open: dataset.warnings.length <= 5 }, h('summary', {}, `Notes and rejected rows (${dataset.warnings.length})`), h('ul', {}, dataset.warnings.slice(0, 200).map((warning) => h('li', {}, warning)))) : null,
      failed ? null : h('div', { class: 'button-row' }, h('a', { class: 'btn btn-primary btn-sm', href: '#overview' }, 'See the overview'), h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => { setScope({ datasetId: dataset.id }); window.location.hash = 'overview'; } }, 'View only this file')),
    ),
  );
}

async function toggleIncluded(dataset, included) {
  try {
    await request(businessPath(`/datasets/${dataset.id}`), { method: 'PATCH', json: { included } });
    await loadDatasets();
    render();
    toast(included ? `${dataset.filename} is back in your numbers.` : `${dataset.filename} is now left out of business-wide numbers.`);
  } catch (error) {
    toast(error.message, { error: true });
    render();
  }
}

function render() {
  mount($('#imports-table'), table(
    [
      { label: 'File', value: (item) => h('div', { class: 'file-cell' }, h('strong', {}, item.filename), h('small', {}, `${item.extension.replace('.', '').toUpperCase()} · ${formatDateTime(item.created_at)}`)) },
      { label: 'Status', value: (item) => statusPill(item) },
      { label: 'Rows', num: true, value: (item) => number(item.source_rows) },
      { label: 'Accepted', num: true, value: (item) => number(item.accepted_rows) },
      { label: 'Notes', value: (item) => (item.warnings.length || item.errors.length ? h('button', { class: 'btn btn-ghost btn-sm', type: 'button', onclick: () => { renderResult(item); $('#import-result').scrollIntoView({ behavior: 'smooth', block: 'center' }); } }, plural(item.warnings.length + item.errors.length, 'note')) : '—') },
      {
        label: 'In analysis',
        value: (item) => (item.status === 'failed'
          ? h('span', { class: 'muted body-sm' }, 'Not usable')
          : h('label', { class: 'switch', title: item.included ? 'Included in business-wide numbers' : 'Left out of business-wide numbers' }, h('input', { type: 'checkbox', checked: item.included, 'aria-label': `Include ${item.filename} in analysis`, onchange: (event) => toggleIncluded(item, event.target.checked) }), h('span', {}))),
      },
    ],
    state.datasets,
    { empty: 'No imports yet. Upload a spreadsheet or paste Mobile Money alerts to begin.' },
  ));
}

async function load() {
  await loadDatasets();
  render();
}

function chooseFile(file) {
  $('#upload-filename').textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB` : '';
  $('#upload-submit').disabled = !file;
}

function init() {
  bindTabs($('#import-tabs'), $('[data-view="data"]'), () => mount($('#import-result')));
  const input = $('#upload-file');
  const zone = $('#dropzone');
  input.addEventListener('change', () => chooseFile(input.files[0]));
  ['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add('dragging'); }));
  ['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, () => zone.classList.remove('dragging')));
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    const [file] = event.dataTransfer.files;
    if (!file) return;
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
    chooseFile(file);
  });

  $('#upload-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const file = input.files[0];
    if (!file) return;
    const button = $('#upload-submit');
    button.disabled = true;
    setStatus('#upload-status', 'Checking every row…');
    try {
      const body = new FormData();
      body.append('file', file);
      const dataset = await request(businessPath('/datasets'), { method: 'POST', body });
      setStatus('#upload-status', '');
      renderResult(dataset);
      $('#upload-form').reset();
      chooseFile(null);
      await loadDatasets();
      render();
    } catch (error) {
      setStatus('#upload-status', error.message, true);
      button.disabled = false;
    }
  });

  $('#momo-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = $('#momo-submit');
    button.disabled = true;
    setStatus('#momo-status', 'Reading messages…');
    try {
      const result = await request(businessPath('/sources/momo'), { method: 'POST', json: { sms_text: $('#momo-text').value } });
      setStatus('#momo-status', '');
      $('#momo-text').value = '';
      renderResult(result.dataset, h('div', { class: 'table-wrap' }, table(
        [
          { label: 'Date', value: (item) => item.transaction_date },
          { label: 'From', value: (item) => item.customer || '—' },
          { label: 'Network', value: (item) => item.channel || '—' },
          { label: 'Amount', num: true, value: (item) => money(item.amount, { code: item.currency || 'GHS' }) },
        ],
        result.records.slice(0, 20),
      )));
      await loadDatasets();
      render();
    } catch (error) {
      setStatus('#momo-status', error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}
