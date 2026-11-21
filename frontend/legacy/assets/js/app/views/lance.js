// Ask Lance: saved conversations with the AI analyst, plus instant answers that are
// calculated directly from records (no AI, so they work without a provider key).

import { request } from '../api.js';
import { $, formatDateTime, h, icon, money, mount, number, plainPercent, plural, setStatus, table } from '../dom.js';
import { renderMarkdown } from '../markdown.js';
import { analysableDatasets, businessPath, scopeLabel, scopeParams, state } from '../state.js';

let conversationId = null;
let sending = false;

const PROMPTS = [
  'Which products made the most profit?',
  'How do this month’s sales compare with last month?',
  'Who are my most valuable customers?',
  'Where am I losing money?',
];

export const view = {
  title: 'Ask Lance',
  description: 'Ask about your business in plain language. Lance answers from your own records and says when data is missing.',
  scoped: true,
  actions: () => [h('button', { class: 'btn btn-secondary', type: 'button', onclick: startConversation }, icon('plus'), h('span', { class: 'btn-label' }, 'New chat'))],
  init() {
    $('#lance-new').addEventListener('click', startConversation);
    const input = $('#lance-input');
    $('#lance-form').addEventListener('submit', (event) => {
      event.preventDefault();
      ask(input.value);
    });
    input.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        ask(input.value);
      }
    });
    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
    });
  },
  load,
};

function thread() {
  return $('#lance-thread');
}

function scrollToEnd() {
  const target = thread();
  target.scrollTop = target.scrollHeight;
}

function renderEmpty() {
  mount(
    thread(),
    h(
      'div',
      { class: 'lance-empty' },
      h('span', { class: 'lance-orb' }, icon('sparkles')),
      h('h2', {}, 'What would you like to know?'),
      h('p', {}, analysableDatasets().length
        ? 'Lance reads every included file in your workspace. Instant answers are calculated directly from your records; questions go to your configured AI provider.'
        : 'Import a sales file first — Lance answers only from your own records.'),
    ),
  );
}

/** Full chip grid on an empty thread; a single scrollable row once a conversation is under way. */
function setSuggestionsVisible(expanded) {
  $('#lance-suggestions').classList.toggle('compact', !expanded);
}

function userMessage(text) {
  return h('div', { class: 'message message-user' }, text);
}

function assistantMessage(body, meta = []) {
  return h(
    'div',
    { class: 'message message-assistant' },
    h('div', { class: 'message-meta' }, h('span', { class: 'message-who' }, icon('sparkles'), 'Lance'), meta),
    h('div', { class: 'message-body' }, body),
  );
}

function renderSuggestions(questions) {
  const instant = questions.map((question) => h('button', { class: 'suggestion', type: 'button', onclick: () => quickAnswer(question) }, h('small', {}, 'Instant'), question.label));
  const prompts = PROMPTS.map((prompt) => h('button', { class: 'suggestion', type: 'button', onclick: () => ask(prompt) }, prompt));
  mount($('#lance-suggestions'), analysableDatasets().length ? [...instant, ...prompts] : []);
}

function productTable(items) {
  return h('div', { class: 'table-wrap' }, table(
    [
      { label: 'Product', value: (item) => item.product },
      { label: 'Revenue', num: true, value: (item) => money(item.revenue) },
      { label: 'Profit / loss', num: true, value: (item) => (item.gross_profit === undefined ? '—' : money(item.gross_profit)) },
      { label: 'Units', num: true, value: (item) => (item.units_sold === undefined ? '—' : number(item.units_sold, 2)) },
    ],
    items.slice(0, 10),
    { empty: 'No product records in this period.' },
  ));
}

function quickBody(question, answer) {
  if (typeof answer === 'string') return [h('p', {}, answer)];
  if (Array.isArray(answer)) return [productTable(answer)];
  if (question === 'customer-overview') {
    if (!answer.available) return [h('p', {}, answer.reason)];
    return [
      h('p', {}, `${plural(answer.number_of_customers, 'customer')}, of whom ${number(answer.repeat_customers)} bought more than once.`),
      h('div', { class: 'table-wrap' }, table([
        { label: 'Customer', value: (item) => item.customer },
        { label: 'Value', num: true, value: (item) => money(item.metric_value) },
        { label: 'Records', num: true, value: (item) => number(item.transactions) },
      ], answer.top_customers.slice(0, 8))),
    ];
  }
  if (question === 'revenue-trend') {
    const months = (answer.monthly || []).slice(-12);
    return [h('div', { class: 'table-wrap' }, table([
      { label: 'Month', value: (item) => item.period },
      { label: 'Revenue', num: true, value: (item) => money(item.revenue) },
      { label: 'Records', num: true, value: (item) => number(item.transactions) },
    ], months, { empty: 'No dated records in this period.' }))];
  }
  if (answer?.message) {
    return [h('p', {}, answer.message), answer.percent !== null && answer.percent !== undefined ? h('p', { class: 'muted body-sm' }, `Change: ${plainPercent(answer.percent, 2)}`) : null];
  }
  return [h('p', {}, 'This answer is not available for the selected data.')];
}

async function quickAnswer(question) {
  if (thread().querySelector('.lance-empty')) thread().replaceChildren();
  setSuggestionsVisible(false);
  thread().append(userMessage(question.label));
  const pending = h('div', { class: 'thinking' }, 'Calculating from your records…');
  thread().append(pending);
  scrollToEnd();
  try {
    const result = await request(businessPath(`/questions/${question.id}?${scopeParams()}`));
    pending.replaceWith(assistantMessage(quickBody(question.id, result.answer), [h('span', { class: 'pill pill-ai' }, 'Calculated · no AI'), h('span', {}, scopeLabel())]));
  } catch (error) {
    pending.replaceWith(assistantMessage([h('p', { class: 'negative' }, error.message)]));
  }
  scrollToEnd();
}

async function ask(raw) {
  const question = String(raw || '').trim();
  if (!question || sending) return;
  if (!analysableDatasets().length) {
    setStatus('#lance-status', 'Import at least one file before asking Lance.', true);
    return;
  }
  sending = true;
  $('#lance-send').disabled = true;
  $('#lance-input').value = '';
  $('#lance-input').style.height = 'auto';
  setStatus('#lance-status', '');
  if (thread().querySelector('.lance-empty')) thread().replaceChildren();
  setSuggestionsVisible(false);
  thread().append(userMessage(question));
  const pending = h('div', { class: 'thinking' }, 'Reading your records…');
  thread().append(pending);
  scrollToEnd();
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 60000);
  try {
    const result = await request(businessPath(`/ask-lance?${scopeParams()}`), { method: 'POST', json: { question, conversation_id: conversationId }, signal: controller.signal });
    conversationId = result.conversation_id;
    state.setup.conversations = true;
    pending.replaceWith(assistantMessage(renderMarkdown(result.answer), [h('span', {}, `Grounded in ${plural(result.datasets_considered, 'file')}`), result.evidence_count ? h('span', {}, `· ${plural(result.evidence_count, 'matching row')}`) : null]));
    loadConversations();
  } catch (error) {
    const message = error.name === 'AbortError' ? 'Lance took too long to respond. Try again in a moment.' : error.message;
    pending.replaceWith(assistantMessage([h('p', { class: 'negative' }, message)]));
    $('#lance-input').value = question;
  } finally {
    window.clearTimeout(timer);
    sending = false;
    $('#lance-send').disabled = false;
    scrollToEnd();
  }
}

async function loadConversations() {
  const conversations = await request(businessPath('/ask-lance/conversations'));
  mount(
    $('#lance-conversations'),
    conversations.length
      ? conversations.map((item) => h('button', { class: 'conversation', type: 'button', 'aria-current': item.id === conversationId ? 'true' : 'false', onclick: () => openConversation(item.id) }, h('strong', {}, item.title), h('small', {}, formatDateTime(item.updated_at))))
      : h('p', { class: 'footnote', style: { padding: '4px' } }, 'Your saved conversations will appear here.'),
  );
}

async function openConversation(id) {
  const conversation = await request(businessPath(`/ask-lance/conversations/${id}`));
  conversationId = conversation.id;
  setSuggestionsVisible(false);
  mount(thread(), conversation.messages.map((message) => (message.role === 'user'
    ? userMessage(message.content)
    : assistantMessage(renderMarkdown(message.content), [h('span', {}, formatDateTime(message.created_at))]))));
  scrollToEnd();
  loadConversations();
}

function startConversation() {
  conversationId = null;
  setSuggestionsVisible(true);
  renderEmpty();
  loadConversations().catch(() => {});
  $('#lance-input').focus();
}

async function load() {
  $('#lance-scope-label').textContent = scopeLabel();
  if (!thread().children.length) renderEmpty();
  const questions = await request(businessPath('/questions')).catch(() => []);
  renderSuggestions(questions);
  await loadConversations();
}

