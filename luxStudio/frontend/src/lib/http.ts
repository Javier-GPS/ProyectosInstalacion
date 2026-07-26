/** Shared HTTP boundary for frontend API wrappers. */

export type Requester = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const parseBody = async (response: Response): Promise<unknown> => {
  const text = await response.text();
  if (!text.trim()) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
};

export const errorMessage = (data: unknown, fallback: string): string => {
  if (!data || typeof data !== 'object') return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => (item && typeof item === 'object' && 'msg' in item ? String(item.msg) : JSON.stringify(item)))
      .filter(Boolean);
    if (messages.length) return messages.join('; ');
  }
  return fallback;
};

export const extractError = async (response: Response, fallback: string) => {
  // clone() keeps the helper non-destructive for callers that still need the body.
  const readable = response.clone ? response.clone() : response;
  return errorMessage(await parseBody(readable), fallback);
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

export const requestBlob = async (
  request: Requester,
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  fallback: string,
): Promise<Blob> => {
  const response = await request(input, init);
  if (!response.ok) throw new Error(errorMessage(await parseBody(response), fallback));
  return response.blob();
};
