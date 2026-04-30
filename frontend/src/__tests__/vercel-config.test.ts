import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

describe('vercel.json', () => {
  it('sets Cross-Origin-Opener-Policy for all routes', () => {
    const filePath = resolve(import.meta.dirname, '../../vercel.json');
    const config = JSON.parse(readFileSync(filePath, 'utf-8')) as {
      headers?: Array<{
        source: string;
        headers: Array<{ key: string; value: string }>;
      }>;
    };

    const routeHeaders = config.headers?.find((entry) => entry.source === '/(.*)');

    expect(routeHeaders).toBeDefined();
    expect(routeHeaders?.headers).toContainEqual({
      key: 'Cross-Origin-Opener-Policy',
      value: 'same-origin-allow-popups',
    });
  });
});
