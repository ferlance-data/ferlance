// The admin console: a separate app at /admin (later its own subdomain), with its own sign-in.
// It uses /api/admin/auth and an admin-only refresh cookie; workspace sessions never apply here.

import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode, useEffect, useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import '../styles/base.css';
import '../styles/app.css';
import { ApiError, configureSession, refreshSession, request, setAccessToken, signOut } from '../lib/api';
import { applyTheme, followSystemTheme, savedTheme } from '../lib/theme';
import { toast, Toasts } from '../lib/toast';
import { Segmented, StatusText } from '../app/components/ui';
import { AdminConsole } from './AdminConsole';

configureSession({ base: '/api/admin/auth', signedOut: '/admin' });

interface AdminUser {
  id: string;
  email: string;
  role: string;
  full_name: string;
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error) => {
      if (error instanceof ApiError && error.status === 401) return;
      toast(error.message, { error: true });
    },
  }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 } },
});

function SignIn({ onSignedIn }: { onSignedIn: (user: AdminUser) => void }) {
  const [mode, setMode] = useState<'signin' | 'create'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const body = mode === 'signin' ? { email, password } : { email, password, full_name: name };
      const result = await request<{ access_token: string; user: AdminUser }>(`/api/admin/auth/${mode === 'signin' ? 'login' : 'signup'}`, { method: 'POST', json: body });
      setAccessToken(result.access_token);
      onSignedIn(result.user);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="admin-signin">
      <form className="card" id="admin-signin" onSubmit={(event) => void submit(event)}>
        <div className="card-header">
          <div>
            <h1 className="card-title">Ferlance Admin</h1>
            <p className="card-subtitle">For platform administrators. Business owners sign in on the main page.</p>
          </div>
        </div>
        <div className="card-body form-grid">
          <Segmented
            label="Sign in or create an admin account"
            value={mode}
            onChange={(value) => {
              setMode(value);
              setError('');
            }}
            options={[
              { value: 'signin', label: 'Sign in' },
              { value: 'create', label: 'Create admin account' },
            ]}
          />
          {mode === 'create' ? (
            <>
              <p className="footnote">Only emails listed in the server setting FERLANCE_ADMIN_EMAILS can create an admin account.</p>
              <label className="field">
                Your name
                <input className="input" autoComplete="name" maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
              </label>
            </>
          ) : null}
          <label className="field">
            Email
            <input className="input" type="email" required autoComplete="username" value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="field">
            Password
            <input
              className="input"
              type="password"
              required
              minLength={mode === 'create' ? 12 : undefined}
              autoComplete={mode === 'create' ? 'new-password' : 'current-password'}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {mode === 'create' ? <span className="field-hint">At least 12 characters.</span> : null}
          </label>
          <div className="button-row">
            <button className="btn btn-primary" type="submit" disabled={busy}>
              {mode === 'signin' ? 'Sign in' : 'Create admin account'}
            </button>
            <StatusText id="admin-signin-status" message={error} error />
          </div>
        </div>
      </form>
    </main>
  );
}

function AdminApp() {
  const [user, setUser] = useState<AdminUser | null | undefined>(undefined);

  useEffect(() => {
    refreshSession()
      .then((result) => setUser((result as unknown as { user: AdminUser }).user))
      .catch(() => setUser(null));
  }, []);

  if (user === undefined) return <div className="boot" role="status">Opening the admin console…</div>;
  if (user === null) return <SignIn onSignedIn={setUser} />;
  return (
    <div className="admin-shell">
      <header className="admin-topbar">
        <strong>Ferlance Admin</strong>
        <span className="muted body-sm">{user.email}</span>
        <button className="btn btn-ghost btn-sm" type="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </header>
      <main className="admin-main">
        <AdminConsole user={user} />
      </main>
    </div>
  );
}

applyTheme(savedTheme());
followSystemTheme();
const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <AdminApp />
        <Toasts />
      </QueryClientProvider>
    </StrictMode>,
  );
}
