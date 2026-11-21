// Number, money and date formatting shared by every view.

let currency = 'GHS';
export const setCurrency = (code: string | null | undefined): void => {
  currency = code || 'GHS';
};

const moneyFormatters = new Map<string, Intl.NumberFormat>();
function moneyFormatter(code: string, compact: boolean): Intl.NumberFormat {
  const key = `${code}:${compact}`;
  let formatter = moneyFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(code === 'GHS' ? 'en-GH' : 'en-US', {
      style: 'currency',
      currency: code,
      currencyDisplay: 'narrowSymbol',
      notation: compact ? 'compact' : 'standard',
      minimumFractionDigits: compact ? 0 : 2,
      maximumFractionDigits: compact ? 1 : 2,
    });
    moneyFormatters.set(key, formatter);
  }
  return formatter;
}

type Numeric = number | string | null | undefined;

export function money(value: Numeric, { compact = false, code = currency }: { compact?: boolean; code?: string } = {}): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  try {
    return moneyFormatter(code, compact).format(Number(value));
  } catch {
    return `${code} ${Number(value).toFixed(2)}`;
  }
}

export const number = (value: Numeric, digits = 0): string =>
  value === null || value === undefined ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits });

export const percent = (value: Numeric, digits = 1): string =>
  value === null || value === undefined ? '—' : `${Number(value) > 0 ? '+' : ''}${Number(value).toFixed(digits)}%`;

export const plainPercent = (value: Numeric, digits = 1): string =>
  value === null || value === undefined ? '—' : `${Number(value).toFixed(digits)}%`;

export function formatDate(
  value: string | number | Date | null | undefined,
  options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' },
): string {
  if (!value) return '—';
  const date = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString('en-GB', options);
}

export const formatDateTime = (value: string | number | Date | null | undefined): string =>
  value ? new Date(value).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—';

export function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export const plural = (count: number, word: string, many = `${word}s`): string => `${number(count)} ${count === 1 ? word : many}`;

/** Only http(s) links from API data may become hrefs; anything else (e.g. javascript:) is dropped. */
export function safeHref(url: unknown): string | undefined {
  if (typeof url !== 'string') return undefined;
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:' ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
