// API client. Access tokens live only in memory; the refresh cookie is HttpOnly.
// Concurrent 401s share one refresh request, because refresh tokens are single-use.

let accessToken = null;
let refreshing = null;

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export function refreshSession() {
  refreshing ??= fetch('/api/auth/refresh', { method: 'POST', credentials: 'same-origin' })
    .then(async (response) => {
      if (!response.ok) throw new ApiError('Your session has ended. Please sign in again.', 401);
      const body = await response.json();
      accessToken = body.access_token;
      return body;
    })
    .finally(() => { refreshing = null; });
  return refreshing;
}

function detail(body, status) {
  if (Array.isArray(body?.detail)) return body.detail.map((item) => item.msg).join(' ');
  return body?.detail || (status >= 500 ? 'The server could not complete that request.' : 'Request failed.');
}

export async function request(path, { method = 'GET', json, body, signal } = {}) {
  const send = () => {
    const headers = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    if (json !== undefined) headers['Content-Type'] = 'application/json';
    return fetch(path, { method, credentials: 'same-origin', headers, signal, body: json !== undefined ? JSON.stringify(json) : body });
  };
  let response = await send();
  if (response.status === 401 && !path.startsWith('/api/auth/')) {
    try {
      await refreshSession();
    } catch (error) {
      window.location.replace('/?signin');
      throw error;
    }
    response = await send();
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(detail(payload, response.status), response.status);
  return payload;
}

export async function signOut() {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  accessToken = null;
  window.location.replace('/');
}
