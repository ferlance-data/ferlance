import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { applyTheme, savedTheme, THEME_KEY } from './theme';

function mockMedia(matches: boolean) {
  const listeners: (() => void)[] = [];
  const media = { matches, addEventListener: (_: string, fn: () => void) => listeners.push(fn) };
  vi.stubGlobal('matchMedia', vi.fn(() => media));
  return { media, listeners };
}

describe('theme', () => {
  beforeEach(() => {
    document.head.replaceChildren();
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    meta.content = '#000';
    document.head.append(meta);
    localStorage.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it('applies explicit choices and the theme-color meta', () => {
    mockMedia(false);
    applyTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('#0f0f11');
    applyTheme('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(document.querySelector('meta[name="theme-color"]')?.getAttribute('content')).toBe('#fbfaf6');
  });

  it('resolves system from the OS preference', () => {
    mockMedia(true);
    applyTheme('system');
    expect(document.documentElement.dataset.theme).toBe('dark');
    mockMedia(false);
    applyTheme('system');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('reads the saved theme with a system fallback', () => {
    expect(savedTheme()).toBe('system');
    localStorage.setItem(THEME_KEY, 'dark');
    expect(savedTheme()).toBe('dark');
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(savedTheme()).toBe('system');
  });

  it('registers a single OS listener that only acts while the choice is system', async () => {
    const { media, listeners } = mockMedia(true);
    vi.resetModules();
    const fresh = await import('./theme');
    fresh.followSystemTheme();
    expect(listeners).toHaveLength(1);
    localStorage.setItem(THEME_KEY, 'light');
    document.documentElement.dataset.theme = 'light';
    listeners[0]?.();
    expect(document.documentElement.dataset.theme).toBe('light');
    localStorage.setItem(THEME_KEY, 'system');
    listeners[0]?.();
    expect(media.matches).toBe(true);
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});
