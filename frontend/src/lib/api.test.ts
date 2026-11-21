import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, navigation, refreshSession, request, resetSessionForTests, signOut } from './api';

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

describe('api client', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let replace: ReturnType<typeof vi.fn<(url: string) => void>>;

  beforeEach(() => {
    resetSessionForTests();
    fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    replace = vi.fn<(url: string) => void>();
    vi.spyOn(navigation, 'replace').mockImplementation(replace);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('shares one refresh request across concurrent callers (refresh tokens are single-use)', async () => {
    let resolve!: (response: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise<Response>((done) => (resolve = done)));
    const first = refreshSession();
    const second = refreshSession();
    resolve(json(200, { access_token: 'token-1', token_type: 'bearer', business: null }));
    await expect(Promise.all([first, second])).resolves.toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/refresh', expect.objectContaining({ method: 'POST', credentials: 'same-origin' }));
  });

  it('sends the in-memory bearer token and JSON bodies', async () => {
    fetchMock.mockResolvedValueOnce(json(200, { access_token: 'abc', token_type: 'bearer', business: null }));
    await refreshSession();
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }));
    await request('/api/thing', { method: 'POST', json: { a: 1 } });
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(init.headers).toEqual({ Authorization: 'Bearer abc', 'Content-Type': 'application/json' });
    expect(init.body).toBe('{"a":1}');
  });

  it('refreshes once on 401 and retries the original request', async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { detail: 'expired' }))
      .mockResolvedValueOnce(json(200, { access_token: 'fresh', token_type: 'bearer', business: null }))
      .mockResolvedValueOnce(json(200, { value: 42 }));
    await expect(request<{ value: number }>('/api/data')).resolves.toEqual({ value: 42 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const retryInit = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(retryInit.headers).toMatchObject({ Authorization: 'Bearer fresh' });
    expect(replace).not.toHaveBeenCalled();
  });

  it('redirects to sign-in when the refresh fails', async () => {
    fetchMock.mockResolvedValueOnce(json(401, {})).mockResolvedValueOnce(json(401, {}));
    await expect(request('/api/data')).rejects.toBeInstanceOf(ApiError);
    expect(replace).toHaveBeenCalledWith('/?signin');
  });

  it('does not try to refresh for auth endpoints', async () => {
    fetchMock.mockResolvedValueOnce(json(401, { detail: 'Invalid email or password.' }));
    await expect(request('/api/auth/login', { method: 'POST', json: {} })).rejects.toMatchObject({ status: 401, message: 'Invalid email or password.' });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('turns FastAPI validation errors and server errors into readable messages', async () => {
    fetchMock.mockResolvedValueOnce(json(422, { detail: [{ msg: 'Field required' }, { msg: 'Too short' }] }));
    await expect(request('/api/x')).rejects.toMatchObject({ status: 422, message: 'Field required Too short' });
    fetchMock.mockResolvedValueOnce(new Response('oops', { status: 500 }));
    await expect(request('/api/x')).rejects.toMatchObject({ status: 500, message: 'The server could not complete that request.' });
  });

  it('signs out and returns to the landing page even if logout fails', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'));
    await signOut();
    expect(replace).toHaveBeenCalledWith('/');
  });
});
