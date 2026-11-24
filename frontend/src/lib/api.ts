// API client. Access tokens live only in memory; the refresh cookie is HttpOnly.
// Concurrent 401s share one refresh request, because refresh tokens are single-use.

import type { AuthResponse } from './types';

let accessToken: string | null = null;
let refreshing: Promise<AuthResponse> | null = null;

/**
 * Which suite this page belongs to. The workspace uses /api/auth; the admin console has its own
 * sign-in at /api/admin/auth with a separate refresh cookie, so the two sessions never mix.
 */
const session = { base: '/api/auth', signedOut: '/?signin' };

export function configureSession(options: { base: string; signedOut: string }): void {
  session.base = options.base;
  session.signedOut = options.signedOut;
}

/** Keep the access token from a sign-in response (the refresh cookie is set by the server). */
export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export class ApiError extends Error {
  readonly status: number;
  /** Structured error body from the server, when it sent one (for example a list of conflicts). */
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/** Where to send the browser when the session cannot be recovered. Replaceable in tests. */
export const navigation = {
  replace: (url: string) => window.location.replace(url),
};

export function refreshSession(): Promise<AuthResponse> {
  refreshing ??= fetch(`${session.base}/refresh`, { method: 'POST', credentials: 'same-origin' })
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
  detail?: string | { msg: string }[] | { message?: string };
}

function detail(body: ErrorBody | null, status: number): string {
  const value = body?.detail;
  if (Array.isArray(value)) return value.map((item) => item.msg).join(' ');
  if (value && typeof value === 'object' && typeof value.message === 'string') return value.message;
  if (typeof value === 'string' && value) return value;
  return status >= 500 ? 'The server could not complete that request.' : 'Request failed.';
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** JSON body; serialised and sent with a JSON content type. */
  json?: unknown;
  /** Raw body, e.g. FormData for uploads. */
  body?: BodyInit;
  signal?: AbortSignal;
  /** Return the response body as text (e.g. a CSV download) instead of parsing JSON. */
  asText?: boolean;
}

export async function request<T>(path: string, { method = 'GET', json, body, signal, asText = false }: RequestOptions = {}): Promise<T> {
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
  if (response.status === 401 && !path.startsWith(`${session.base}/`)) {
    try {
      await refreshSession();
    } catch (error) {
      navigation.replace(session.signedOut);
      throw error;
    }
    response = await send();
  }
  if (asText && response.ok) return (await response.text()) as T;
  const payload = (await response.json().catch(() => ({}))) as unknown;
  if (!response.ok) throw new ApiError(detail(payload as ErrorBody, response.status), response.status, (payload as ErrorBody)?.detail);
  return payload as T;
}

export async function signOut(): Promise<void> {
  await fetch(`${session.base}/logout`, { method: 'POST', credentials: 'same-origin' }).catch(() => undefined);
  accessToken = null;
  navigation.replace(session.base === '/api/auth' ? '/' : session.signedOut);
}

/** Test hook: forget any token and in-flight refresh. */
export function resetSessionForTests(): void {
  accessToken = null;
  refreshing = null;
}
