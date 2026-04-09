const LOOPBACK_ALIASES = new Set(['127.0.0.1', '0.0.0.0']);

export function getDevLoopbackRedirectUrl(rawUrl: string, isDev: boolean): string | null {
  if (!isDev) {
    return null;
  }

  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    return null;
  }

  if (!LOOPBACK_ALIASES.has(parsed.hostname)) {
    return null;
  }

  parsed.hostname = 'localhost';
  return parsed.toString();
}

