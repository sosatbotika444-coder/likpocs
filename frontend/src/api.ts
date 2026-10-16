import axios, { type AxiosError } from 'axios';

const api = axios.create({ baseURL: import.meta.env.VITE_API_BASE || '/api', timeout: 20000 });
const ACCESS_KEY = 'dormflow.access';
const REFRESH_KEY = 'dormflow.refresh';

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(ACCESS_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshPromise: Promise<string | null> | null = null;
api.interceptors.response.use((response) => response, async (error: AxiosError) => {
  const original = error.config as (typeof error.config & { _retry?: boolean }) | undefined;
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  if (error.response?.status !== 401 || !original || original._retry || !refreshToken || String(original.url).includes('/auth/')) throw error;
  original._retry = true;
  refreshPromise ??= axios.post(`${api.defaults.baseURL}/auth/refresh`, { refresh_token: refreshToken }).then((result) => {
    localStorage.setItem(ACCESS_KEY, result.data.access_token);
    localStorage.setItem(REFRESH_KEY, result.data.refresh_token);
    return result.data.access_token as string;
  }).catch(() => {
    clearSession();
    return null;
  }).finally(() => { refreshPromise = null; });
  const token = await refreshPromise;
  if (!token) throw error;
  original.headers.Authorization = `Bearer ${token}`;
  return api(original);
});

export function saveSession(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}
export function clearSession() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}
export function hasSession() { return Boolean(localStorage.getItem(ACCESS_KEY)); }
export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (status === 401) return 'Sessiya tugadi. Qayta kiring.';
    if (status === 403) return 'Bu amal uchun ruxsatingiz yo‘q.';
    if (status === 404) return 'So‘ralgan ma’lumot topilmadi.';
    if (status === 409) return typeof detail === 'string' ? detail : 'Ma’lumotlar o‘rtasida ziddiyat bor.';
    if (status === 422) return typeof detail === 'string' ? detail : 'Kiritilgan ma’lumotlarni tekshiring.';
    if (!error.response) return 'Server bilan bog‘lanib bo‘lmadi. Ulanishni tekshiring.';
  }
  return error instanceof Error ? error.message : 'Kutilmagan xatolik yuz berdi.';
}

export { api };
