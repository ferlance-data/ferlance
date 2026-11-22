// Admin console for platform operators: setup funnel, users (search, role, disable/enable),
// businesses (counts only) and the audit log of admin changes.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { request } from '../../lib/api';
import { RadialProgress } from '../../lib/chart/RadialProgress';
import { formatDate, formatDateTime, number } from '../../lib/format';
import { toast } from '../../lib/toast';
import { DataTable, EmptyState, Pill, SkeletonRows, type Column } from '../components/ui';
import { useIsAdmin } from '../hooks';
import { useWorkspace } from '../workspace';

interface AdminUser {
  id: string;
  email: string;
  full_name: string | null;
  role: string;
  created_at: string;
  disabled_at: string | null;
  businesses: number;
}
interface AdminBusiness {
  id: string;
  name: string;
  owner_email: string;
  created_at: string;
  members: number;
  datasets: number;
  products: number;
  balances: number;
  conversations: number;
}
interface Funnel {
  businesses: number;
  steps: { key: string; label: string; count: number }[];
}
interface AuditEntry {
  id: string;
  action: string;
  detail: Record<string, string>;
  created_at: string;
  actor_email: string | null;
  target_email: string | null;
}

const ROLES = ['owner', 'member', 'admin'];

function auditText(entry: AuditEntry): string {
  const who = entry.target_email ?? 'a deleted user';
  if (entry.action === 'role') return `changed ${who} from ${entry.detail.before} to ${entry.detail.after}`;
  if (entry.action === 'disable') return `disabled ${who}`;
  if (entry.action === 'enable') return `re-enabled ${who}`;
  return `${entry.action} ${who}`;
}

export default function Admin() {
  const isAdmin = useIsAdmin();
  const { user } = useWorkspace();
  const queryClient = useQueryClient();
  const [userSearch, setUserSearch] = useState('');
  const [businessSearch, setBusinessSearch] = useState('');
  const users = useQuery({
    queryKey: ['admin', 'users', userSearch],
    queryFn: ({ signal }) => request<AdminUser[]>(`/api/admin/users?q=${encodeURIComponent(userSearch)}`, { signal }),
    enabled: isAdmin,
  });
  const businesses = useQuery({
    queryKey: ['admin', 'businesses', businessSearch],
    queryFn: ({ signal }) => request<AdminBusiness[]>(`/api/admin/businesses?q=${encodeURIComponent(businessSearch)}`, { signal }),
    enabled: isAdmin,
  });
  const funnel = useQuery({ queryKey: ['admin', 'onboarding'], queryFn: ({ signal }) => request<Funnel>('/api/admin/onboarding', { signal }), enabled: isAdmin });
  const audit = useQuery({ queryKey: ['admin', 'audit'], queryFn: ({ signal }) => request<AuditEntry[]>('/api/admin/audit', { signal }), enabled: isAdmin });

  if (!isAdmin) return <EmptyState title="Administrators only" message="This page is for Ferlance platform administrators." />;

  async function act(path: string, init: Parameters<typeof request>[1], done: string) {
    try {
      await request(path, init);
      toast(done);
    } catch (error) {
      toast((error as Error).message, { error: true });
    } finally {
      await queryClient.invalidateQueries({ queryKey: ['admin'] });
    }
  }

  const userColumns: Column<AdminUser>[] = [
    {
      label: 'User',
      value: (item) => (
        <div className="file-cell">
          <strong>{item.email}</strong>
          <small>{`${item.full_name || '—'} · joined ${formatDate(item.created_at)} · ${number(item.businesses)} business${item.businesses === 1 ? '' : 'es'}`}</small>
        </div>
      ),
    },
    {
      label: 'Role',
      value: (item) => (
        <select
          className="select"
          disabled={item.id === user.id}
          aria-label={`Role for ${item.email}`}
          value={item.role}
          onChange={(event) => void act(`/api/admin/users/${item.id}/role`, { method: 'PATCH', json: { role: event.target.value } }, `${item.email} is now ${event.target.value}.`)}
        >
          {ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
      ),
    },
    {
      label: 'Status',
      value: (item) => (item.disabled_at ? <Pill tone="error">{`Disabled ${formatDate(item.disabled_at)}`}</Pill> : <Pill tone="success">Active</Pill>),
    },
    {
      label: '',
      value: (item) =>
        item.id === user.id ? null : item.disabled_at ? (
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => void act(`/api/admin/users/${item.id}/enable`, { method: 'POST' }, `${item.email} can sign in again.`)}>
            Enable
          </button>
        ) : (
          <button
            className="btn btn-danger btn-sm"
            type="button"
            onClick={() => {
              if (window.confirm(`Disable ${item.email}? They are signed out everywhere and cannot sign in until re-enabled.`)) {
                void act(`/api/admin/users/${item.id}/disable`, { method: 'POST' }, `${item.email} is disabled.`);
              }
            }}
          >
            Disable
          </button>
        ),
    },
  ];

  const businessColumns: Column<AdminBusiness>[] = [
    {
      label: 'Business',
      value: (item) => (
        <div className="file-cell">
          <strong>{item.name}</strong>
          <small>{`${item.owner_email} · since ${formatDate(item.created_at)}`}</small>
        </div>
      ),
    },
    { label: 'People', num: true, value: (item) => number(item.members) },
    { label: 'Files', num: true, value: (item) => number(item.datasets) },
    { label: 'Products', num: true, value: (item) => number(item.products) },
    { label: 'Balances', num: true, value: (item) => number(item.balances) },
    { label: 'Chats', num: true, value: (item) => number(item.conversations) },
  ];

  return (
    <div className="stack" id="admin-console">
      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Setup progress</h2>
            <p className="card-subtitle">{funnel.data ? `How far ${number(funnel.data.businesses)} businesses have got` : 'Across all businesses'}</p>
          </div>
        </div>
        <div className="card-body completeness">
          {funnel.data
            ? funnel.data.steps.map((step) => (
                <div className="completeness-item" key={step.key}>
                  <RadialProgress value={step.count} max={Math.max(funnel.data.businesses, 1)} label={step.label} size={56} />
                  <div>
                    <strong>{step.label}</strong>
                    <small>{`${number(step.count)} of ${number(funnel.data.businesses)}`}</small>
                  </div>
                </div>
              ))
            : <SkeletonRows count={2} />}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Users</h2>
            <p className="card-subtitle">Platform role and account status</p>
          </div>
          <input className="input admin-search" type="search" placeholder="Search email or name" aria-label="Search users" value={userSearch} onChange={(event) => setUserSearch(event.target.value)} />
        </div>
        <div className="table-wrap" id="admin-users">
          {users.data ? <DataTable columns={userColumns} rows={users.data} rowKey={(item) => item.id} /> : <SkeletonRows count={4} />}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Businesses</h2>
            <p className="card-subtitle">Counts only; records stay private to each business</p>
          </div>
          <input className="input admin-search" type="search" placeholder="Search business or owner" aria-label="Search businesses" value={businessSearch} onChange={(event) => setBusinessSearch(event.target.value)} />
        </div>
        <div className="table-wrap" id="admin-businesses">
          {businesses.data ? <DataTable columns={businessColumns} rows={businesses.data} rowKey={(item) => item.id} /> : <SkeletonRows count={4} />}
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Admin log</h2>
            <p className="card-subtitle">Every role change, disable and enable</p>
          </div>
        </div>
        <div className="card-body">
          {audit.data?.length ? (
            <ul className="pending-invites" id="admin-audit">
              {audit.data.map((entry) => (
                <li key={entry.id}>
                  <span>{`${entry.actor_email ?? 'Someone'} ${auditText(entry)}`}</span>
                  <small className="muted">{formatDateTime(entry.created_at)}</small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="body-sm muted">No admin changes yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
