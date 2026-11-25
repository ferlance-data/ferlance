import { describe, expect, it } from 'vitest';
import { PAGES } from '../app/routes';
import { GUIDE_LANGS, GUIDES, guideScript, guideVideo } from './guides';

// Keys are the files that exist under public/assets/demo (nothing is loaded).
const shipped = new Set(Object.keys(import.meta.glob('../../public/assets/demo/*')).map((key) => key.replace('../../public', '')));

describe('guides', () => {
  it('have unique slugs and point at real pages', () => {
    expect(new Set(GUIDES.map((guide) => guide.slug)).size).toBe(GUIDES.length);
    const pages = new Set(PAGES.map((page) => page.name as string));
    for (const guide of GUIDES) expect(pages.has(guide.page), guide.slug).toBe(true);
  });

  it('ship a narrated video in every language, a script and a poster for every guide', () => {
    for (const guide of GUIDES) {
      expect(guide.steps.length).toBeGreaterThan(0);
      expect(shipped.has(guide.poster), guide.poster).toBe(true);
      for (const lang of GUIDE_LANGS) {
        expect(shipped.has(guideVideo(guide.slug, lang.code)), `${guide.slug} ${lang.code}`).toBe(true);
        expect(guideScript(guide.slug, lang.code).length, `${guide.slug} ${lang.code} script`).toBeGreaterThan(40);
      }
    }
  });
});
