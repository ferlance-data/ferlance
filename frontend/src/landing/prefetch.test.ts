import { describe, expect, it } from 'vitest';
import { workspaceAssets } from './prefetch';

const html = `<!doctype html><html><head>
  <script type="module" crossorigin src="/assets/app-abc.js"></script>
  <link rel="modulepreload" crossorigin href="/assets/vendor-def.js">
  <link rel="modulepreload" crossorigin href="/assets/vendor-def.js">
  <link rel="stylesheet" crossorigin href="/assets/app-ghi.css">
  <script src="https://cdn.example.com/x.js"></script>
  <script>window.inline = true</script>
  <link rel="icon" href="/favicon.svg">
</head><body></body></html>`;

describe('workspaceAssets', () => {
  it('lists same-origin scripts, module preloads and stylesheets once, keeping crossorigin', () => {
    expect(workspaceAssets(html, 'https://ferlance.test/')).toEqual([
      { href: '/assets/app-abc.js', as: 'script', crossOrigin: '' },
      { href: '/assets/vendor-def.js', as: 'script', crossOrigin: '' },
      { href: '/assets/app-ghi.css', as: 'style', crossOrigin: '' },
    ]);
  });

  it('returns nothing for an empty or failed response', () => {
    expect(workspaceAssets('', 'https://ferlance.test/')).toEqual([]);
  });
});
