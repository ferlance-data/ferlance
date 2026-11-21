import { useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react';
import { request } from '../../lib/api';
import { formatDateTime, money, number, plainPercent, plural } from '../../lib/format';
import { Icon, IconSlot } from '../../lib/icons';
import { Markdown } from '../../lib/markdown';
import { analysableDatasets } from '../../lib/scope';
import { toast } from '../../lib/toast';
import { DataTable } from '../components/ui';
import { useBusinessQuery } from '../hooks';
import { PageActions } from '../page';
import { keys, useScope, useWorkspace } from '../workspace';

const PROMPTS = [
  'Which products made the most profit?',
  'How do this month’s sales compare with last month?',
  'Who are my most valuable customers?',
  'Where am I losing money?',
];

interface Question {
  id: string;
  label: string;
}
interface ProductItem {
  product: string;
  revenue: number;
  gross_profit?: number;
  units_sold?: number;
}
interface CustomerOverview {
  available: boolean;
  reason?: string;
  number_of_customers: number;
  repeat_customers: number;
  top_customers: { customer: string; metric_value: number; transactions: number }[];
}
interface QuickResult {
  question: string;
  answer: unknown;
}
interface AskResult {
  conversation_id: string;
  answer: string;
  datasets_considered: number;
  evidence_count?: number;
}
interface ConversationItem {
  id: string;
  title: string;
  updated_at: string;
}
interface ConversationDetail {
  id: string;
  messages: { role: string; content: string; created_at: string }[];
}

type Entry =
  | { id: number; kind: 'user'; text: string }
  | { id: number; kind: 'thinking'; text: string }
  | { id: number; kind: 'assistant'; meta: ReactNode; body: ReactNode };

type NewEntry = { kind: 'user'; text: string } | { kind: 'thinking'; text: string } | { kind: 'assistant'; meta: ReactNode; body: ReactNode };

function table<Row>(columns: { label: string; value: (row: Row) => ReactNode; num?: boolean }[], rows: Row[], empty?: string, key: (row: Row) => string = (row) => JSON.stringify(row)) {
  return (
    <div className="table-wrap">
      <DataTable columns={columns} rows={rows} rowKey={(row, index) => `${key(row)}-${index}`} empty={empty} />
    </div>
  );
}

function QuickBody({ question, answer }: { question: string; answer: unknown }) {
  if (typeof answer === 'string') return <p>{answer}</p>;
  if (Array.isArray(answer)) {
    return table<ProductItem>(
      [
        { label: 'Product', value: (item) => item.product },
        { label: 'Revenue', num: true, value: (item) => money(item.revenue) },
        { label: 'Profit / loss', num: true, value: (item) => (item.gross_profit === undefined ? '—' : money(item.gross_profit)) },
        { label: 'Units', num: true, value: (item) => (item.units_sold === undefined ? '—' : number(item.units_sold, 2)) },
      ],
      (answer as ProductItem[]).slice(0, 10),
      'No product records in this period.',
    );
  }
  const data = (answer ?? {}) as Record<string, unknown>;
  if (question === 'customer-overview') {
    const overview = data as unknown as CustomerOverview;
    if (!overview.available) return <p>{overview.reason}</p>;
    return (
      <>
        <p>{`${plural(overview.number_of_customers, 'customer')}, of whom ${number(overview.repeat_customers)} bought more than once.`}</p>
        {table(
          [
            { label: 'Customer', value: (item: CustomerOverview['top_customers'][number]) => item.customer },
            { label: 'Value', num: true, value: (item) => money(item.metric_value) },
            { label: 'Records', num: true, value: (item) => number(item.transactions) },
          ],
          overview.top_customers.slice(0, 8),
        )}
      </>
    );
  }
  if (question === 'revenue-trend') {
    const months = ((data.monthly as { period: string; revenue: number; transactions: number }[] | undefined) ?? []).slice(-12);
    return table(
      [
        { label: 'Month', value: (item: (typeof months)[number]) => item.period },
        { label: 'Revenue', num: true, value: (item) => money(item.revenue) },
        { label: 'Records', num: true, value: (item) => number(item.transactions) },
      ],
      months,
      'No dated records in this period.',
    );
  }
  if (data.message) {
    const percent = data.percent;
    return (
      <>
        <p>{String(data.message)}</p>
        {percent !== null && percent !== undefined ? <p className="muted body-sm">{`Change: ${plainPercent(percent as number, 2)}`}</p> : null}
      </>
    );
  }
  return <p>This answer is not available for the selected data.</p>;
}

function Assistant({ meta, body }: { meta: ReactNode; body: ReactNode }) {
  return (
    <div className="message message-assistant">
      <div className="message-meta">
        <span className="message-who">
          <Icon name="sparkles" />
          Lance
        </span>
        {meta}
      </div>
      <div className="message-body">{body}</div>
    </div>
  );
}

export default function Lance() {
  const { business, businessPath, datasets, markSetup } = useWorkspace();
  const { label, params } = useScope();
  const queryClient = useQueryClient();
  const hasFiles = analysableDatasets(datasets).length > 0;

  const questions = useBusinessQuery<Question[]>('/questions', { silent: true });
  const conversations = useBusinessQuery<ConversationItem[]>('/ask-lance/conversations', { silent: true });

  const [conversationId, setConversationId] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [status, setStatus] = useState<{ message: string; error: boolean }>({ message: '', error: false });

  const nextId = useRef(0);
  const sendingRef = useRef(false);
  const lifetime = useRef<AbortController | null>(null);
  const askController = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => {
      controller.abort();
      askController.current?.abort();
    };
  }, []);

  useLayoutEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [entries]);

  useLayoutEffect(() => {
    const input = inputRef.current;
    if (!input) return;
    input.style.height = 'auto';
    if (draft) input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
  }, [draft]);

  const refreshConversations = useCallback(
    () => queryClient.invalidateQueries({ queryKey: keys.business(business.id, '/ask-lance/conversations') }),
    [queryClient, business.id],
  );

  const push = (entry: NewEntry): number => {
    const id = nextId.current++;
    setEntries((current) => [...current, { ...entry, id } as Entry]);
    return id;
  };
  const replace = (id: number, entry: Omit<Extract<Entry, { kind: 'assistant' }>, 'id'>) =>
    setEntries((current) => current.map((item) => (item.id === id ? { ...entry, id } : item)));

  const quickAnswer = async (question: Question) => {
    const signal = lifetime.current?.signal;
    push({ kind: 'user', text: question.label });
    const pending = push({ kind: 'thinking', text: 'Calculating from your records…' });
    try {
      const result = await request<QuickResult>(businessPath(`/questions/${question.id}?${params().toString()}`), { signal });
      if (signal?.aborted) return;
      replace(pending, {
        kind: 'assistant',
        meta: (
          <>
            <span className="pill pill-ai">Calculated · no AI</span>
            <span>{label}</span>
          </>
        ),
        body: <QuickBody question={question.id} answer={result.answer} />,
      });
    } catch (error) {
      if (signal?.aborted) return;
      replace(pending, { kind: 'assistant', meta: null, body: <p className="negative">{(error as Error).message}</p> });
    }
  };

  const ask = async (raw: string) => {
    const question = raw.trim();
    if (!question || sendingRef.current) return;
    if (!hasFiles) {
      setStatus({ message: 'Import at least one file before asking Lance.', error: true });
      return;
    }
    sendingRef.current = true;
    setSending(true);
    setDraft('');
    setStatus({ message: '', error: false });
    push({ kind: 'user', text: question });
    const pending = push({ kind: 'thinking', text: 'Reading your records…' });
    const controller = new AbortController();
    askController.current = controller;
    const timer = window.setTimeout(() => controller.abort(), 60000);
    try {
      const result = await request<AskResult>(businessPath(`/ask-lance?${params().toString()}`), {
        method: 'POST',
        json: { question, conversation_id: conversationId },
        signal: controller.signal,
      });
      if (lifetime.current?.signal.aborted) return;
      setConversationId(result.conversation_id);
      markSetup({ conversations: true });
      replace(pending, {
        kind: 'assistant',
        meta: (
          <>
            <span>{`Grounded in ${plural(result.datasets_considered, 'file')}`}</span>
            {result.evidence_count ? <span>{`· ${plural(result.evidence_count, 'matching row')}`}</span> : null}
          </>
        ),
        body: <Markdown source={result.answer} />,
      });
      void refreshConversations();
    } catch (error) {
      if (lifetime.current?.signal.aborted) return;
      const message = (error as Error).name === 'AbortError' ? 'Lance took too long to respond. Try again in a moment.' : (error as Error).message;
      replace(pending, { kind: 'assistant', meta: null, body: <p className="negative">{message}</p> });
      setDraft(question);
    } finally {
      window.clearTimeout(timer);
      if (!lifetime.current?.signal.aborted) {
        sendingRef.current = false;
        setSending(false);
      }
    }
  };

  const openConversation = async (id: string) => {
    const signal = lifetime.current?.signal;
    try {
      const conversation = await request<ConversationDetail>(businessPath(`/ask-lance/conversations/${id}`), { signal });
      if (signal?.aborted) return;
      setConversationId(conversation.id);
      setEntries(
        conversation.messages.map((message): Entry => {
          const entryId = nextId.current++;
          return message.role === 'user'
            ? { id: entryId, kind: 'user', text: message.content }
            : { id: entryId, kind: 'assistant', meta: <span>{formatDateTime(message.created_at)}</span>, body: <Markdown source={message.content} /> };
        }),
      );
      void refreshConversations();
    } catch (error) {
      if (signal?.aborted) return;
      toast((error as Error).message, { error: true });
    }
  };

  const startConversation = () => {
    setConversationId(null);
    setEntries([]);
    void refreshConversations();
    inputRef.current?.focus();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void ask(draft);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void ask(draft);
    }
  };

  const list = conversations.data ?? [];

  return (
    <>
      <PageActions>
        <button className="btn btn-secondary" type="button" onClick={startConversation}>
          <Icon name="plus" />
          <span className="btn-label">New chat</span>
        </button>
      </PageActions>
      <div className="lance">
        <aside className="lance-history">
          <button className="btn btn-secondary lance-new" id="lance-new" type="button" onClick={startConversation}>
            <IconSlot name="plus" />
            New conversation
          </button>
          <p className="nav-label">Saved conversations</p>
          <div className="lance-conversations" id="lance-conversations">
            {conversations.data && !list.length ? (
              <p className="footnote" style={{ padding: '4px' }}>
                Your saved conversations will appear here.
              </p>
            ) : (
              list.map((item) => (
                <button
                  key={item.id}
                  className="conversation"
                  type="button"
                  aria-current={item.id === conversationId ? 'true' : 'false'}
                  onClick={() => void openConversation(item.id)}
                >
                  <strong>{item.title}</strong>
                  <small>{formatDateTime(item.updated_at)}</small>
                </button>
              ))
            )}
          </div>
        </aside>
        <div className="lance-main">
          <div className="lance-thread" id="lance-thread" aria-live="polite" ref={threadRef}>
            {entries.length === 0 ? (
              <div className="lance-empty">
                <span className="lance-orb">
                  <Icon name="sparkles" />
                </span>
                <h2>What would you like to know?</h2>
                <p>
                  {hasFiles
                    ? 'Lance reads every included file in your workspace. Instant answers are calculated directly from your records; questions go to your configured AI provider.'
                    : 'Import a sales file first — Lance answers only from your own records.'}
                </p>
              </div>
            ) : (
              entries.map((entry) =>
                entry.kind === 'user' ? (
                  <div className="message message-user" key={entry.id}>
                    {entry.text}
                  </div>
                ) : entry.kind === 'thinking' ? (
                  <div className="thinking" key={entry.id}>
                    {entry.text}
                  </div>
                ) : (
                  <Assistant key={entry.id} meta={entry.meta} body={entry.body} />
                ),
              )
            )}
          </div>
          <div className="lance-dock">
            <div className={`lance-suggestions${entries.length ? ' compact' : ''}`} id="lance-suggestions">
              {hasFiles ? (
                <>
                  {(questions.data ?? []).map((question) => (
                    <button className="suggestion" type="button" key={question.id} onClick={() => void quickAnswer(question)}>
                      <small>Instant</small>
                      {question.label}
                    </button>
                  ))}
                  {PROMPTS.map((prompt) => (
                    <button className="suggestion" type="button" key={prompt} onClick={() => void ask(prompt)}>
                      {prompt}
                    </button>
                  ))}
                </>
              ) : null}
            </div>
            <form className="composer" id="lance-form" onSubmit={submit}>
              <label className="visually-hidden" htmlFor="lance-input">
                Ask Lance
              </label>
              <textarea
                id="lance-input"
                ref={inputRef}
                rows={1}
                maxLength={1000}
                placeholder="Ask about sales, products, customers or costs…"
                required
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
              />
              <div className="composer-row">
                <span className="composer-scope">
                  <IconSlot name="at" />
                  <span id="lance-scope-label">{label}</span>
                </span>
                <span className="pill pill-ai">
                  <IconSlot name="sparkles" />
                  Lance
                </span>
                <button className="composer-send" id="lance-send" type="submit" aria-label="Send question" data-icon="send" disabled={sending}>
                  <Icon name="send" />
                </button>
              </div>
            </form>
            <p className={`status-text${status.error ? ' error' : ''}`} id="lance-status" role="status" aria-live="polite">
              {status.message}
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
