// Admin console for platform operators: setup funnel, users (search, role, disable/enable),
// businesses (counts only) and the audit log of admin changes.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useDeferredValue, useEffect, useState } from 'react';
import { request } from '../lib/api';
import { RadialProgress } from '../lib/chart/RadialProgress';
import { formatDate, formatDateTime, number } from '../lib/format';
import { toast } from '../lib/toast';
import { DataTable, Pill, SkeletonRows, type Column } from '../app/components/ui';

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

interface ExportRun {
  business_id: string;
  business_name: string;
  day: string;
  status: 'running' | 'ok' | 'failed';
  attempts: number;
  row_count: number | null;
  bytes: number | null;
  error: string | null;
  finished_at: string | null;
}
interface ExportStatus {
  enabled: boolean;
  destination: string | null;
  hour_utc: number;
  running: boolean;
  problem: string | null;
  backup: { day: string; status: 'running' | 'ok' | 'failed'; bytes: number | null; error: string | null } | null;
  failed: number;
  runs: ExportRun[];
}

const ROLES = ['owner', 'member', 'admin'];
const EXPORT_TONE = { ok: 'success', failed: 'error', running: 'info' } as const;
const EXPORT_LABEL = { ok: 'Exported', failed: 'Failed', running: 'Running' } as const;

function auditText(entry: AuditEntry): string {
  const who = entry.target_email ?? 'a deleted user';
  if (entry.action === 'role') return `changed ${who} from ${entry.detail.before} to ${entry.detail.after}`;
  if (entry.action === 'disable') return `disabled ${who}`;
  if (entry.action === 'enable') return `re-enabled ${who}`;
  if (entry.action === 'export_run') return 'started a data export';
  return `${entry.action} ${who}`;
}

/** The value after typing pauses for 300 ms, so a search sends one request instead of one per key. */
function useDebounced(value: string): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), 300);
    return () => window.clearTimeout(timer);
  }, [value]);
  return useDeferredValue(settled);
}

/** The platform console, mounted by the separate admin app (/admin) for a signed-in administrator. */
export function AdminConsole({ user }: { user: { id: string; email: string } }) {
  const queryClient = useQueryClient();
  const [userSearch, setUserSearch] = useState('');
  const [businessSearch, setBusinessSearch] = useState('');
  const userQuery = useDebounced(userSearch);
  const businessQuery = useDebounced(businessSearch);
  const users = useQuery({
    queryKey: ['admin', 'users', userQuery],
    queryFn: ({ signal }) => request<AdminUser[]>(`/api/admin/users?q=${encodeURIComponent(userQuery)}`, { signal }),
  });
  const businesses = useQuery({
    queryKey: ['admin', 'businesses', businessQuery],
    queryFn: ({ signal }) => request<AdminBusiness[]>(`/api/admin/businesses?q=${encodeURIComponent(businessQuery)}`, { signal }),
  });
  const funnel = useQuery({ queryKey: ['admin', 'onboarding'], queryFn: ({ signal }) => request<Funnel>('/api/admin/onboarding', { signal }) });
  const audit = useQuery({ queryKey: ['admin', 'audit'], queryFn: ({ signal }) => request<AuditEntry[]>('/api/admin/audit', { signal }) });
  const exportStatus = useQuery({
    queryKey: ['admin', 'exports'],
    queryFn: ({ signal }) => request<ExportStatus>('/api/admin/exports', { signal }),
    refetchInterval: (query) => (query.state.data?.running ? 2000 : false),
  });
  const [exporting, setExporting] = useState(false);
  const exportRunning = exporting || Boolean(exportStatus.data?.running);

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

  async function exportNow() {
    setExporting(true);
    try {
      await request('/api/admin/exports/run', { method: 'POST' });
      toast('Export started. Results appear here as each business finishes.');
    } catch (error) {
      toast((error as Error).message, { error: true });
    } finally {
      setExporting(false);
      await queryClient.invalidateQueries({ queryKey: ['admin'] });
    }
  }

  const exportColumns: Column<ExportRun>[] = [
    {
      label: 'Business',
      value: (item) => (
        <div className="file-cell">
          <strong>{item.business_name}</strong>
          <small>{item.error ?? `${formatDate(item.day)} · ${number(item.row_count ?? 0)} rows`}</small>
        </div>
      ),
    },
    { label: 'Status', value: (item) => <Pill tone={EXPORT_TONE[item.status]}>{item.attempts > 1 && item.status === 'failed' ? `Failed ${item.attempts}×` : EXPORT_LABEL[item.status]}</Pill> },
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

      <div className="card" id="admin-exports">
        <div className="card-header">
          <div>
            <h2 className="card-title">Data export</h2>
            <p className="card-subtitle">
              {exportStatus.data?.enabled
                ? exportStatus.data.problem
                  ? `Could not start: ${exportStatus.data.problem}`
                  : `Daily after ${String(exportStatus.data.hour_utc).padStart(2, '0')}:00 UTC to ${exportStatus.data.destination}${exportStatus.data.failed ? ` · ${number(exportStatus.data.failed)} failed` : ''}`
                : 'Off. Set FERLANCE_EXPORT_BUCKET on the server to export each business to S3 daily.'}
            </p>
          </div>
          {exportStatus.data?.enabled ? (
            <button className="btn btn-ghost btn-sm" type="button" disabled={exportRunning} onClick={() => void exportNow()}>
              {exportRunning ? 'Exporting…' : 'Export now'}
            </button>
          ) : null}
        </div>
        {exportStatus.data?.enabled ? (
          <p className="body-sm muted card-body" id="admin-backup">
            {exportStatus.data.backup
              ? exportStatus.data.backup.status === 'ok'
                ? `Last restorable backup: ${formatDate(exportStatus.data.backup.day)} (${number(Math.round((exportStatus.data.backup.bytes ?? 0) / 1024))} KB)`
                : `Backup ${exportStatus.data.backup.status} on ${formatDate(exportStatus.data.backup.day)}${exportStatus.data.backup.error ? `: ${exportStatus.data.backup.error}` : ''}`
              : 'No restorable backup yet. One is made with each daily export.'}
          </p>
        ) : null}
        {exportStatus.data?.runs.length ? (
          <div className="table-wrap">
            <DataTable columns={exportColumns} rows={exportStatus.data.runs} rowKey={(item) => item.business_id} />
          </div>
        ) : exportStatus.data?.enabled ? (
          <p className="body-sm muted card-body">No exports yet.</p>
        ) : null}
      </div>

      <div className="card">
        <div className="card-header">
          <div>
            <h2 className="card-title">Admin log</h2>
            <p className="card-subtitle">Every role change, disable, enable and manual export</p>
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
