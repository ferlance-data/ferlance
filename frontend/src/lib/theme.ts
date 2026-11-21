// Theme handling for Settings (legacy views/settings.js).

export const THEME_KEY = 'ferlance-theme';
export type ThemeChoice = 'system' | 'light' | 'dark';

export const isThemeChoice = (value: unknown): value is ThemeChoice => value === 'system' || value === 'light' || value === 'dark';

export function applyTheme(choice: string): void {
  const dark = choice === 'dark' || (choice === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', dark ? '#0f1c1b' : '#fbfaf6');
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
 * Follow the OS colour scheme while the saved choice is "system". Legacy registered
 * this once for the page's lifetime (so it kept working after leaving Settings); this
 * does the same, guarded so repeated calls register a single listener.
 */
export function followSystemTheme(): void {
  if (following || typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
  following = true;
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (savedTheme() === 'system') applyTheme('system');
  });
}

