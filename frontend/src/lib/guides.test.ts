import { describe, expect, it } from 'vitest';
import { PAGES } from '../app/routes';
import { GUIDES } from './guides';

// Keys are the files that exist under public/assets/demo (nothing is loaded).
const shipped = new Set(Object.keys(import.meta.glob('../../public/assets/demo/*')).map((key) => key.replace('../../public', '')));

describe('guides', () => {
  it('have unique slugs and point at real pages', () => {
    expect(new Set(GUIDES.map((guide) => guide.slug)).size).toBe(GUIDES.length);
    const pages = new Set(PAGES.map((page) => page.name as string));
    for (const guide of GUIDES) expect(pages.has(guide.page), guide.slug).toBe(true);
  });

  it('ship a video and a poster for every guide', () => {
    for (const guide of GUIDES) {
      expect(guide.steps.length).toBeGreaterThan(0);
      for (const file of [guide.video, guide.poster]) expect(shipped.has(file), file).toBe(true);
    }
  });
});
