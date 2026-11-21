// Contains a crash to the page that threw, so the sidebar and other pages keep working.
// A failed lazy chunk (typically a tab left open across a deploy, whose old hashed files
// are gone) reloads the page once to pick up the new build.

import { Component, type ErrorInfo, type ReactNode } from 'react';

const RELOAD_KEY = 'ferlance-chunk-reload-at';
/** At most one automatic reload per minute, so a genuinely missing chunk can't loop. */
const RELOAD_COOLDOWN_MS = 60_000;

export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(message);
}

interface State {
  error: Error | null;
}

export class PageErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page crashed', error, info.componentStack);
    if (isChunkLoadError(error)) {
      try {
        const last = Number(sessionStorage.getItem(RELOAD_KEY) || 0);
        if (Date.now() - last > RELOAD_COOLDOWN_MS) {
          sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
          window.location.reload();
        }
      } catch {
        /* storage unavailable: fall through to the manual reload button */
      }
    }
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="empty-state" role="alert">
        <strong>This page could not be displayed</strong>
        <span>
          {isChunkLoadError(this.state.error)
            ? 'Ferlance was updated while this tab was open. Reload to get the latest version.'
            : 'Something went wrong while showing this page. Your data is safe — reload to try again.'}
        </span>
        <button className="btn btn-secondary btn-sm" type="button" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    );
  }
}
