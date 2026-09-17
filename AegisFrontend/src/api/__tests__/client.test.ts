import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { HttpClient, ApiError } from '../client';

describe('HttpClient', () => {
  let client: HttpClient;

  beforeEach(() => {
    client = new HttpClient();
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should manage auth token correctly in memory and localStorage', () => {
    expect(client.getToken()).toBe('');
    client.setToken('test-secret-token-123');
    expect(client.getToken()).toBe('test-secret-token-123');
    expect(localStorage.getItem('aegis_api_token')).toBe('test-secret-token-123');
  });

  it('should inject X-API-Token and Authorization headers when token is set', async () => {
    client.setToken('valid-token-xyz');

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'healthy' }),
    });
    global.fetch = mockFetch;

    const result = await client.get('/api/v1/health');

    expect(result).toEqual({ status: 'healthy' });
    expect(mockFetch).toHaveBeenCalledTimes(1);

    const [calledUrl, calledOptions] = mockFetch.mock.calls[0];
    expect(calledUrl).toBe('/api/v1/health');
    expect(calledOptions.headers.get('X-API-Token')).toBe('valid-token-xyz');
    expect(calledOptions.headers.get('Authorization')).toBe('Bearer valid-token-xyz');
    expect(calledOptions.headers.get('Content-Type')).toBe('application/json');
  });

  it('should correctly build query parameters in GET request', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ tree: [] }),
    });
    global.fetch = mockFetch;

    await client.get('/api/v1/workspaces/ws-1/files/tree', { max_depth: 3, include_hidden: false });

    const [calledUrl] = mockFetch.mock.calls[0];
    expect(calledUrl).toBe('/api/v1/workspaces/ws-1/files/tree?max_depth=3&include_hidden=false');
  });

  it('should return empty object on 204 No Content', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    });
    global.fetch = mockFetch;

    const result = await client.delete('/api/v1/sessions/sess-1');
    expect(result).toEqual({});
  });

  it('should parse structured error details on 401/403/422 HTTP failures', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: 'Forbidden',
      json: async () => ({
        detail: {
          error_code: 'HOST_NOT_ALLOWED',
          message: 'Host header not in allowed whitelist',
          context: { host: 'malicious.attacker.com' },
        },
      }),
    });
    global.fetch = mockFetch;

    await expect(client.get('/api/v1/workspaces')).rejects.toThrow(ApiError);

    try {
      await client.get('/api/v1/workspaces');
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(403);
      expect(apiErr.errorCode).toBe('HOST_NOT_ALLOWED');
      expect(apiErr.message).toBe('Host header not in allowed whitelist');
      expect(apiErr.context).toEqual({ host: 'malicious.attacker.com' });
    }
  });

  it('should send JSON payload with POST / PUT / PATCH', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ success: true }),
    });
    global.fetch = mockFetch;

    const payload = { name: 'Test Workspace', root_path: '/tmp/test' };
    await client.post('/api/v1/workspaces', payload);

    const [, calledOptions] = mockFetch.mock.calls[0];
    expect(calledOptions.method).toBe('POST');
    expect(calledOptions.body).toBe(JSON.stringify(payload));
  });
});
