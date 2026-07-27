/** sessionStorage helper with JSON parse/stringify + error handling. */

const STORAGE_PREFIX = 'gis:';

export const getJson = <T>(key: string): T | null => {
  try {
    const raw = sessionStorage.getItem(STORAGE_PREFIX + key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
};

export const setJson = (key: string, val: unknown): boolean => {
  try {
    sessionStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(val));
    return true;
  } catch (e) {
    if (e instanceof DOMException && e.name === 'QuotaExceededError') {
      console.warn('sessionStorage quota exceeded for key:', key);
    }
    return false;
  }
};

export const remove = (key: string): void => {
  try { sessionStorage.removeItem(STORAGE_PREFIX + key); } catch {}
};

export const clear = (): void => {
  try { sessionStorage.clear(); } catch {}
};
