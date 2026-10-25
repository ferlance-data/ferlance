// Settings: profile, appearance, the web-research integration, and administration.

import { request } from '../api.js';
import { $, $$, formatDate, h, mount, pill, setStatus, table, toast } from '../dom.js';
import { businessPath, state } from '../state.js';

const THEME_KEY = 'ferlance-theme';
let onProfileChanged = () => {};
export const setProfileListener = (listener) => { onProfileChanged = listener; };

export const view = {
  title: 'Settings',
  description: 'Your profile, how the workspace looks, and connected services.',
  scoped: false,
  init,
  load,
};

export function applyTheme(choice) {
  const dark = choice === 'dark' || (choice === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0f1c1b' : '#fbfaf6');
}

function savedTheme() {
  try { return localStorage.getItem(THEME_KEY) || 'system'; } catch { return 'system'; }
}

async function loadBrave() {
  const result = await request(businessPath('/integrations/brave-search'));
  const replacement = result.configured ? pill(`Connected ${result.updated_at ? formatDate(result.updated_at) : ''}`.trim(), 'success') : pill('Not connected');
  replacement.id = 'brave-pill';
  $('#brave-pill').replaceWith(replacement);
  $('#brave-remove').disabled = !result.configured;
}

async function loadAdmin() {
  try {
    await request('/api/admin/capabilities');
  } catch {
    $('#admin-card').hidden = true;
    return;
  }
  $('#admin-card').hidden = false;
  const users = await request('/api/admin/users');
  mount($('#admin-users'), table(
    [
      { label: 'User', value: (item) => h('div', { class: 'file-cell' }, h('strong', {}, item.email), h('small', {}, item.full_name || '—')) },
      { label: 'Joined', value: (item) => formatDate(item.created_at) },
      {
        label: 'Role',
        value: (item) => h(
          'select',
          {
            class: 'select',
            style: { width: '130px' },
            disabled: item.id === state.user.id,
            'aria-label': `Role for ${item.email}`,
            onchange: async (event) => {
              try {
                await request(`/api/admin/users/${item.id}/role`, { method: 'PATCH', json: { role: event.target.value } });
                toast(`${item.email} is now ${event.target.value}.`);
              } catch (error) {
                toast(error.message, { error: true });
                loadAdmin();
              }
            },
          },
          ['owner', 'member', 'admin'].map((role) => h('option', { value: role, selected: role === item.role }, role)),
        ),
      },
    ],
    users,
  ));
}

async function load() {
  $('#profile-name').value = state.user.full_name || '';
  $('#profile-business').value = state.business.name;
  $('#profile-email').value = state.user.email;
  await Promise.all([loadBrave(), loadAdmin()]);
}

function init() {
  const choice = savedTheme();
  $$('#theme-picker [data-theme-choice]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.themeChoice === choice));
    button.addEventListener('click', () => {
      $$('#theme-picker [data-theme-choice]').forEach((other) => other.setAttribute('aria-pressed', String(other === button)));
      try { localStorage.setItem(THEME_KEY, button.dataset.themeChoice); } catch { /* storage unavailable */ }
      applyTheme(button.dataset.themeChoice);
    });
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (savedTheme() === 'system') applyTheme('system');
  });

  $('#profile-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
      const result = await request('/api/auth/profile', { method: 'PATCH', json: { full_name: $('#profile-name').value, business_name: $('#profile-business').value } });
      state.user = { ...state.user, ...result.user };
      state.business = { ...state.business, ...result.business };
      onProfileChanged();
      setStatus('#profile-status', 'Saved.');
    } catch (error) {
      setStatus('#profile-status', error.message, true);
    }
  });

  $('#brave-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const key = $('#brave-key').value.trim();
    if (!key) {
      setStatus('#brave-status', 'Paste an API key first.', true);
      return;
    }
    try {
      await request(businessPath('/integrations/brave-search'), { method: 'PUT', json: { api_key: key } });
      $('#brave-key').value = '';
      await loadBrave();
      setStatus('#brave-status', 'Connected. The key is encrypted and will not be shown again.');
    } catch (error) {
      setStatus('#brave-status', error.message, true);
    }
  });

  $('#brave-remove').addEventListener('click', async () => {
    try {
      await request(businessPath('/integrations/brave-search'), { method: 'DELETE' });
      await loadBrave();
      setStatus('#brave-status', 'Disconnected.');
    } catch (error) {
      setStatus('#brave-status', error.message, true);
    }
  });
}
