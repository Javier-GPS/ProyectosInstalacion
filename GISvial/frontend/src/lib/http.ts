/** Shared HTTP boundary — same pattern as luxStudio frontend. */
export type Requester = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const parseBody = async (response: Response): Promise<unknown> => {
  const text = await response.text();
  if (!text.trim()) return null;
  try { return JSON.parse(text); } catch { return text; }
};

export const errorMessage = (data: unknown, fallback: string): string => {
  if (!data || typeof data !== 'object') return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map(i => (i && typeof i === 'object' && 'msg' in i ? String(i.msg) : JSON.stringify(i))).filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  return fallback;
};

export const requestJson = async <T>(
  request: Requester,
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  fallback: string,
): Promise<T> => {
  const response = await request(input, init);
  const body = await parseBody(response);
  if (!response.ok) throw new Error(errorMessage(body, fallback));
  return body as T;
};
