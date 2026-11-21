// Workspace entry point: restore the session, then mount the shell.

import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router';
import '../styles/base.css';
import '../styles/app.css';
import { ApiError, navigation, refreshSession, request } from '../lib/api';
import { toast, Toasts } from '../lib/toast';
import type { Business, BalanceHistoryRow, ConversationSummary, Identity, User } from '../lib/types';
import { pagePath, resolvePageName } from './routes';
import { Shell } from './Shell';
import { WorkspaceProvider, type SetupFlags } from './workspace';

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    // Legacy runLoad: surface load failures as toasts, except auth (handled by redirect).
    onError: (error, query) => {
      if (query.meta?.silent) return;
      if (error instanceof ApiError && error.status === 401) return;
      if (error instanceof DOMException && error.name === 'AbortError') return;
      toast(error.message, { error: true });
    },
  }),
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
});

interface Boot {
  user: User;
  business: Business;
  setup: SetupFlags;
}

function BootSplash() {
  return (
    <div className="boot" id="boot" role="status">
      <svg className="brand-mark" viewBox="0 0 20 20" aria-hidden="true">
        <rect x="1" y="12" width="5" height="5" rx="1" />
        <rect x="7.5" y="7.5" width="5" height="5" rx="1" />
        <rect x="14" y="3" width="5" height="5" rx="1" />
      </svg>
      <span>Opening your workspace…</span>
    </div>
  );
}

function App() {
  const [boot, setBoot] = useState<Boot | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let identity: Identity;
      try {
        await refreshSession();
        identity = await request<Identity>('/api/auth/me');
      } catch {
        navigation.replace('/?signin');
        return;
      }
      const { user, business } = identity;
      if (!business) {
        toast('This account has no business workspace.', { error: true });
        return;
      }
      const path = (suffix: string) => `/api/businesses/${business.id}${suffix}`;
      const [history, conversations] = await Promise.all([
        request<BalanceHistoryRow[]>(path('/financial-position/history?limit=1')).catch(() => []),
        request<ConversationSummary[]>(path('/ask-lance/conversations')).catch(() => []),
      ]);
      if (!cancelled) setBoot({ user, business, setup: { balances: history.length > 0, conversations: conversations.length > 0 } });
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      {boot ? (
        <WorkspaceProvider initialUser={boot.user} initialBusiness={boot.business} initialSetup={boot.setup}>
          <Shell />
        </WorkspaceProvider>
      ) : (
        <BootSplash />
      )}
      <Toasts />
    </>
  );
}

// Old links such as /app#inventory become /app/inventory before the router reads the URL.
if (window.location.hash.length > 1 && /^\/app\/?$/.test(window.location.pathname)) {
  window.history.replaceState(null, '', pagePath(resolvePageName(window.location.hash)) + window.location.search);
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root');
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
