// Warm the browser cache with the workspace bundle while someone signs in.
//
// It starts only when the sign-in dialog opens, because most landing visitors never sign
// in and data is expensive for many users. It is skipped when the browser asks to save data.
// The landing build cannot know the workspace's hashed file names, so they are read from
// the workspace HTML, which is small and served no-cache.

export interface WorkspaceAsset {
  href: string;
  as: 'script' | 'style';
  crossOrigin: string | null;
}

/** Same-origin scripts, module preloads and stylesheets referenced by the workspace HTML. */
export function workspaceAssets(html: string, base: string): WorkspaceAsset[] {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const assets: WorkspaceAsset[] = [];
  const seen = new Set<string>();
  const add = (raw: string | null, as: WorkspaceAsset['as'], crossOrigin: string | null) => {
    if (!raw) return;
    const url = new URL(raw, base);
    if (url.origin !== new URL(base).origin || seen.has(url.href)) return;
    seen.add(url.href);
    assets.push({ href: url.pathname + url.search, as, crossOrigin });
  };
  for (const node of doc.querySelectorAll('script[src]')) add(node.getAttribute('src'), 'script', node.getAttribute('crossorigin'));
  for (const node of doc.querySelectorAll('link[rel="modulepreload"][href]')) add(node.getAttribute('href'), 'script', node.getAttribute('crossorigin'));
  for (const node of doc.querySelectorAll('link[rel="stylesheet"][href]')) add(node.getAttribute('href'), 'style', node.getAttribute('crossorigin'));
  return assets;
}

let started = false;

export function prefetchWorkspace(): void {
  if (started) return;
  started = true;
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  if (connection?.saveData) return;
  fetch('/app/', { credentials: 'same-origin' })
    .then((response) => (response.ok ? response.text() : ''))
    .then((html) => {
      for (const asset of workspaceAssets(html, window.location.href)) {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.as = asset.as;
        link.href = asset.href;
        if (asset.crossOrigin !== null) link.crossOrigin = asset.crossOrigin;
        document.head.append(link);
      }
    })
    .catch(() => undefined);
}
