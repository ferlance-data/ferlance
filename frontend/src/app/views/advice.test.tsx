import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import type { Advice, AdviceItem } from '../../lib/types';
import { evidenceText, visibleAdvice } from './advice.logic';

const request = vi.fn();
vi.mock('../../lib/api', () => ({ request: (...args: unknown[]) => request(...args) }));
vi.mock('../workspace', () => ({
  useWorkspace: () => ({ business: { id: 'b1' }, businessPath: (suffix: string) => `/api/businesses/b1${suffix}` }),
  useScope: () => ({ params: () => new URLSearchParams('from=2026-10-01&to=2026-10-30') }),
}));
const { AdviceList } = await import('./advice');

beforeAll(() => {
  // jsdom does not implement modal dialogs.
  HTMLDialogElement.prototype.showModal ??= function (this: HTMLDialogElement) {
    this.open = true;
  };
});

const item = (patch: Partial<AdviceItem>): AdviceItem => ({
  id: 'a',
  kind: 'decline',
  severity: 'attention',
  title: 'Rice is selling less',
  summary: 'Down 40%.',
  product: 'Rice',
  impact: 100,
  evidence: [{ label: 'Change', value: -40, format: 'percent' }],
  reasons: [{ text: '2 regular buyers of Rice did not buy it this period.', confidence: 'likely', basis: 'customers', people: ['Kofi', 'Ama'] }],
  actions: ['Call or message the 2 regular buyers who stopped buying Rice.'],
  ...patch,
});

const advice = (patch: Partial<Advice> = {}): Advice => ({
  items: [item({}), item({ id: 'b', title: 'Sell more Oil', severity: 'opportunity' }), item({ id: 'c', title: 'Tip', severity: 'info' })],
  top: ['a', 'b'],
  missing: [],
  period: { from: '2026-10-01', to: '2026-10-30' },
  comparison_period: { from: '2026-09-01', to: '2026-09-30' },
  ai_available: false,
  ...patch,
});

const renderList = (value: Advice) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AdviceList advice={value} />
    </QueryClientProvider>,
  );

describe('advice logic', () => {
  it('shows the server top list, then everything when expanded', () => {
    expect(visibleAdvice(advice(), false).map((entry) => entry.id)).toEqual(['a', 'b']);
    expect(visibleAdvice(advice(), true).map((entry) => entry.id)).toEqual(['a', 'b', 'c']);
    expect(visibleAdvice(undefined, true)).toEqual([]);
  });
  it('formats evidence by kind', () => {
    expect(evidenceText({ label: 'x', value: 12.5, format: 'percent' })).toContain('12.5');
    expect(evidenceText({ label: 'x', value: 3, format: 'number' })).toBe('3');
    expect(evidenceText({ label: 'x', value: 'n/a', format: 'text' })).toBe('n/a');
  });
});

describe('AdviceList', () => {
  it('opens a detail sheet with reasons, the people behind them, and actions; no AI call when AI is off', () => {
    renderList(advice());
    expect(screen.queryByText('Tip')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Show 1 more' }));
    expect(screen.getByText('Tip')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Rice is selling less/ }));
    const sheet = screen.getByRole('dialog');
    expect(within(sheet).getByText(/Kofi, Ama/)).toBeInTheDocument();
    expect(within(sheet).getByText('Call or message the 2 regular buyers who stopped buying Rice.')).toBeInTheDocument();
    expect(within(sheet).getByText(/AI explanations are not switched on/)).toBeInTheDocument();
    expect(request).not.toHaveBeenCalled();
    fireEvent.click(within(sheet).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('fetches the AI explanation on tap and renders it safely, dropping unsafe links', async () => {
    request.mockResolvedValueOnce({
      id: 'a',
      explanation: 'Fewer **regular buyers**. <script>alert(1)</script>',
      news: [
        { title: 'Rice prices up', url: 'https://news.test/a', source: 'news.test', date: '20261010' },
        { title: 'Evil', url: 'javascript:alert(1)', source: 'x', date: '' },
      ],
      cached: false,
      created_at: '',
    });
    renderList(advice({ ai_available: true }));
    fireEvent.click(screen.getByRole('button', { name: /Rice is selling less/ }));
    const sheet = screen.getByRole('dialog');
    await waitFor(() => expect(within(sheet).getByText('regular buyers').tagName).toBe('STRONG'));
    expect(request).toHaveBeenCalledWith('/api/businesses/b1/insights/a/explain?from=2026-10-01&to=2026-10-30', expect.objectContaining({ method: 'POST' }));
    expect(sheet.querySelector('script')).toBeNull();
    expect(within(sheet).getByRole('link', { name: 'Rice prices up' })).toHaveAttribute('rel', 'noopener noreferrer');
    expect(within(sheet).queryByText('Evil')).toBeNull();
  });
});
