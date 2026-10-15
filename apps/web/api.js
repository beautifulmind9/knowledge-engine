// Shared request transport. Create payloads are complete before reaching this layer.
export const CSRF_COOKIE = '__Host-ke-beta-csrf';
const now=()=>{try{return globalThis.performance?.now?.()??Date.now();}catch{return Date.now();}};
function timing(event, durationMs, fields={}) { try { console.info('KE_PERF',{event,duration_ms:Math.round(durationMs*100)/100,...fields}); } catch {} }
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
  const started=now();
  let response;
  try { response=await globalThis.fetch(input, csrfOptions(input, options)); }
  catch(error) { timing('api_fetch',now()-started,{result:'network_error',endpoint:String(input).split('?')[0]});throw error; }
  const endpoint=String(input).split('?')[0];
  if(/^\/libraries(?:$|\/)|^\/sources(?:$|\/)/.test(endpoint))
    timing('data_fetch',now()-started,{result:response.ok?'success':'http_error',status:response.status,endpoint});
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
    const error = new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
    error.status = response.status;
    throw error;
  }
  return response.json();
}
