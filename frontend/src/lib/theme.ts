// Workspace theme: saved choice (system/light/dark) and how it is applied.

export const THEME_KEY = 'ferlance-theme';
export type ThemeChoice = 'system' | 'light' | 'dark';

export const isThemeChoice = (value: unknown): value is ThemeChoice => value === 'system' || value === 'light' || value === 'dark';

export function applyTheme(choice: string): void {
  const dark = choice === 'dark' || (choice === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  // Browser UI colour must be a literal: it matches --graphite-950 / --mud-50. color-lint: allow
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0f0f11' : '#fbfaf6'); // color-lint: allow
}

export function savedTheme(): string {
  try {
    return localStorage.getItem(THEME_KEY) || 'system';
  } catch {
    return 'system';
  }
}

let following = false;

/**
 * Follow the OS colour scheme while the saved choice is "system". Registered once
 * for the page's lifetime (so it keeps working after leaving Settings),
 * guarded so repeated calls register a single listener.
 */
export function followSystemTheme(): void {
  if (following || typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
  following = true;
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (savedTheme() === 'system') applyTheme('system');
  });
}

