// Settings: profile, appearance and administration.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate } from '../../lib/format';
import { toast } from '../../lib/toast';
import { DataTable, StatusText, type Column } from '../components/ui';
import { useWorkspace } from '../workspace';
import { applyTheme, savedTheme, THEME_KEY, type ThemeChoice } from '../../lib/theme';

interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  created_at: string;
  role: string;
}
interface ProfileResult {
  user: { full_name: string | null; email: string; id: string; role: string };
  business: { name: string };
}
interface Status {
  message: string;
  error: boolean;
}

const THEMES: { value: ThemeChoice; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];
const ROLES = ['owner', 'member', 'admin'];

export default function Settings() {
  return (
    <div className="settings">
      <ProfileCard />
      <AppearanceCard />
      <AdminCard />
    </div>
  );
}

function ProfileCard() {
  const { user, business, updateIdentity } = useWorkspace();
  const [name, setName] = useState(user.full_name || '');
  const [businessName, setBusinessName] = useState(business.name);
  const [status, setStatus] = useState<Status | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request<ProfileResult>('/api/auth/profile', {
        method: 'PATCH',
        json: { full_name: name, business_name: businessName },
      });
      updateIdentity({ user: result.user, business: result.business });
      setStatus({ message: 'Saved.', error: false });
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  return (
    <form className="card" id="profile-form" onSubmit={(event) => void submit(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">Profile</h2>
          <p className="card-subtitle">Your name and business details</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <label className="field">
          Full name
          <input className="input" id="profile-name" maxLength={120} autoComplete="name" value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="field">
          Business name
          <input
            className="input"
            id="profile-business"
            maxLength={120}
            required
            autoComplete="organization"
            value={businessName}
            onChange={(event) => setBusinessName(event.target.value)}
          />
        </label>
        <label className="field">
          Email
          <input className="input" id="profile-email" disabled value={user.email} readOnly />
        </label>
        <div className="button-row">
          <button className="btn btn-primary" type="submit">
            Save profile
          </button>
          <StatusText id="profile-status" message={status?.message} error={status?.error} />
        </div>
      </div>
    </form>
  );
}

function AppearanceCard() {
  const [choice, setChoice] = useState(savedTheme);
  // The OS-follow listener is registered once at boot (src/app/main.tsx -> followSystemTheme).
  function pick(value: ThemeChoice) {
    setChoice(value);
    try {
      localStorage.setItem(THEME_KEY, value);
    } catch {
      /* storage unavailable */
    }
    applyTheme(value);
  }
  return (
    <div className="card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Appearance</h2>
          <p className="card-subtitle">Choose how the workspace looks on this device</p>
        </div>
      </div>
      <div className="card-body">
        <div className="segmented" id="theme-picker" role="group" aria-label="Theme">
          {THEMES.map((theme) => (
            <button key={theme.value} type="button" data-theme-choice={theme.value} aria-pressed={choice === theme.value} onClick={() => pick(theme.value)}>
              {theme.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function AdminCard() {
  const { user } = useWorkspace();
  const queryClient = useQueryClient();
  // A 403 is expected for non-admins; resolve to null instead of throwing so the
  // global QueryCache handler never toasts it.
  const capable = useQuery({
    queryKey: ['admin', 'capabilities'],
    queryFn: async ({ signal }) => {
      try {
        return await request<unknown>('/api/admin/capabilities', { signal });
      } catch {
        return null;
      }
    },
    retry: false,
  });
  const allowed = capable.data !== null && capable.data !== undefined;
  const users = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: ({ signal }) => request<AdminUser[]>('/api/admin/users', { signal }),
    enabled: allowed,
  });
  if (!allowed) return null;

  async function changeRole(item: AdminUser, role: string) {
    try {
      await request(`/api/admin/users/${item.id}/role`, { method: 'PATCH', json: { role } });
      toast(`${item.email} is now ${role}.`);
    } catch (error) {
      toast((error as Error).message, { error: true });
      await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    }
  }

  const columns: Column<AdminUser>[] = [
    {
      label: 'User',
      value: (item) => (
        <div className="file-cell">
          <strong>{item.email}</strong>
          <small>{item.full_name || '—'}</small>
        </div>
      ),
    },
    { label: 'Joined', value: (item) => formatDate(item.created_at) },
    {
      label: 'Role',
      value: (item) => (
        <select
          className="select"
          style={{ width: '130px' }}
          disabled={item.id === user.id}
          aria-label={`Role for ${item.email}`}
          defaultValue={item.role}
          key={`${item.id}-${item.role}-${users.dataUpdatedAt}`}
          onChange={(event) => void changeRole(item, event.target.value)}
        >
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      ),
    },
  ];

  return (
    <div className="card" id="admin-card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Administration</h2>
          <p className="card-subtitle">Platform users and roles</p>
        </div>
      </div>
      <div className="table-wrap" id="admin-users">
        {users.data ? <DataTable columns={columns} rows={users.data} rowKey={(item) => item.id} /> : null}
      </div>
    </div>
  );
}
