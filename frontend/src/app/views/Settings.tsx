// Settings: profile, appearance and administration.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate } from '../../lib/format';
import { toast } from '../../lib/toast';
import { DataTable, StatusText, type Column } from '../components/ui';
import { ROLE_LABEL, useWorkspace } from '../workspace';
import type { Business, BusinessRole } from '../../lib/types';
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
}
interface TeamMember {
  user_id: string;
  email: string;
  full_name: string | null;
  role: BusinessRole;
  created_at: string;
}
interface PendingInvite {
  id: string;
  role: BusinessRole;
  created_at: string;
  expires_at: string;
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
      <TeamCard />
      <AdminCard />
    </div>
  );
}

function ProfileCard() {
  const { user, business, updateIdentity, businessPath, can, role } = useWorkspace();
  const canRename = can('manage_business');
  const [name, setName] = useState(user.full_name || '');
  const [businessName, setBusinessName] = useState(business.name);
  const [status, setStatus] = useState<Status | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const result = await request<ProfileResult>('/api/auth/profile', { method: 'PATCH', json: { full_name: name } });
      updateIdentity({ user: result.user });
      if (canRename && businessName.trim() !== business.name) {
        const renamed = await request<Business>(businessPath(''), { method: 'PATCH', json: { name: businessName } });
        updateIdentity({ business: { name: renamed.name } });
      }
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
            disabled={!canRename}
            value={businessName}
            onChange={(event) => setBusinessName(event.target.value)}
          />
          {canRename ? null : <span className="field-hint">{`Only the owner can rename the business. Your role: ${ROLE_LABEL[role]}.`}</span>}
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

function TeamCard() {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const allowed = can('manage_team');
  const teamKey = ['team', business.id];
  const team = useQuery({
    queryKey: teamKey,
    queryFn: ({ signal }) => request<{ members: TeamMember[]; invites: PendingInvite[] }>(businessPath('/team'), { signal }),
    enabled: allowed,
  });
  const [role, setRole] = useState<BusinessRole>('manager');
  const [link, setLink] = useState<string | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  if (!allowed) return null;
  const refresh = () => queryClient.invalidateQueries({ queryKey: teamKey });

  async function run(action: () => Promise<unknown>, done: string) {
    try {
      await action();
      await refresh();
      setStatus({ message: done, error: false });
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  async function createInvite(event: FormEvent) {
    event.preventDefault();
    try {
      const invite = await request<{ path: string }>(businessPath('/invites'), { method: 'POST', json: { role } });
      setLink(`${window.location.origin}${invite.path}`);
      await refresh();
      setStatus(null);
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      toast('Invite link copied. Share it on WhatsApp or SMS.');
    } catch {
      toast('Copy the link from the box.', { error: true });
    }
  }

  const columns: Column<TeamMember>[] = [
    {
      label: 'Person',
      value: (member) => (
        <div className="file-cell">
          <strong>{member.full_name || member.email}</strong>
          <small>{member.email}</small>
        </div>
      ),
    },
    {
      label: 'Role',
      value: (member) =>
        member.role === 'owner' ? (
          <span>Owner</span>
        ) : (
          <select
            className="select"
            aria-label={`Role for ${member.email}`}
            value={member.role}
            onChange={(event) => void run(() => request(businessPath(`/members/${member.user_id}`), { method: 'PATCH', json: { role: event.target.value } }), 'Role updated.')}
          >
            <option value="manager">Manager</option>
            <option value="accountant">Accountant</option>
          </select>
        ),
    },
    {
      label: '',
      value: (member) =>
        member.role === 'owner' ? null : (
          <button
            className="btn btn-ghost btn-sm"
            type="button"
            onClick={() => void run(() => request(businessPath(`/members/${member.user_id}`), { method: 'DELETE' }), `${member.email} no longer has access.`)}
          >
            Remove
          </button>
        ),
    },
  ];

  return (
    <div className="card" id="team-card">
      <div className="card-header">
        <div>
          <h2 className="card-title">Team</h2>
          <p className="card-subtitle">Give a manager or your accountant their own sign-in</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <ul className="role-help">
          <li>
            <strong>Manager</strong>: imports data, manages stock and balances, uses Ask Lance. Cannot manage the team.
          </li>
          <li>
            <strong>Accountant</strong>: sees everything, records balances, prints reports and uses Ask Lance. Cannot change sales or stock.
          </li>
        </ul>
        <form className="field-inline" onSubmit={(event) => void createInvite(event)}>
          <label className="field">
            Invite as
            <select className="select" id="invite-role" value={role} onChange={(event) => setRole(event.target.value as BusinessRole)}>
              <option value="manager">Manager</option>
              <option value="accountant">Accountant</option>
            </select>
          </label>
          <button className="btn btn-primary" type="submit">
            Create invite link
          </button>
        </form>
        {link ? (
          <div className="invite-link">
            <label className="field">
              Invite link (works once, expires in 7 days)
              <input className="input" id="invite-link" readOnly value={link} onFocus={(event) => event.target.select()} />
            </label>
            <button className="btn btn-secondary" type="button" onClick={() => void copy()}>
              Copy link
            </button>
          </div>
        ) : null}
        <StatusText id="team-status" message={status?.message} error={status?.error} />
      </div>
      <div className="table-wrap">
        {team.data ? <DataTable columns={columns} rows={team.data.members} rowKey={(member) => member.user_id} /> : null}
      </div>
      {team.data?.invites.length ? (
        <div className="card-body">
          <h3 className="card-title">Pending invites</h3>
          <ul className="pending-invites">
            {team.data.invites.map((pending) => (
              <li key={pending.id}>
                <span>{`${ROLE_LABEL[pending.role]} · expires ${formatDate(pending.expires_at)}`}</span>
                <button
                  className="btn btn-ghost btn-sm"
                  type="button"
                  onClick={() => void run(() => request(businessPath(`/invites/${pending.id}`), { method: 'DELETE' }), 'Invite cancelled.')}
                >
                  Cancel
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
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
