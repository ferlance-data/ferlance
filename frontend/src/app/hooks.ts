// Data hooks every view uses for server reads.

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { request } from '../lib/api';
import { keys, useScope, useWorkspace } from './workspace';

/**
 * Read a scoped business endpoint (`/analytics`, `/insights`, …) with the current
 * dataset/date scope. The query refetches whenever the scope changes, and stale
 * responses from an earlier scope are discarded by the query cache.
 * Date presets anchor to the latest record using each file's stored period,
 * so the first request already carries the right window.
 *
 * Load failures are toasted globally; pass `silent` for optional reads whose
 * failure the view already handles quietly.
 */
export function useScopedQuery<T>(
  suffix: string,
  { includeDataset = true, enabled = true, silent = false }: { includeDataset?: boolean; enabled?: boolean; silent?: boolean } = {},
) {
  const { business, businessPath } = useWorkspace();
  const { params } = useScope();
  const qs = params({ includeDataset }).toString();
  return useQuery({
    queryKey: keys.scoped(business.id, suffix, qs),
    queryFn: ({ signal }) => request<T>(businessPath(`${suffix}${qs ? `?${qs}` : ''}`), { signal }),
    placeholderData: keepPreviousData,
    enabled,
    meta: { silent },
  });
}

/** Read an unscoped business endpoint, e.g. `useBusinessQuery<Movement[]>('/inventory/movements?limit=100')`. */
export function useBusinessQuery<T>(suffix: string, { enabled = true, silent = false }: { enabled?: boolean; silent?: boolean } = {}) {
  const { business, businessPath } = useWorkspace();
  return useQuery({
    queryKey: keys.business(business.id, suffix),
    queryFn: ({ signal }) => request<T>(businessPath(suffix), { signal }),
    enabled,
    meta: { silent },
  });
}

