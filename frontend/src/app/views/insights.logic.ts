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
