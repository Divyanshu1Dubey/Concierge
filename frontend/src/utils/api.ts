import axios, { AxiosError, AxiosRequestConfig } from 'axios';

const envApiUrl = import.meta.env.VITE_API_URL;
const isLocalhostInRemoteBrowser =
  typeof window !== 'undefined' &&
  window.location.hostname !== 'localhost' &&
  window.location.hostname !== '127.0.0.1' &&
  Boolean(envApiUrl && envApiUrl.includes('localhost'));

export const API_BASE = (isLocalhostInRemoteBrowser || !envApiUrl) ? '/api' : envApiUrl;

export const TOKEN_KEY = 'auth_token';
export const REFRESH_KEY = 'auth_refresh';

// Endpoints that must never carry a (possibly stale) bearer token or trigger refresh.
const PUBLIC_AUTH_PATHS = ['/auth/login/', '/auth/token/', '/auth/token/refresh/', '/auth/config/', '/auth/password-reset/', '/auth/password-reset/confirm/'];
const isPublicAuthPath = (url?: string) => !!url && PUBLIC_AUTH_PATHS.some((p) => url.endsWith(p));

export const apiClient = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token && !isPublicAuthPath(config.url)) config.headers.Authorization = `Bearer ${token}`;
  const activePracticeId = localStorage.getItem('active_practice_id');
  if (activePracticeId) {
    config.headers['X-Practice-ID'] = activePracticeId;
  }
  return config;
});

let refreshPromise: Promise<string | null> | null = null;
let onSessionExpired: ((reason?: 'expired' | 'suspended') => void) | null = null;

/** Registered by the auth store so an unrecoverable 401 logs the user out everywhere. */
export function setSessionExpiredHandler(handler: (reason?: 'expired' | 'suspended') => void) {
  onSessionExpired = handler;
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!refresh) return null;
  try {
    const { data } = await axios.post(`${API_BASE}/auth/token/refresh/`, { refresh });
    localStorage.setItem(TOKEN_KEY, data.access);
    // Refresh tokens rotate server-side; keep the new one.
    if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
    return data.access as string;
  } catch {
    return null;
  }
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined;
    if (error.response?.status === 401 && (error.response?.data as any)?.code === 'practice_suspended') {
      onSessionExpired?.('suspended');
      return Promise.reject(error);
    }
    if (error.response?.status !== 401 || !original || original._retried || isPublicAuthPath(original.url)) {
      return Promise.reject(error);
    }
    original._retried = true;
    // Share one refresh between concurrent 401s.
    refreshPromise = refreshPromise ?? refreshAccessToken().finally(() => { refreshPromise = null; });
    const newToken = await refreshPromise;
    if (!newToken) {
      onSessionExpired?.();
      return Promise.reject(error);
    }
    original.headers = { ...(original.headers || {}), Authorization: `Bearer ${newToken}` };
    return apiClient(original);
  }
);

/** Extract a human-readable message from a DRF error response. */
export function apiErrorMessage(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const data = (err as AxiosError<any>)?.response?.data;
  if (!data) {
    return (err as AxiosError)?.response ? fallback : 'Network error: could not reach the server.';
  }
  if (typeof data === 'string') return fallback;
  if (data.error) return String(data.error);
  if (data.detail) return String(data.detail);
  if (data.message) return String(data.message);
  if (Array.isArray(data.non_field_errors)) return data.non_field_errors.join(' ');
  const firstKey = Object.keys(data)[0];
  if (firstKey) {
    const val = data[firstKey];
    return `${firstKey.replace(/_/g, ' ')}: ${Array.isArray(val) ? val.join(' ') : String(val)}`;
  }
  return fallback;
}

/** Download an authenticated file (CSV / ZIP) through the API client. */
export async function downloadFile(url: string, fallbackName: string) {
  const res = await apiClient.get(url, { responseType: 'blob' });
  const disposition = res.headers['content-disposition'] as string | undefined;
  const match = disposition?.match(/filename="?([^"]+)"?/);
  const href = URL.createObjectURL(res.data as Blob);
  const a = document.createElement('a');
  a.href = href;
  a.download = match?.[1] || fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(href);
}

/** Normalise list responses that may be paginated ({results}) or plain arrays. */
export function asList<T = any>(data: any): T[] {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.results)) return data.results;
  return [];
}

export const api = {
  get: <T = any>(url: string, config?: any) => apiClient.get<T>(url, config),
  post: <T = any>(url: string, data?: any, config?: any) => apiClient.post<T>(url, data, config),
  patch: <T = any>(url: string, data?: any, config?: any) => apiClient.patch<T>(url, data, config),
  put: <T = any>(url: string, data?: any, config?: any) => apiClient.put<T>(url, data, config),
  delete: <T = any>(url: string, config?: any) => apiClient.delete<T>(url, config),
};

export default api;
