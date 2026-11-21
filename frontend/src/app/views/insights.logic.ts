import { safeHref } from '../../lib/format';

export interface ResearchSource {
  id: number | string;
  product: string;
  title: string;
  description?: string;
  url?: string;
  age?: string;
}

export interface ResearchFinding {
  finding: string;
  product: string;
}

export interface ResearchResult {
  findings?: ResearchFinding[];
  sources?: ResearchSource[];
  analysis?: string;
  analysis_error?: string;
  limitations?: string[];
}

export interface ComparisonMetricRow {
  key: string;
  label: string;
  current: number;
  changePct: number | null;
}

const LABELS: Record<string, string> = {
  revenue: 'Revenue',
  cost: 'Recorded cost',
  gross_profit: 'Profit after costs',
  transactions: 'Records',
  average_sale: 'Average sale',
};

export function comparisonRows(metrics: Record<string, { current: number | null; change_pct: number | null }>): ComparisonMetricRow[] {
  return Object.entries(metrics)
    .filter(([, metric]) => metric.current !== null)
    .map(([key, metric]) => ({ key, label: LABELS[key] || key, current: metric.current as number, changePct: metric.change_pct }));
}

/** Sources for one finding. `href` is undefined for non-http(s) URLs, so the UI renders plain text. */
export function sourcesFor(result: ResearchResult, product: string): (ResearchSource & { href: string | undefined })[] {
  return (result.sources ?? []).filter((source) => source.product === product).map((source) => ({ ...source, href: safeHref(source.url) }));
}
