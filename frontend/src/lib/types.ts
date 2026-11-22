// Response shapes for the Ferlance API (see backend/routers/*). Shared types live here;
// shapes used by a single view are declared next to that view.

export interface User {
  id: string;
  email: string;
  role: 'admin' | 'owner' | 'member' | string;
  full_name: string | null;
}

export type BusinessRole = 'owner' | 'manager' | 'accountant';
export type Permission = 'read' | 'write_data' | 'write_balances' | 'use_ai' | 'manage_team' | 'manage_business';

export interface Business {
  id: string;
  name: string;
  currency: string;
  /** The signed-in user's role in this business. */
  role?: BusinessRole;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  business: Business | null;
}

export interface Identity {
  user: User;
  business: Business | null;
  /** Every business the user belongs to (owned first). */
  businesses?: Business[];
}

export type DatasetStatus = 'processed' | 'partial' | 'failed';

export interface Dataset {
  id: string;
  filename: string;
  extension: string;
  status: DatasetStatus;
  source_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  warnings: string[];
  errors: string[];
  created_at: string;
  included: boolean;
  /** Earliest and latest record dates in the file. */
  period?: Period;
  /** Present on the merged "all business data" pseudo-dataset in analytics responses. */
  files?: number;
}

export interface Period {
  from: string | null;
  to: string | null;
}

export interface TrendPoint {
  period: string;
  revenue: number;
  transactions?: number;
}

export interface CostPoint {
  period: string;
  cost: number;
}

export interface ProductRow {
  product: string;
  revenue: number;
  transactions: number;
  metric_label: string;
  metric_value: number;
  cost?: number;
  gross_profit?: number;
  margin_pct?: number;
  roi_pct?: number;
  units_sold?: number;
}

export interface CustomerRow {
  customer: string;
  revenue: number;
  cost?: number;
  transactions: number;
  metric_label: string;
  metric_value: number;
}

export interface ComparisonMetric {
  current: number | null;
  previous: number | null;
  change_pct: number | null;
}

export interface Analytics {
  period: Period;
  summary: string;
  profile: { domain: 'revenue' | 'cost' | string; label: string; value_key: string; value_label: string };
  currency: string;
  available_period: Period;
  revenue: { total: number; currency: string; transactions: number; average_sale: number };
  trend: Record<string, TrendPoint[] | CostPoint[]>;
  products: {
    available: boolean;
    quantity_available?: boolean;
    profit_available?: boolean;
    metric_label?: string;
    items: ProductRow[];
    reason?: string;
    [key: string]: unknown;
  };
  customers: {
    available: boolean;
    number_of_customers?: number;
    repeat_customers?: number;
    top_customers: CustomerRow[];
    reason?: string;
  };
  profit: { available: boolean; reason?: string; gross_profit?: number; cost?: number; margin_pct?: number; [key: string]: unknown };
  inventory: { available: boolean; reason?: string; [key: string]: unknown };
  /** Share of records (0–100) carrying each optional field. */
  coverage?: { records: number; product: number; cost: number; quantity: number; customer: number };
  kpis: {
    total_revenue: number;
    total_cost: number;
    primary_value: number;
    primary_label: string;
    transactions: number;
    average_sale: number;
    top_product: string | null;
    [key: string]: unknown;
  };
  warnings: string[];
  comparison: {
    available: boolean;
    reason?: string;
    previous_period?: Period;
    metrics?: Record<string, ComparisonMetric>;
  };
  dataset: Dataset | null;
}

export interface Insight {
  type: 'summary' | 'comparison' | 'anomaly' | 'recommendation' | string;
  title: string;
  message: string;
  severity: 'positive' | 'attention' | 'info' | string;
  supporting_metric?: Record<string, unknown>;
  limitations?: string[];
}

export type AdviceSeverity = 'risk' | 'attention' | 'opportunity' | 'info';

export interface AdviceEvidence {
  label: string;
  value: number | string;
  format: 'money' | 'percent' | 'number' | 'text';
}

export interface AdviceReason {
  text: string;
  confidence: 'likely' | 'possible';
  basis: string;
  /** Customer names behind a "regular buyers stopped" reason. Shown to the owner only. */
  people?: string[];
}

export interface AdviceItem {
  id: string;
  kind: string;
  severity: AdviceSeverity;
  title: string;
  summary: string;
  product: string | null;
  impact: number;
  evidence: AdviceEvidence[];
  reasons: AdviceReason[];
  actions: string[];
}

export interface Advice {
  items: AdviceItem[];
  /** Ids of the most important items, in order. */
  top: string[];
  /** What data would unlock more suggestions. */
  missing: string[];
  currency?: string;
  period: Period | null;
  comparison_period: Period | null;
  calendar?: { window: 'previous' | 'current'; name: string; note: string }[];
  ai_available: boolean;
}

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  date: string;
}

export interface AdviceExplanation {
  id: string;
  explanation: string;
  news: NewsItem[];
  cached: boolean;
  created_at: string;
}

export interface InsightsResponse {
  period: Period;
  comparison_period?: Period;
  comparison?: { label: string; message: string; current: number | null; previous: number | null; percent: number | null; direction: string };
  revenue_change?: { current: number | null; previous: number | null; percent: number | null; direction: string };
  insights: Insight[];
  warnings: string[];
  dataset: Dataset | null;
  advice?: Advice;
}

export interface InventoryItem {
  id: string;
  sku: string | null;
  name: string;
  unit: string;
  unit_cost: number | null;
  reorder_level: number | null;
  quantity_on_hand: number;
  stock_value: number | null;
  low_stock: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InventoryResponse {
  items: InventoryItem[];
  summary: {
    product_count: number;
    units_on_hand: number;
    low_stock_count: number;
    inventory_value: number;
    inventory_value_complete: boolean;
    uncosted_stock_items: unknown[];
  };
}

export interface Movement {
  id: string;
  product_id: string;
  product_name: string;
  sku: string | null;
  unit: string;
  movement_type: string;
  quantity_delta: number;
  unit_cost: number | null;
  stock_value_after: number | null;
  note: string | null;
  source: string;
  recorded_by: string;
  created_at: string;
}

export interface PositionBalance {
  category: string;
  account_name: string;
  as_of_date: string;
  amount: number;
  note: string | null;
  created_at: string;
}

export interface PositionResult {
  as_of_date: string;
  assets: PositionBalance[];
  liabilities: PositionBalance[];
  equity: PositionBalance[];
  totals: {
    assets: number;
    liabilities: number;
    equity: number;
    liabilities_and_equity: number;
    balance_difference: number;
    complete: boolean;
    balanced: boolean;
  };
  missing_categories: { key: string; label: string; group: string }[];
  stale_balances: { account_name: string; category: string; as_of_date: string }[];
  warnings: string[];
}

export interface BalanceHistoryRow extends PositionBalance {
  id: string;
  recorded_by: string;
}

export interface ConversationSummary {
  id: string;
  title?: string;
  updated_at?: string;
  [key: string]: unknown;
}
