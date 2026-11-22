// Public landing page: navigation, hero skyline, interactive demos, and auth dialog.
// Plain TypeScript (no React): the markup is static in index.html for SEO and first paint.
// All dynamic content is built from text nodes; nothing here uses innerHTML.

import '../styles/base.css';
import '../styles/landing.css';
import { prefetchWorkspace } from './prefetch';

const SVG_NS = 'http://www.w3.org/2000/svg';

function $<T extends Element = HTMLElement>(selector: string, root: ParentNode = document): T {
  const node = root.querySelector<T>(selector);
  if (!node) throw new Error(`Landing markup is missing ${selector}`);
  return node;
}
const $$ = <T extends Element = HTMLElement>(selector: string, root: ParentNode = document): T[] => [...root.querySelectorAll<T>(selector)];

type Child = Node | string | number | Child[];

function el(tag: string, attrs: Record<string, string> = {}, ...children: Child[]): HTMLElement {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (key === 'class') node.className = value;
    else node.setAttribute(key, value);
  });
  children.flat(Infinity as 1).forEach((child) => node.append(child instanceof Node ? child : document.createTextNode(String(child))));
  return node;
}

/* ---------- Navigation ---------- */
const nav = $('#site-nav');
const menu = $('#site-menu');
const menuButton = $('#site-menu-btn');
const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 24);
window.addEventListener('scroll', onScroll, { passive: true });
onScroll();

function setMenu(open: boolean): void {
  menu.hidden = !open;
  nav.classList.toggle('open', open);
  menuButton.setAttribute('aria-expanded', String(open));
}
menuButton.addEventListener('click', () => setMenu(menu.hidden === true));
$$('a', menu).forEach((link) => link.addEventListener('click', () => setMenu(false)));
$('#year').textContent = String(new Date().getFullYear());

/* ---------- Hero skyline: a city drawn from bar-chart columns ---------- */
function seeded(seed: number): () => number {
  let value = seed;
  return () => {
    value = (value * 1664525 + 1013904223) % 4294967296;
    return value / 4294967296;
  };
}

function drawSkyline(svg: SVGSVGElement): void {
  const width = 1600;
  const height = 900;
  const random = seeded(7);
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const layers = [
    // Colours are tokens (landing.css, --skyline-*); inline style accepts var(), SVG attributes do not.
    { count: 30, min: 180, max: 520, color: 'var(--skyline-far)', windows: 0.12, opacity: 0.55 },
    { count: 22, min: 260, max: 760, color: 'var(--skyline-mid)', windows: 0.2, opacity: 0.85 },
    { count: 14, min: 320, max: 860, color: 'var(--skyline-near)', windows: 0.26, opacity: 1 },
  ];
  const fragment = document.createDocumentFragment();
  layers.forEach((layer, depth) => {
    const group = document.createElementNS(SVG_NS, 'g');
    group.setAttribute('opacity', String(layer.opacity));
    let x = -40 + random() * 40;
    while (x < width) {
      const buildingWidth = 46 + random() * (60 + depth * 30);
      // Taller towers toward the right, like a skyline seen from the shop floor.
      const lean = 0.55 + (x / width) * 0.6;
      const buildingHeight = Math.min(height - 20, (layer.min + random() * (layer.max - layer.min)) * lean);
      const top = height - buildingHeight;
      const body = document.createElementNS(SVG_NS, 'rect');
      body.setAttribute('x', x.toFixed(1));
      body.setAttribute('y', top.toFixed(1));
      body.setAttribute('width', buildingWidth.toFixed(1));
      body.setAttribute('height', buildingHeight.toFixed(1));
      body.style.fill = layer.color;
      group.append(body);
      const edge = document.createElementNS(SVG_NS, 'rect');
      edge.setAttribute('x', x.toFixed(1));
      edge.setAttribute('y', top.toFixed(1));
      edge.setAttribute('width', buildingWidth.toFixed(1));
      edge.setAttribute('height', '2');
      edge.style.fill = depth === 2 && random() > 0.7 ? 'var(--skyline-mint)' : 'var(--skyline-amber)';
      edge.setAttribute('opacity', depth === 2 ? '0.55' : '0.25');
      group.append(edge);
      for (let wy = top + 14; wy < height - 12; wy += 16) {
        for (let wx = x + 8; wx < x + buildingWidth - 10; wx += 13) {
          if (random() > layer.windows) continue;
          const light = document.createElementNS(SVG_NS, 'rect');
          light.setAttribute('x', wx.toFixed(1));
          light.setAttribute('y', wy.toFixed(1));
          light.setAttribute('width', '5');
          light.setAttribute('height', '7');
          light.style.fill = random() > 0.85 ? 'var(--skyline-mint)' : 'var(--skyline-amber)';
          light.setAttribute('opacity', (0.25 + random() * 0.55).toFixed(2));
          group.append(light);
        }
      }
      x += buildingWidth + random() * 10;
    }
    fragment.append(group);
  });
  svg.append(fragment);
}
drawSkyline($<SVGSVGElement>('#hero-skyline'));

/* ---------- Ask Lance demo ---------- */
interface AgentScript {
  question: string;
  step: string;
  answer: string;
  metrics: [string, string, string][];
  followups: string[];
}

const agentScripts: Record<string, AgentScript> = {
  summary: {
    question: 'How did the shop do this week?',
    step: 'Read 412 records from 3 files · compared with last week',
    answer: 'Revenue was GH₵12,480 across 412 sales, up 9.2% on last week. Rice 25kg and Frytol oil drove most of the growth; Thursday was the strongest day.',
    metrics: [['Revenue', 'GH₵12,480', '▲ 9.2%'], ['Average sale', 'GH₵30.29', '▲ 2.1%'], ['Sales', '412', '▲ 7.0%']],
    followups: ['Which customers bought most?', 'Show the daily trend'],
  },
  margin: {
    question: 'Which items are losing us money?',
    step: 'Checked item revenue against recorded unit costs',
    answer: 'Two items sold below their recorded cost this month. Milo 400g lost GH₵120 after GH₵1,840 in sales; Peak milk tins lost GH₵36. Every other costed item made a profit.',
    metrics: [['Milo 400g', 'GH₵-120', 'Margin -6.5%'], ['Peak milk', 'GH₵-36', 'Margin -2.9%'], ['Best return', 'Sugar 1kg', 'ROI 41%']],
    followups: ['What price would break even?', 'Compare with last month'],
  },
  stock: {
    question: 'What do I need to reorder?',
    step: 'Checked 58 products against their reorder levels',
    answer: 'Rice 25kg (4 bags) and Frytol oil 5L (2 tins) are at or below their reorder levels. At last week\'s pace, rice runs out in about 3 days.',
    metrics: [['Low stock', '2 items', 'Reorder now'], ['Stock value', 'GH₵21,300', 'Costed'], ['Products', '58', 'Active']],
    followups: ['Print the inventory report', 'Who supplies rice?'],
  },
};

function renderAgent(key: string): void {
  const script = agentScripts[key];
  if (!script) return;
  $('#agent-thread').replaceChildren(
    el('div', { class: 'agent-user fade-in' }, script.question),
    el('div', { class: 'agent-step fade-in', style: 'animation-delay:.15s' }, script.step),
    el(
      'div',
      { class: 'agent-answer fade-in', style: 'animation-delay:.3s' },
      el('p', {}, script.answer),
      el('div', { class: 'agent-metrics' }, script.metrics.map(([label, value, note]) => el('div', { class: 'agent-metric' }, el('small', {}, label), el('b', {}, value), el('small', {}, note)))),
      el('div', { class: 'agent-followups' }, script.followups.map((text) => el('span', {}, text))),
    ),
  );
}

function bindTabs(selector: string, attribute: string, render: (key: string) => void): void {
  const tabs = $$(selector);
  tabs.forEach((tab) => tab.addEventListener('click', () => {
    tabs.forEach((other) => other.setAttribute('aria-selected', String(other === tab)));
    render(tab.dataset[attribute] ?? '');
  }));
}
bindTabs('[data-agent-tab]', 'agentTab', renderAgent);
renderAgent('summary');

/* ---------- Use cases ---------- */
type Usecase = [title: string, summary: string, points: string[]];

const usecases: Record<string, Usecase> = {
  retail: ['Retail & provisions', 'Know which shelves pay the rent. Ferlance ranks every item by sales and profit, flags lines selling below cost, and warns you before fast movers run out.', ['Top and slow sellers for any week, month or year', 'Item profit and margin from your unit costs', 'Low-stock alerts from a simple stock ledger']],
  wholesale: ['Wholesale & distribution', 'Bulk orders, credit customers and thin margins. See which customers and lines carry the business, and whether growth is outpacing last period.', ['Customer ranking and repeat buyers', 'Period-over-period comparisons on every number', 'Stocktake imports that reconcile counted stock']],
  pharmacy: ['Pharmacy', 'Hundreds of SKUs and strict stock discipline. Keep an auditable ledger of every purchase, sale and adjustment alongside your sales performance.', ['SKU-level stock with reorder levels', 'Audit trail for every stock movement', 'Printable inventory and financial reports']],
  food: ['Food & hospitality', 'Daily cash, Mobile Money and ingredients. Paste MoMo alerts straight in and see the day\'s takings next to what it cost to make them.', ['Mobile Money SMS turned into sales records', 'Daily and weekly revenue trends', 'Cost files supported alongside sales']],
  services: ['Services', 'Salons, repairs, consulting. Track revenue by service and client, and keep a dated statement of what the business owns and owes.', ['Revenue by service and by client', 'Statement of financial position for any date', 'Ask Lance plain-language questions about your month']],
};

function renderUsecase(key: string): void {
  const entry = usecases[key];
  if (!entry) return;
  const [title, summary, points] = entry;
  $('#usecase-panel').replaceChildren(
    el('div', { class: 'fade-in' }, el('h3', {}, title), el('p', {}, summary)),
    el('ul', { class: 'fade-in' }, points.map((point, index) => el('li', {}, el('span', {}, String(index + 1).padStart(2, '0')), point))),
  );
}
bindTabs('[data-usecase]', 'usecase', renderUsecase);
renderUsecase('retail');

/* ---------- Facts curve draws in when visible ---------- */
const curve = $('.facts-curve-path');
if ('IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    if (entries.some((entry) => entry.isIntersecting)) {
      curve.classList.add('drawn');
      observer.disconnect();
    }
  }, { threshold: 0.4 });
  observer.observe(curve);
} else {
  curve.classList.add('drawn');
}

/* ---------- Auth ---------- */
type Mode = 'login' | 'signup';

const dialog = $<HTMLDialogElement>('#auth-dialog');
const forms: Record<Mode, HTMLFormElement> = { login: $<HTMLFormElement>('#login-form'), signup: $<HTMLFormElement>('#signup-form') };
const copy: Record<Mode, [string, string]> = {
  login: ['Welcome back', 'Sign in to your Ferlance workspace.'],
  signup: ['Create your workspace', 'Free to start. Bring a sales file and see your numbers in minutes.'],
};

function setMode(mode: Mode): void {
  (Object.entries(forms) as [Mode, HTMLFormElement][]).forEach(([name, form]) => { form.hidden = name !== mode; });
  $$('[data-auth-mode]').forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.authMode === mode)));
  const [title, subtitle] = copy[mode];
  $('#auth-title').textContent = title;
  $('#auth-subtitle').textContent = subtitle;
}

const asMode = (value: string | undefined): Mode => (value === 'signup' ? 'signup' : 'login');

function openAuth(mode: Mode): void {
  setMode(mode);
  if (!dialog.open) dialog.showModal();
  prefetchWorkspace();
  $<HTMLInputElement>('input', forms[mode]).focus();
}

$$('[data-auth]').forEach((button) => button.addEventListener('click', () => openAuth(asMode(button.dataset.auth))));
$$('[data-auth-mode]').forEach((tab) => tab.addEventListener('click', () => setMode(asMode(tab.dataset.authMode))));
dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });

interface ErrorPayload {
  detail?: string | { msg: string }[];
}

async function post(path: string, body: Record<string, FormDataEntryValue | null>): Promise<unknown> {
  const response = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = (await response.json().catch(() => ({}))) as ErrorPayload;
  if (!response.ok) {
    const detail = Array.isArray(payload.detail) ? payload.detail.map((item) => item.msg).join(' ') : payload.detail;
    throw new Error(detail || 'Something went wrong. Please try again.');
  }
  return payload;
}

/* ---------- Invite links (/?invite=TOKEN) ---------- */
interface InviteInfo {
  business_name: string;
  role: 'manager' | 'accountant';
}
interface AuthResult {
  access_token: string;
  business: { id: string } | null;
}

let invite: { token: string; info: InviteInfo } | null = null;

function rememberBusiness(id: string | undefined): void {
  if (!id) return;
  try {
    localStorage.setItem('ferlance-business', id);
  } catch {
    /* storage unavailable */
  }
}

async function acceptInvite(accessToken: string): Promise<string | undefined> {
  if (!invite) return undefined;
  const response = await fetch(`/api/invites/${encodeURIComponent(invite.token)}/accept`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const payload = (await response.json().catch(() => ({}))) as ErrorPayload & { business?: { id: string } };
  // Already a member is fine: open that business.
  if (!response.ok && response.status !== 409) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'The invite could not be accepted.');
  return payload.business?.id;
}

function bindAuthForm(mode: Mode, path: string, fields: string[], pending: string): void {
  const form = forms[mode];
  const statusLine = $(`#${mode}-status`);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    const submit = $<HTMLButtonElement>('button[type="submit"]', form);
    submit.disabled = true;
    statusLine.className = 'status-text';
    statusLine.textContent = pending;
    try {
      const body: Record<string, FormDataEntryValue | null> = Object.fromEntries(fields.map((field) => [field, data.get(field)]));
      if (invite && mode === 'signup') {
        delete body.business_name;
        body.invite_token = invite.token;
      }
      const result = (await post(path, body)) as AuthResult;
      // Signup with an invite already joined the business; a sign-in still has to accept it.
      const joined = invite && mode === 'login' ? await acceptInvite(result.access_token) : invite ? result.business?.id : undefined;
      rememberBusiness(joined);
      window.location.assign('/app');
    } catch (error) {
      statusLine.className = 'status-text error';
      statusLine.textContent = error instanceof Error ? error.message : String(error);
      submit.disabled = false;
    }
  });
}
bindAuthForm('login', '/api/auth/login', ['email', 'password'], 'Signing in…');
bindAuthForm('signup', '/api/auth/signup', ['business_name', 'email', 'password'], 'Creating your workspace…');

const params = new URLSearchParams(window.location.search);
const inviteToken = params.get('invite');
if (inviteToken) {
  // Keep the token out of history, bookmarks and Referer headers once it has been read.
  params.delete('invite');
  window.history.replaceState(null, '', `${window.location.pathname}${params.size ? `?${params}` : ''}`);
  void openInvite(inviteToken);
} else if (params.has('signin') || params.has('signup')) {
  openAuth(params.has('signup') ? 'signup' : 'login');
}

async function openInvite(token: string): Promise<void> {
  const response = await fetch(`/api/invites/${encodeURIComponent(token)}`).catch(() => null);
  const info = response?.ok ? ((await response.json()) as InviteInfo) : null;
  openAuth('signup');
  if (!info) {
    $('#auth-subtitle').textContent = 'This invite link is not valid. It may have expired or already been used; ask for a new one.';
    return;
  }
  invite = { token, info };
  const role = info.role === 'accountant' ? 'an accountant' : 'a manager';
  const subtitle = `You have been invited to ${info.business_name} as ${role}. Create an account, or sign in if you already have one.`;
  copy.signup = [`Join ${info.business_name}`, subtitle];
  copy.login = [`Join ${info.business_name}`, subtitle];
  const businessField = $<HTMLInputElement>('input[name="business_name"]', forms.signup);
  businessField.required = false;
  const label = businessField.closest('label');
  if (label) label.hidden = true;
  setMode('signup');
}
