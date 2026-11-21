// API client. Access tokens live only in memory; the refresh cookie is HttpOnly.
// Concurrent 401s share one refresh request, because refresh tokens are single-use.

import type { AuthResponse } from './types';

let accessToken: string | null = null;
let refreshing: Promise<AuthResponse> | null = null;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** Where to send the browser when the session cannot be recovered. Replaceable in tests. */
export const navigation = {
  replace: (url: string) => window.location.replace(url),
};

export function refreshSession(): Promise<AuthResponse> {
  refreshing ??= fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' })
    .then(async (response) => {
      if (!response.ok) throw new ApiError('Your session has ended. Please sign in again.', 401);
      const body = (await response.json()) as AuthResponse;
      accessToken = body.access_token;
      return body;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

interface ErrorBody {
  detail?: string | { msg: string }[];
}

function detail(body: ErrorBody | null, status: number): string {
  if (Array.isArray(body?.detail)) return body.detail.map((item) => item.msg).join(' ');
  return body?.detail || (status >= 500 ? 'The server could not complete that request.' : 'Request failed.');
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** JSON body; serialised and sent with a JSON content type. */
  json?: unknown;
  /** Raw body, e.g. FormData for uploads. */
  body?: BodyInit;
  signal?: AbortSignal;
}

export async function request<T>(path: string, { method = 'GET', json, body, signal }: RequestOptions = {}): Promise<T> {
  const send = () => {
    const headers: Record<string, string> = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    if (json !== undefined) headers['Content-Type'] = 'application/json';
    return fetch(path, {
      method,
      credentials: 'same-origin',
      headers,
      signal,
      body: json !== undefined ? JSON.stringify(json) : body,
    });
  };
  let response = await send();
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    try {
      await refreshSession();
    } catch (error) {
      navigation.replace('/?signin');
      throw error;
    }
    response = await send();
  }
  const payload = (await response.json().catch(() => ({}))) as unknown;
  if (!response.ok) throw new ApiError(detail(payload as ErrorBody, response.status), response.status);
  return payload as T;
}

export async function signOut(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => undefined);
  accessToken = null;
  navigation.replace('/');
}

/** Test hook: forget any token and in-flight refresh. */
export function resetSessionForTests(): void {
  accessToken = null;
  refreshing = null;
}
