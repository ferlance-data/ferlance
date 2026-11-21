// Workspace entry point: session bootstrap, hash router, sidebar, and scope bar.

import { refreshSession, request, signOut } from './api.js';
import { $, $$, h, mount, toast } from './dom.js';
import { hydrateIcons } from './icons.js';
import { analysableDatasets, businessPath, onScopeChange, setScope, state } from './state.js';
import { view as data, loadDatasets, setDatasetsListener } from './views/data.js';
import { view as insights } from './views/insights.js';
import { view as inventory, loadInventorySummary } from './views/inventory.js';
import { view as lance } from './views/lance.js';
import { view as overview } from './views/overview.js';
import { view as position } from './views/position.js';
import { view as products } from './views/products.js';
import { view as settings, setProfileListener } from './views/settings.js';

const VIEWS = { overview, products, insights, lance, inventory, position, data, settings };
const LEGACY_ROUTES = { dashboard: 'overview', catalogue: 'products', 'ask-lance': 'lance', 'financial-position': 'position', profile: 'settings' };
let current = null;

/* ---------- Identity ---------- */
function renderIdentity() {
  const name = state.business?.name || 'Workspace';
  $('#workspace-name').textContent = name;
  $('#workspace-email').textContent = state.user.email;
  $('#workspace-avatar').textContent = name.slice(0, 1).toUpperCase();
}

/* ---------- Scope bar ---------- */
function renderScopeOptions() {
  const select = $('#scope-dataset');
  const files = analysableDatasets();
  if (state.scope.datasetId !== 'all' && !files.some((item) => item.id === state.scope.datasetId)) state.scope.datasetId = 'all';
  mount(
    select,
    h('option', { value: 'all' }, files.length ? `All business data · ${files.filter((item) => item.included).length} files` : 'All business data'),
    files.length ? h('optgroup', { label: 'A single file' }, files.map((item) => h('option', { value: item.id }, `${item.filename}${item.included ? '' : ' (excluded)'}`))) : null,
  );
  select.value = state.scope.datasetId;
  const pending = state.datasets.filter((item) => item.status === 'partial' || item.status === 'failed').length;
  $('#nav-data-count').hidden = !pending;
  $('#nav-data-count').textContent = pending;
}

function bindScopeBar() {
  $('#scope-dataset').addEventListener('change', (event) => setScope({ datasetId: event.target.value }));
  $('#scope-range').addEventListener('change', (event) => {
    const custom = event.target.value === 'custom';
    $('#scope-custom').hidden = !custom;
    if (custom) {
      $('#scope-from').value ||= state.bounds.from || '';
      $('#scope-to').value ||= state.bounds.to || '';
      return;
    }
    setScope({ range: event.target.value });
  });
  $('#scope-apply').addEventListener('click', () => {
    const from = $('#scope-from').value || null;
    const to = $('#scope-to').value || null;
    if (from && to && from > to) {
      toast('The start date must be on or before the end date.', { error: true });
      return;
    }
    setScope({ range: 'custom', from, to });
  });
  onScopeChange(() => {
    if (current?.scoped) runLoad(current);
  });
}

/* ---------- Router ---------- */
function runLoad(target) {
  target.load().catch((error) => {
    if (error.status === 401) return;
    toast(error.message, { error: true });
  });
}

function route() {
  let name = window.location.hash.slice(1) || 'overview';
  name = LEGACY_ROUTES[name] || name;
  if (!VIEWS[name]) name = 'overview';
  const target = VIEWS[name];
  current = target;
  $$('.view').forEach((section) => { section.hidden = section.dataset.view !== name; });
  $$('.nav-item[data-page]').forEach((link) => {
    if (link.dataset.page === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  $('#page-title').textContent = target.title;
  $('#page-description').textContent = target.description;
  document.title = `${target.title} · Ferlance`;
  $('#scope-bar').hidden = !target.scoped;
  mount($('#topbar-actions'), target.actions ? target.actions() : []);
  closeSidebar();
  window.scrollTo({ top: 0 });
  runLoad(target);
}

/* ---------- Sidebar (mobile drawer) ---------- */
function openSidebar() {
  $('#shell').classList.add('nav-open');
  $('#sidebar-backdrop').hidden = false;
  $('#menu-btn').setAttribute('aria-expanded', 'true');
}

function closeSidebar() {
  $('#shell').classList.remove('nav-open');
  $('#sidebar-backdrop').hidden = true;
  $('#menu-btn').setAttribute('aria-expanded', 'false');
}

/* ---------- Boot ---------- */
async function bootstrap() {
  try {
    await refreshSession();
    const identity = await request('/api/auth/me');
    state.user = identity.user;
    state.business = identity.business;
  } catch {
    window.location.replace('/?signin');
    return;
  }
  if (!state.business) {
    toast('This account has no business workspace.', { error: true });
    return;
  }
  state.setup = { balances: false, conversations: false };
  hydrateIcons();
  renderIdentity();
  Object.values(VIEWS).forEach((target) => target.init?.());
  setDatasetsListener(renderScopeOptions);
  setProfileListener(renderIdentity);
  bindScopeBar();
  $('#menu-btn').addEventListener('click', openSidebar);
  $('#sidebar-close').addEventListener('click', closeSidebar);
  $('#sidebar-backdrop').addEventListener('click', closeSidebar);
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeSidebar(); });
  $('#logout').addEventListener('click', signOut);

  const [, , history, conversations] = await Promise.all([
    loadDatasets(),
    loadInventorySummary().catch(() => null),
    request(businessPath('/financial-position/history?limit=1')).catch(() => []),
    request(businessPath('/ask-lance/conversations')).catch(() => []),
  ]);
  state.setup = { balances: history.length > 0, conversations: conversations.length > 0 };

  $('#boot').hidden = true;
  $('#shell').hidden = false;
  window.addEventListener('hashchange', route);
  route();
}

bootstrap();
