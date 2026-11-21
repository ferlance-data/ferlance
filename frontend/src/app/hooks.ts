// Data hooks every view uses for server reads.

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { request } from '../lib/api';
import type { Period } from '../lib/types';
import { keys, useScope, useWorkspace } from './workspace';

/**
 * Read a scoped business endpoint (`/analytics`, `/insights`, …) with the current
 * dataset/date scope. The query refetches whenever the scope changes, and stale
 * responses from an earlier scope are discarded by the query cache.
 *
 * With `updatesBounds`, the response's `available_period` becomes the scope's
 * bounds, so date presets anchor to the latest record (legacy `state.bounds`).
 */
export function useScopedQuery<T extends { available_period?: Period }>(
  suffix: string,
  { includeDataset = true, updatesBounds = false, enabled = true }: { includeDataset?: boolean; updatesBounds?: boolean; enabled?: boolean } = {},
) {
  const { business, businessPath } = useWorkspace();
  const { params, setBounds } = useScope();
  const qs = params({ includeDataset }).toString();
  const query = useQuery({
    queryKey: keys.scoped(business.id, suffix, qs),
    queryFn: ({ signal }) => request<T>(businessPath(`${suffix}${qs ? `?${qs}` : ''}`), { signal }),
    placeholderData: keepPreviousData,
    enabled,
  });
  const period = query.data?.available_period;
  useEffect(() => {
    if (updatesBounds && period) setBounds(period);
  }, [updatesBounds, period, setBounds]);
  return query;
}

/** Read an unscoped business endpoint, e.g. `useBusinessQuery<Movement[]>('/inventory/movements?limit=100')`. */
export function useBusinessQuery<T>(suffix: string, { enabled = true }: { enabled?: boolean } = {}) {
  const { business, businessPath } = useWorkspace();
  return useQuery({
    queryKey: keys.business(business.id, suffix),
    queryFn: ({ signal }) => request<T>(businessPath(suffix), { signal }),
    enabled,
  });
}
