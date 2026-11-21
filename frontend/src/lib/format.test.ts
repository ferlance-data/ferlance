import { describe, expect, it } from 'vitest';
import { formatDate, isoDate, money, percent, plainPercent, plural, safeHref } from './format';

describe('format', () => {
  it('formats cedi amounts with the narrow symbol and handles missing values', () => {
    expect(money(1250.5)).toMatch(/1,250\.50/);
    expect(money(1250.5)).toContain('₵');
    expect(money(null)).toBe('—');
    expect(money('not a number')).toBe('—');
    expect(money(1500, { compact: true })).toMatch(/1\.5K/);
  });

  it('signs percentages', () => {
    expect(percent(12.345)).toBe('+12.3%');
    expect(percent(-4)).toBe('-4.0%');
    expect(plainPercent(7.5, 2)).toBe('7.50%');
    expect(percent(undefined)).toBe('—');
  });

  it('reads ISO dates as local calendar dates', () => {
    expect(formatDate('2026-03-01')).toBe('1 Mar 2026');
    expect(formatDate(null)).toBe('—');
    expect(isoDate(new Date(2026, 0, 9))).toBe('2026-01-09');
  });

  it('pluralises', () => {
    expect(plural(1, 'row')).toBe('1 row');
    expect(plural(3, 'row')).toBe('3 rows');
    expect(plural(2, 'entry', 'entries')).toBe('2 entries');
  });

  it('only allows http(s) links from API data', () => {
    expect(safeHref('https://example.com/a?b=1')).toBe('https://example.com/a?b=1');
    expect(safeHref('http://example.com')).toBe('http://example.com/');
    expect(safeHref('javascript:alert(1)')).toBeUndefined();
    expect(safeHref('data:text/html,<script>alert(1)</script>')).toBeUndefined();
    expect(safeHref(42)).toBeUndefined();
  });
});
