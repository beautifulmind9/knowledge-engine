// Shared request transport. Workshop fetch decorators still enrich payloads.
export const CSRF_COOKIE = '__Host-ke-beta-csrf';
const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export function csrfToken(cookie = globalThis.document?.cookie || '') {
  const entry = cookie.split(';').map(part => part.trim()).find(part => part.startsWith(CSRF_COOKIE + '='));
  if (!entry) return '';
  try { return decodeURIComponent(entry.slice(CSRF_COOKIE.length + 1)); }
  catch { return ''; }
}

export function csrfOptions(input, options = {}, {cookie = globalThis.document?.cookie || '', origin = globalThis.location?.origin} = {}) {
  const init = {...options};
  const method = String(init.method || input?.method || 'GET').toUpperCase();
  const target = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, origin || 'http://localhost');
  if (!origin || target.origin !== origin) return init;
  if (UNSAFE_METHODS.has(method)) {
    const headers = new Headers(init.headers || input?.headers);
    const token = csrfToken(cookie);
    headers.delete('X-CSRF-Token');
    if (token) headers.set('X-CSRF-Token', token);
    init.headers = headers;
  }
  return init;
}

export async function apiFetch(input, options = {}) {
  const response = await globalThis.fetch(input, csrfOptions(input, options));
  if (response.status === 401 && globalThis.location && input !== '/login') {
    globalThis.location.assign('/login');
  }
  return response;
}

export async function api(path, options = {}) {
  const init = {...options};
  if (init.body && !(init.body instanceof FormData)) {
    const headers = new Headers(init.headers);
    if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    init.headers = headers;
    init.body = JSON.stringify(init.body);
  }
  const response = await apiFetch(path, init);
  if (!response.ok) {
    let data;
    try { data = await response.json(); }
    catch { data = {detail: `Request failed (${response.status})`}; }
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return response.json();
}
