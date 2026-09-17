/**
 * Aegis Core HTTP Client
 * Provides unified request handling, token injection, and structured error parsing.
 */

export interface ApiErrorDetail {
  error_code?: string;
  message?: string;
  context?: Record<string, unknown>;
  [key: string]: unknown;
}

export class ApiError extends Error {
  public status: number;
  public errorCode?: string;
  public detail?: ApiErrorDetail | string;
  public context?: Record<string, unknown>;

  constructor(status: number, message: string, detail?: ApiErrorDetail | string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;

    if (typeof detail === 'object' && detail !== null) {
      this.errorCode = detail.error_code;
      this.context = detail.context;
      if (detail.message) {
        this.message = detail.message;
      }
    }
  }
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
  timeoutMs?: number;
}

export class HttpClient {
  private baseURL: string = '';
  private token: string = '';

  constructor(baseURL: string = '') {
    this.baseURL = baseURL;
    if (typeof window !== 'undefined' && window.localStorage) {
      this.token = localStorage.getItem('aegis_api_token') || '';
    }
  }

  public setToken(token: string) {
    this.token = token;
    if (typeof window !== 'undefined' && window.localStorage) {
      localStorage.setItem('aegis_api_token', token);
    }
  }

  public getToken(): string {
    return this.token;
  }

  public setBaseURL(url: string) {
    this.baseURL = url.replace(/\/+$/, '');
  }

  public getBaseURL(): string {
    return this.baseURL;
  }

  private buildUrl(endpoint: string, params?: Record<string, string | number | boolean | undefined | null>): string {
    const fullPath = endpoint.startsWith('http') ? endpoint : `${this.baseURL}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
    if (!params) return fullPath;

    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    });

    const queryString = searchParams.toString();
    return queryString ? `${fullPath}${fullPath.includes('?') ? '&' : '?'}${queryString}` : fullPath;
  }

  private getHeaders(extraHeaders: HeadersInit = {}): Headers {
    const headers = new Headers(extraHeaders);
    if (!headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    if (this.token) {
      headers.set('X-API-Token', this.token);
      headers.set('Authorization', `Bearer ${this.token}`);
    }
    return headers;
  }

  public async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
    const { params, timeoutMs = 30000, ...fetchOptions } = options;
    const url = this.buildUrl(endpoint, params);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...fetchOptions,
        headers: this.getHeaders(fetchOptions.headers),
        signal: fetchOptions.signal || controller.signal,
      });

      if (!response.ok) {
        let errorDetail: ApiErrorDetail | string = response.statusText;
        let errorMessage = `API Request Failed [${response.status}] ${response.statusText}`;

        try {
          const errorJson = await response.json();
          if (errorJson.detail) {
            errorDetail = errorJson.detail;
            if (typeof errorJson.detail === 'object' && errorJson.detail.message) {
              errorMessage = errorJson.detail.message;
            } else if (typeof errorJson.detail === 'string') {
              errorMessage = errorJson.detail;
            }
          } else if (errorJson.message) {
            errorMessage = errorJson.message;
            errorDetail = errorJson;
          }
        } catch {
          // Non-JSON response body
        }

        throw new ApiError(response.status, errorMessage, errorDetail);
      }

      if (response.status === 204) {
        return {} as T;
      }

      return await response.json();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        throw err;
      }
      if (err instanceof Error && err.name === 'AbortError') {
        throw new ApiError(408, `Request Timeout (${timeoutMs}ms): ${url}`);
      }
      throw new ApiError(0, err instanceof Error ? err.message : 'Network / Unknown Error');
    } finally {
      clearTimeout(timeoutId);
    }
  }

  public get<T>(endpoint: string, params?: Record<string, string | number | boolean | undefined | null>, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET', params });
  }

  public post<T>(endpoint: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  }

  public put<T>(endpoint: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  }

  public patch<T>(endpoint: string, data?: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: data !== undefined ? JSON.stringify(data) : undefined,
    });
  }

  public delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

export const httpClient = new HttpClient();
