const rawBackendOrigin = ((import.meta.env.VITE_BACKEND_ORIGIN as string | undefined) ?? '').trim();

export const backendOrigin = rawBackendOrigin.replace(/\/+$/, '');

export function buildApiUrl(path: string): string {
  if (!backendOrigin) {
    return path;
  }
  return new URL(path, backendOrigin).toString();
}

export function buildWebSocketUrl(path: string): string {
  if (!backendOrigin) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return new URL(path, `${protocol}//${window.location.host}`).toString();
  }

  const base = new URL(backendOrigin);
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
  return new URL(path, base).toString();
}
