import { Link } from '../../lib/router';
import { formatDate, money, number } from '../../lib/format';
import type { Analytics, InsightsResponse, Period } from '../../lib/types';
import { Delta, EmptyState, SkeletonRows } from '../components/ui';
import { useScopedQuery } from '../hooks';
import { pagePath } from '../routes';
import { useScope } from '../workspace';
import { AdviceList, AdviceMissing, SeasonCard } from './advice';
import { comparisonRows } from './insights.logic';
import { InsightCard } from './shared';

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
  const { hasData } = useScope();
  const insights = useScopedQuery<InsightsResponse & { available_period?: Period }>('/insights', { enabled: hasData });
  const analytics = useScopedQuery<AnalyticsWithPeriod>('/analytics', { enabled: hasData });
  const advice = insights.data?.advice;

  const comparison = hasData ? analytics.data?.comparison : null;
  const period = comparison?.available && comparison.period && comparison.previous_period
    ? `${formatDate(comparison.period.from)} – ${formatDate(comparison.period.to)} vs ${formatDate(comparison.previous_period.from)} – ${formatDate(comparison.previous_period.to)}`
    : 'Against the previous period of equal length';

  if (!hasData) {
    return (
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
  }

  const findings = !insights.data ? (
    <div className="card card-body">
      <SkeletonRows count={4} />
    </div>
  ) : insights.data.insights.length ? (
    insights.data.insights.map((item, index) => <InsightCard key={`${item.title}-${index}`} item={item} />)
  ) : (
    <EmptyState title="Nothing notable in this period" message="There are not enough records to compare. Try a wider date range." />
  );

  return (
    <div className="grid-main reverse">
      <div className="stack">
        <div className="card">
          <div className="card-header">
            <div>
              <h2 className="card-title">What to do now</h2>
              <p className="card-subtitle">Ranked by money at stake. Tap one to see why and what to do.</p>
            </div>
          </div>
          <div className="card-body" id="advice-list">
            {insights.data ? <AdviceList advice={advice} /> : <SkeletonRows count={4} height={40} />}
          </div>
        </div>
        <div className="insight-stack" id="insights-list">
          <h2 className="card-title">Calculated findings</h2>
          {findings}
        </div>
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
        <SeasonCard advice={advice} />
        <AdviceMissing advice={advice} />
      </div>
    </div>
  );
}
