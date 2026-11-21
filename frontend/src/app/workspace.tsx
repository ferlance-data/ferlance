// Workspace state shared by every view: identity, datasets, inventory summary,
// setup-guide flags, and the scope (which files and which dates).

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { request } from '../lib/api';
import { setCurrency } from '../lib/format';
import {
  DEFAULT_SCOPE,
  analysableDatasets,
  resolveRange,
  scopeHasData,
  scopeLabel,
  scopeParams,
  type Scope,
} from '../lib/scope';
import type { Business, Dataset, InventoryResponse, Period, User } from '../lib/types';

/* ---------- Query keys ---------- */
// Every server read is cached under one of these keys. Writes invalidate them.
export const keys = {
  datasets: (businessId: string) => ['datasets', businessId] as const,
  inventory: (businessId: string) => ['inventory', businessId] as const,
  /** Scoped reads include the resolved query string, so a scope change refetches automatically. */
  scoped: (businessId: string, name: string, params: string) => ['scoped', businessId, name, params] as const,
  business: (businessId: string, ...rest: (string | number | boolean | null)[]) => ['business', businessId, ...rest] as const,
};

/* ---------- Workspace ---------- */
export interface SetupFlags {
  balances: boolean;
  conversations: boolean;
}

interface WorkspaceValue {
  user: User;
  business: Business;
  /** Merge profile changes (Settings) into the identity shown everywhere. */
  updateIdentity: (patch: { user?: Partial<User>; business?: Partial<Business> }) => void;
  /** `/api/businesses/{id}{suffix}` */
  businessPath: (suffix?: string) => string;
  datasets: Dataset[];
  refreshDatasets: () => Promise<void>;
  inventory: InventoryResponse | null;
  refreshInventory: () => Promise<void>;
  setup: SetupFlags;
  markSetup: (patch: Partial<SetupFlags>) => void;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

export function useWorkspace(): WorkspaceValue {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error('useWorkspace must be used inside <WorkspaceProvider>');
  return value;
}

export function WorkspaceProvider({
  initialUser,
  initialBusiness,
  initialSetup,
  children,
}: {
  initialUser: User;
  initialBusiness: Business;
  initialSetup: SetupFlags;
  children: ReactNode;
}) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState(initialUser);
  const [business, setBusiness] = useState(initialBusiness);
  const [setup, setSetup] = useState(initialSetup);
  setCurrency(business.currency);

  const businessPath = useCallback((suffix = '') => `/api/businesses/${business.id}${suffix}`, [business.id]);

  const datasetsQuery = useQuery({
    queryKey: keys.datasets(business.id),
    queryFn: ({ signal }) => request<Dataset[]>(businessPath('/datasets'), { signal }),
  });
  const inventoryQuery = useQuery({
    queryKey: keys.inventory(business.id),
    queryFn: ({ signal }) => request<InventoryResponse>(businessPath('/inventory?include_archived=true'), { signal }),
  });

  const value = useMemo<WorkspaceValue>(
    () => ({
      user,
      business,
      updateIdentity: ({ user: userPatch, business: businessPatch }) => {
        if (userPatch) setUser((current) => ({ ...current, ...userPatch }));
        if (businessPatch) setBusiness((current) => ({ ...current, ...businessPatch }));
      },
      businessPath,
      datasets: datasetsQuery.data ?? [],
      refreshDatasets: async () => {
        // Imports change every scoped number, so refetch those too.
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: keys.datasets(business.id) }),
          queryClient.invalidateQueries({ queryKey: ['scoped', business.id] }),
        ]);
      },
      inventory: inventoryQuery.data ?? null,
      refreshInventory: () => queryClient.invalidateQueries({ queryKey: keys.inventory(business.id) }),
      setup,
      markSetup: (patch) => setSetup((current) => ({ ...current, ...patch })),
    }),
    [user, business, businessPath, datasetsQuery.data, inventoryQuery.data, setup, queryClient],
  );

  return (
    <WorkspaceContext.Provider value={value}>
      <ScopeProvider datasets={value.datasets}>{children}</ScopeProvider>
    </WorkspaceContext.Provider>
  );
}

/* ---------- Scope ---------- */
interface ScopeValue {
  scope: Scope;
  setScope: (patch: Partial<Scope>) => void;
  /** Earliest/latest record dates in scope; presets anchor to `bounds.to`. */
  bounds: Period;
  /** Call with `analytics.available_period` after each scoped load. */
  setBounds: (bounds: Period | null | undefined) => void;
  /** Resolved dates for the current preset. */
  range: Period;
  /** Query string for scoped endpoints (dataset_id, from, to). */
  params: (options?: { includeDataset?: boolean }) => URLSearchParams;
  label: string;
  hasData: boolean;
}

const ScopeContext = createContext<ScopeValue | null>(null);

export function useScope(): ScopeValue {
  const value = useContext(ScopeContext);
  if (!value) throw new Error('useScope must be used inside <WorkspaceProvider>');
  return value;
}

function ScopeProvider({ datasets, children }: { datasets: Dataset[]; children: ReactNode }) {
  const [rawScope, setRawScope] = useState<Scope>(DEFAULT_SCOPE);
  const [bounds, setBoundsState] = useState<Period>({ from: null, to: null });

  // A file that disappears (deleted or failed) drops the scope back to all data.
  const scope = useMemo<Scope>(
    () =>
      rawScope.datasetId !== 'all' && datasets.length && !analysableDatasets(datasets).some((item) => item.id === rawScope.datasetId)
        ? { ...rawScope, datasetId: 'all' }
        : rawScope,
    [rawScope, datasets],
  );

  const setScope = useCallback((patch: Partial<Scope>) => setRawScope((current) => ({ ...current, ...patch })), []);
  const setBounds = useCallback((next: Period | null | undefined) => {
    if (!next) return;
    setBoundsState((current) => (current.from === next.from && current.to === next.to ? current : { from: next.from, to: next.to }));
  }, []);

  const value = useMemo<ScopeValue>(
    () => ({
      scope,
      setScope,
      bounds,
      setBounds,
      range: resolveRange(scope, bounds),
      params: (options) => scopeParams(scope, bounds, options),
      label: scopeLabel(scope, datasets),
      hasData: scopeHasData(scope, datasets),
    }),
    [scope, setScope, bounds, setBounds, datasets],
  );
  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}
