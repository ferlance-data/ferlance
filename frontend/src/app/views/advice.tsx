// Advice: plain-language "what to do" cards, and a detail sheet that opens on tap with the
// evidence, likely reasons, actions and, when AI is set up, Lance's explanation.

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import '../../styles/advice.css';
import { request } from '../../lib/api';
import { formatDate, safeHref } from '../../lib/format';
import { Icon, IconSlot } from '../../lib/icons';
import { Markdown } from '../../lib/markdown';
import type { Advice, AdviceExplanation, AdviceItem } from '../../lib/types';
import { Pill, SkeletonRows } from '../components/ui';
import { useScope, useWorkspace } from '../workspace';
import { SEVERITY, evidenceText, visibleAdvice } from './advice.logic';

function AdviceCard({ item, onOpen }: { item: AdviceItem; onOpen: (item: AdviceItem) => void }) {
  const severity = SEVERITY[item.severity];
  return (
    <li>
      <button type="button" className={`advice-card advice-${item.severity}`} onClick={() => onOpen(item)} aria-haspopup="dialog">
        <span className="advice-icon" aria-hidden="true">
          <Icon name={severity.icon} />
        </span>
        <span className="advice-text">
          <span className="advice-meta">
            <Pill tone={severity.tone}>{severity.label}</Pill>
          </span>
          <strong className="advice-title">{item.title}</strong>
          <span className="advice-summary">{item.summary}</span>
          {item.actions[0] ? <span className="advice-next">{`Next step: ${item.actions[0]}`}</span> : null}
        </span>
        <span className="advice-chevron" aria-hidden="true">
          <Icon name="arrow-right" />
        </span>
      </button>
    </li>
  );
}

function Explanation({ item, advice }: { item: AdviceItem; advice: Advice }) {
  const { business, businessPath } = useWorkspace();
  const { params } = useScope();
  const qs = params().toString();
  const query = useQuery({
    queryKey: ['explain', business.id, item.id, qs],
    queryFn: ({ signal }) => request<AdviceExplanation>(businessPath(`/insights/${item.id}/explain${qs ? `?${qs}` : ''}`), { method: 'POST', signal }),
    enabled: advice.ai_available,
    staleTime: Infinity,
    retry: false,
    meta: { silent: true },
  });

  if (!advice.ai_available) {
    return (
      <p className="body-sm muted">
        AI explanations are not switched on for this workspace. Everything above is calculated directly from your records.
      </p>
    );
  }
  if (query.isPending) {
    return (
      <div role="status" aria-live="polite">
        <p className="body-sm muted">Lance is looking into this…</p>
        <SkeletonRows count={3} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="notice notice-warning">
        <span>{query.error.message}</span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void query.refetch()}>
          Try again
        </button>
      </div>
    );
  }
  const news = query.data.news
    .map((entry) => ({ ...entry, href: safeHref(entry.url) }))
    .filter((entry) => entry.href);
  return (
    <div className="advice-ai">
      <div className="message-body">
        <Markdown source={query.data.explanation} />
      </div>
      {news.length ? (
        <div className="advice-news">
          <h4>News that may be related</h4>
          <ul>
            {news.map((entry) => (
              <li key={entry.url}>
                <a href={entry.href} target="_blank" rel="noopener noreferrer">
                  {entry.title}
                </a>
                <small className="muted">{` · ${entry.source}`}</small>
              </li>
            ))}
          </ul>
          <p className="footnote">Headlines from the free GDELT news index. They are leads to read, not proof.</p>
        </div>
      ) : null}
      <p className="footnote">Written by AI from the evidence above. It can be wrong, so check it against your own knowledge of the business.</p>
    </div>
  );
}

function AdviceDetail({ item, advice, onClose }: { item: AdviceItem; advice: Advice; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    // No cleanup: removing the element ends the modal, and a close() here would fire onClose
    // during StrictMode's effect replay and shut the sheet straight away.
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  const severity = SEVERITY[item.severity];
  return (
    <dialog
      ref={ref}
      className="advice-sheet"
      aria-labelledby="advice-sheet-title"
      onClose={onClose}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="advice-sheet-body">
        <header className="advice-sheet-head">
          <div>
            <Pill tone={severity.tone}>{severity.label}</Pill>
            <h2 id="advice-sheet-title">{item.title}</h2>
            <p className="body-sm">{item.summary}</p>
          </div>
          <button type="button" className="btn btn-ghost btn-icon" aria-label="Close" onClick={onClose}>
            <Icon name="x" />
          </button>
        </header>

        {item.evidence.length ? (
          <section aria-label="Numbers behind this">
            <h3>The numbers</h3>
            <dl className="advice-evidence">
              {item.evidence.map((entry) => (
                <div key={entry.label}>
                  <dt>{entry.label}</dt>
                  <dd className="num">{evidenceText(entry)}</dd>
                </div>
              ))}
            </dl>
            {advice.period && advice.comparison_period ? (
              <p className="footnote">{`${formatDate(advice.period.from)} – ${formatDate(advice.period.to)}, compared with ${formatDate(advice.comparison_period.from)} – ${formatDate(advice.comparison_period.to)}.`}</p>
            ) : null}
          </section>
        ) : null}

        <section>
          <h3>Why this may be happening</h3>
          {item.reasons.length ? (
            <ul className="advice-reasons">
              {item.reasons.map((reason, index) => (
                <li key={index}>
                  <Pill tone={reason.confidence === 'likely' ? 'info' : ''}>{reason.confidence === 'likely' ? 'Likely' : 'Possible'}</Pill>
                  <span>
                    {reason.text}
                    {reason.people?.length ? <span className="advice-people">{` (${reason.people.join(', ')})`}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="body-sm muted">Your records do not show a clear cause. Lance's explanation below may suggest some.</p>
          )}
        </section>

        <section>
          <h3>What to do</h3>
          <ol className="advice-actions">
            {item.actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>
        </section>

        <section className="advice-ai-section">
          <h3>
            <IconSlot name="sparkles" />
            Lance explains
          </h3>
          <Explanation item={item} advice={advice} />
        </section>
      </div>
    </dialog>
  );
}

/** Advice list with a detail sheet. `limit` shows only the top items (Overview); otherwise a "show all" toggle. */
export function AdviceList({ advice, limit }: { advice: Advice | undefined; limit?: number }) {
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState<AdviceItem | null>(null);
  if (!advice) return null;
  const items = visibleAdvice(advice, expanded && !limit).slice(0, limit ?? Infinity);
  const hidden = advice.items.length - items.length;
  return (
    <>
      {items.length ? (
        <ul className="advice-list">
          {items.map((item) => (
            <AdviceCard key={item.id} item={item} onOpen={setOpen} />
          ))}
        </ul>
      ) : (
        <p className="body-sm muted">Nothing needs your attention in this period. Try a longer date range to compare more.</p>
      )}
      {!limit && hidden > 0 ? (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setExpanded(true)}>
          {`Show ${hidden} more`}
        </button>
      ) : null}
      {open ? <AdviceDetail item={open} advice={advice} onClose={() => setOpen(null)} /> : null}
    </>
  );
}

export function AdviceMissing({ advice }: { advice: Advice | undefined }) {
  if (!advice?.missing.length) return null;
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Get sharper suggestions</h2>
          <p className="card-subtitle">What your records are missing</p>
        </div>
      </div>
      <ul className="card-body advice-missing">
        {advice.missing.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

export function SeasonCard({ advice }: { advice: Advice | undefined }) {
  const events = advice?.calendar ?? [];
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Season and calendar</h2>
          <p className="card-subtitle">Ghanaian holidays and seasons that differ between the two periods</p>
        </div>
      </div>
      <div className="card-body">
        {events.length ? (
          <ul className="advice-missing">
            {events.map((event) => (
              <li key={`${event.window}-${event.name}`}>
                {`${event.name}: ${event.window === 'previous' ? 'in the previous period only' : 'in this period only'}.`}
                {event.note ? <span className="muted">{` ${event.note}`}</span> : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="body-sm muted">No festive, school or religious season separates these two periods.</p>
        )}
      </div>
    </div>
  );
}
