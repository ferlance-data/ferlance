import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from '../../lib/router';
import { request } from '../../lib/api';
import { formatDate, money, number } from '../../lib/format';
import { IconSlot } from '../../lib/icons';
import { analysableDatasets } from '../../lib/scope';
import type { Analytics, InsightsResponse, Period } from '../../lib/types';
import { Delta, EmptyState, SkeletonRows, StatusText } from '../components/ui';
import { useBusinessQuery, useScopedQuery } from '../hooks';
import { pagePath } from '../routes';
import { useScope, useWorkspace } from '../workspace';
import { comparisonRows, sourcesFor, type ResearchResult } from './insights.logic';
import { InsightCard } from './shared';

export function ResearchResults({ result }: { result: ResearchResult }) {
  const findings = result.findings ?? [];
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Market context</h2>
          <p className="card-subtitle">Contextual leads, not proof of cause</p>
        </div>
      </div>
      <div className="card-body research">
        {result.analysis_error ? <div className="notice notice-warning">{`Automated analysis is unavailable: ${result.analysis_error}`}</div> : null}
        {result.analysis ? (
          <p className="body-sm" style={{ whiteSpace: 'pre-wrap' }}>
            {result.analysis}
          </p>
        ) : null}
        {!findings.length ? <p className="body-sm muted">{result.analysis || 'No losses or material declines were detected for this period.'}</p> : null}
        {findings.map((finding, index) => {
          const sources = sourcesFor(result, finding.product);
          return (
            <div className="research-finding" key={`${finding.product}-${index}`}>
              <h3 className="card-title">{`${finding.finding} · ${finding.product}`}</h3>
              {sources.length ? (
                sources.map((source, sourceIndex) => {
                  const text = `[${source.id}] ${source.title}`;
                  return (
                    <div className="research-source" key={`${source.id}-${sourceIndex}`}>
                      {source.href ? (
                        <a href={source.href} target="_blank" rel="noopener noreferrer">
                          {text}
                        </a>
                      ) : (
                        <span>{text}</span>
                      )}
                      <span className="muted">{source.description}</span>
                      {source.age ? <small className="muted">{source.age}</small> : null}
                    </div>
                  );
                })
              ) : (
                <p className="body-sm muted">No matching sources were returned.</p>
              )}
            </div>
          );
        })}
        {(result.limitations ?? []).map((note, index) => (
          <p className="footnote" key={index}>
            {note}
          </p>
        ))}
      </div>
    </div>
  );
}

type AnalyticsWithPeriod = Analytics & { comparison: Analytics['comparison'] & { period?: Period } };

function Comparison({ comparison }: { comparison: Analytics['comparison'] | null | undefined }) {
  if (!comparison?.available || !comparison.metrics || !comparison.previous_period) {
    return <p className="body-sm muted">{comparison?.reason || 'Choose a date range to compare.'}</p>;
  }
  return (
    <div className="comparison-rows">
      {comparisonRows(comparison.metrics).map((row) => (
        <div className="comparison-row" key={row.key}>
          <span>{row.label}</span>
          <span className="num">{row.key === 'transactions' ? number(row.current) : money(row.current)}</span>
          {row.changePct === null || row.changePct === undefined ? <span className="muted body-sm">new</span> : <Delta change={row.changePct} invert={row.key === 'cost'} />}
        </div>
      ))}
    </div>
  );
}

export default function Insights() {
  const { business, businessPath, datasets } = useWorkspace();
  const { hasData, params } = useScope();
  const qs = params().toString();
  const insights = useScopedQuery<InsightsResponse & { available_period?: Period }>('/insights', { enabled: hasData });
  const analytics = useScopedQuery<AnalyticsWithPeriod>('/analytics', { enabled: hasData });
  const brave = useBusinessQuery<{ configured: boolean }>('/integrations/brave-search');
  const configured = Boolean(brave.data?.configured);
  const canRun = configured && analysableDatasets(datasets).length > 0;

  // A result belongs to the scope it was run for; a scope change hides it.
  const [research, setResearch] = useState<{ qs: string; businessId: string; result: ResearchResult } | null>(null);
  const run = useMutation({
    mutationFn: () => request<ResearchResult>(businessPath(`/performance-research?${qs}`), { method: 'POST' }),
    onSuccess: (result) => setResearch({ qs, businessId: business.id, result }),
  });
  const shown = research && research.qs === qs && research.businessId === business.id ? research.result : null;

  let status = '';
  if (run.isPending) status = 'Searching for seasonal, weather, festive and market context…';
  else if (run.isError) status = run.error.message;
  else if (run.isSuccess && shown) status = `${number(shown.findings?.length || 0)} finding(s) · ${number(shown.sources?.length || 0)} source(s)`;

  const comparison = hasData ? analytics.data?.comparison : null;
  const period = comparison?.available && comparison.period && comparison.previous_period
    ? `${formatDate(comparison.period.from)} – ${formatDate(comparison.period.to)} vs ${formatDate(comparison.previous_period.from)} – ${formatDate(comparison.previous_period.to)}`
    : 'Against the previous period of equal length';

  let list;
  if (!hasData) {
    list = (
      <EmptyState
        title="No insights yet"
        message="Insights are calculated once you import records."
        action={
          <Link className="btn btn-primary btn-sm" to={pagePath('data')}>
            Import data
          </Link>
        }
      />
    );
  } else if (!insights.data) {
    list = (
      <div className="card card-body">
        <SkeletonRows count={4} />
      </div>
    );
  } else if (insights.data.insights.length) {
    list = insights.data.insights.map((item, index) => <InsightCard key={`${item.title}-${index}`} item={item} />);
  } else {
    list = <EmptyState title="Nothing notable in this period" message="There are not enough records to compare. Try a wider date range." />;
  }

  return (
    <>
      <div className="grid-main reverse">
        <div className="insight-stack" id="insights-list">
          {list}
        </div>
        <div className="stack">
          <div className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Comparison</h2>
                <p className="card-subtitle" id="insights-comparison-period">
                  {period}
                </p>
              </div>
            </div>
            <div className="card-body" id="insights-comparison">
              <Comparison comparison={comparison} />
            </div>
          </div>
          <div className="card">
            <div className="card-header">
              <div>
                <h2 className="card-title">Market context</h2>
                <p className="card-subtitle">Web research on declines and losses</p>
              </div>
              <span className={`pill${configured ? ' pill-success' : ''}`} id="research-pill">
                {configured ? 'Connected' : 'Not connected'}
              </span>
            </div>
            <div className="card-body">
              <p className="body-sm muted">
                When a sales decline or loss is detected, Ferlance can search the web for Ghanaian seasonal, weather, festive and market context. Only product names and dates are sent.
              </p>
              <div className="button-row">
                <button className="btn btn-primary btn-sm" id="research-run" type="button" disabled={!canRun || run.isPending} onClick={() => run.mutate()}>
                  <IconSlot name="search" />
                  Research this period
                </button>
                <Link className="btn btn-ghost btn-sm" to={pagePath('settings')}>
                  Connect search
                </Link>
              </div>
              <StatusText id="research-status" message={status} error={run.isError} />
            </div>
          </div>
        </div>
      </div>
      <div id="research-results">{shown ? <ResearchResults result={shown} /> : null}</div>
    </>
  );
}
