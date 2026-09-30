export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly field: string | null;
  readonly details: Record<string, unknown> | null;

  constructor(status: number, code: string, message: string, field: string | null = null, details: Record<string, unknown> | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.field = field;
    this.details = details;
  }
}

export type Query = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

let csrfToken: string | null = null;
let csrfPending: Promise<string | null> | null = null;

export function setCsrfToken(token: string | null) {
  csrfToken = token;
}

async function loadCsrf(): Promise<string | null> {
  csrfPending ??= fetch('/api/auth/state')
    .then((r) => (r.ok ? r.json() : null))
    .then((s: { csrfToken?: string | null } | null) => {
      csrfToken = s?.csrfToken ?? null;
      return csrfToken;
    })
    .catch(() => null)
    .finally(() => {
      csrfPending = null;
    });
  return csrfPending;
}

function parseJson(text: string): unknown {
  try {
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

export function withQuery(path: string, query?: Query): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, String(v));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export interface RequestOptions {
  query?: Query;
  json?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}

export async function request<T>(method: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE', path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(opts.json);
  }
  if (method !== 'GET') {
    const token = csrfToken ?? (await loadCsrf());
    if (token) headers['X-CSRF-Token'] = token;
  }
  let res: Response;
  try {
    res = await fetch(withQuery(path, opts.query), { method, headers, body, signal: opts.signal, credentials: 'same-origin' });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiError(0, 'unavailable', 'The request did not reach the server.');
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const parsed = parseJson(text);
  if (!res.ok) {
    const e = (parsed as { error?: { code?: string; message?: string; field?: string | null; details?: Record<string, unknown> | null } } | null)?.error;
    throw new ApiError(res.status, e?.code ?? 'internal', e?.message ?? res.statusText, e?.field ?? null, e?.details ?? null);
  }
  return parsed as T;
}

export const get = <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>('GET', path, { query, signal });
export const post = <T>(path: string, json?: unknown) => request<T>('POST', path, { json: json ?? {} });
