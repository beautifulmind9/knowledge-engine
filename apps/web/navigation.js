// Hash routes keep refresh/back/forward within the existing FastAPI shell.
const paths = {home:'home', library:'library', workshop:'create', knowledge:'library/explore', outputs:'my-work', settings:'settings'};
export function routeHash(route) {
  let path = paths[route.view] || 'home';
  if (route.view === 'developerMaterial') path = 'internal/material/' + encodeURIComponent(route.id);
  if (route.view === 'material') path = 'library/material/' + encodeURIComponent(route.id);
  if (route.view === 'work') path = 'my-work/' + encodeURIComponent(route.id);
  const query = new URLSearchParams();
  if (route.library) query.set('library', route.library);
  if (route.picker && route.view === 'knowledge') query.set('picker', '1');
  if (route.add && route.view === 'library') query.set('add', '1');
  if (['workshop', 'knowledge'].includes(route.view)) {
    for (const id of route.materials || []) query.append('material', id);
    if (route.view === 'knowledge' && route.source) query.set('source', route.source);
    if (route.view === 'knowledge' && route.exploreState?.scopeMode) {
      query.set('scope_mode', route.exploreState.scopeMode);
      for (const id of route.exploreState.libraryIds || []) query.append('scope_library', id);
    }
  }
  return '#/' + path + (query.size ? '?' + query : '');
}
export function parseRoute(hash = '') {
  try {
    const [path, search = ''] = hash.replace(/^#\/?/, '').split('?');
    const query = new URLSearchParams(search);
    let view = path === 'create/ideas' ? 'knowledge' : Object.keys(paths).find(key => paths[key] === path), id;
    if (path.startsWith('library/material/') && path.slice(17)) { view = 'material'; id = decodeURIComponent(path.slice(17)); }
    if (path.startsWith('my-work/') && path.slice(8)) { view = 'work'; id = decodeURIComponent(path.slice(8)); }
    if (path.startsWith('internal/material/') && path.slice(18)) { view = 'developerMaterial'; id = decodeURIComponent(path.slice(18)); }
    if (!view) return {view:'home'};
    return {view, id, picker:path === 'create/ideas' || query.get('picker') === '1', library:query.get('library'), add:query.get('add') === '1', materials:[...new Set(query.getAll('material'))], source:query.get('source'), scopeMode:query.get('scope_mode'), scopeLibraryIds:[...new Set(query.getAll('scope_library'))]};
  } catch { return {view:'home'}; }
}
export function createNavigation(browser, render) {
  let lastHash, lastEntry, nextEntry=0;
  const entries=new Map();
  function go(route, replace = false, renderView = true) {
    const hash = routeHash(route);
    const entry=++nextEntry;entries.set(entry,{route,hash});
    browser.history[replace || browser.location.hash === hash ? 'replaceState' : 'pushState']({keEntry:entry}, '', hash);
    lastHash = hash;lastEntry=entry;
    if (renderView) return render(route);
  }
  function restore() {
    // Preserve the native skip-to-content link without changing the active view.
    if (browser.location.hash === '#main' || (browser.location.hash === lastHash && browser.history.state?.keEntry === lastEntry)) return;
    const saved=entries.get(browser.history.state?.keEntry);
    // View state can acquire defaults after rendering (for example a scope
    // mode). Compare the hash actually stored for this entry, retaining its
    // in-memory query and selection rather than reparsing an opaque URL.
    return go(saved?.hash === browser.location.hash ? saved.route : parseRoute(browser.location.hash), true);
  }
  browser.addEventListener('popstate', restore);
  browser.addEventListener('hashchange', restore);
  return {go, start:() => go(parseRoute(browser.location.hash), true)};
}
