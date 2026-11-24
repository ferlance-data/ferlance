// Talking to the Ferlance server from the phone.
//
// The access token lives in memory only. The refresh token is kept in the device's secure store
// (Keychain / Keystore) and swapped for a new one on every refresh (/api/auth/mobile/*). Refreshes
// are single-flight: tokens are single-use, so two parallel 401s must share one refresh.

import { storage } from './storage';
import type { Business } from '../../frontend/src/lib/types';

export const DEFAULT_SERVER = process.env.EXPO_PUBLIC_API_URL || 'https://13-48-56-28.sslip.io';
const REFRESH_KEY = 'ferlance.refresh';
const SERVER_KEY = 'ferlance.server';

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

interface Tokens {
  access_token: string;
  refresh_token: string;
  business: Business | null;
}

let server = DEFAULT_SERVER;
let accessToken: string | null = null;
let refreshing: Promise<Tokens | null> | null = null;
let onSignedOut: () => void = () => undefined;

export const serverUrl = (): string => server;
export const absolute = (path: string): string => `${server}${path}`;

/** Called when the session can't be renewed (signed out elsewhere, disabled, expired). */
export function setSignedOutHandler(handler: () => void): void {
  onSignedOut = handler;
}

function clean(url: string): string {
  const trimmed = url.trim().replace(/\/+$/, '');
  return /^https?:\/\//.test(trimmed) ? trimmed : `https://${trimmed}`;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) return 'Some details are missing or not valid. Check the form and try again.';
  } catch {
    // not JSON
  }
  return response.status >= 500 ? 'The server had a problem. Try again in a moment.' : `Request failed (${response.status}).`;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(absolute(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  } catch {
    throw new ApiError('Could not reach Ferlance. Check your internet connection.', 0);
  }
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  return (await response.json()) as T;
}

async function keep(tokens: Tokens): Promise<Tokens> {
  accessToken = tokens.access_token;
  await storage.setItemAsync(REFRESH_KEY, tokens.refresh_token);
  return tokens;
}

async function forget(): Promise<void> {
  accessToken = null;
  await storage.deleteItemAsync(REFRESH_KEY);
}

/** Load the saved server address. Returns the saved session's business, or null if signed out. */
export async function restore(): Promise<Business | null | undefined> {
  server = (await storage.getItemAsync(SERVER_KEY)) || DEFAULT_SERVER;
  const tokens = await renew();
  return tokens ? tokens.business : undefined;
}

export async function signIn(address: string, email: string, password: string): Promise<Business | null> {
  server = clean(address || DEFAULT_SERVER);
  const tokens = await keep(await post<Tokens>('/api/auth/mobile/login', { email, password }));
  await storage.setItemAsync(SERVER_KEY, server);
  return tokens.business;
}

export async function signOut(): Promise<void> {
  const token = await storage.getItemAsync(REFRESH_KEY);
  await forget();
  if (token) await post('/api/auth/mobile/logout', { refresh_token: token }).catch(() => undefined);
}

/** Swap the saved refresh token for new tokens. Concurrent callers share one request. */
function renew(): Promise<Tokens | null> {
  refreshing ??= (async () => {
    const token = await storage.getItemAsync(REFRESH_KEY);
    if (!token) return null;
    try {
      return await keep(await post<Tokens>('/api/auth/mobile/refresh', { refresh_token: token }));
    } catch (error) {
      // Only a refused token ends the session; a network blip keeps it for the next try.
      if (error instanceof ApiError && error.status === 401) await forget();
      if (error instanceof ApiError && error.status === 0) throw error;
      return null;
    }
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

/** An authenticated request. `body` is JSON unless it is FormData. Retries once after a refresh. */
export async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const send = async () => {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    let body: BodyInit | undefined;
    if (init.body instanceof FormData) body = init.body;
    else if (init.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(init.body);
    }
    try {
      return await fetch(absolute(path), { method: init.method ?? (body ? 'POST' : 'GET'), headers, body });
    } catch {
      throw new ApiError('Could not reach Ferlance. Check your internet connection.', 0);
    }
  };
  let response = await send();
  if (response.status === 401) {
    const tokens = await renew();
    if (!tokens) {
      onSignedOut();
      throw new ApiError('Your session has ended. Sign in again.', 401);
    }
    response = await send();
  }
  if (!response.ok) throw new ApiError(await readError(response), response.status);
  return (await response.json()) as T;
}
