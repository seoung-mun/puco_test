import { describe, expect, it } from 'vitest';

import { getDevLoopbackRedirectUrl } from '../devOrigin';

describe('getDevLoopbackRedirectUrl', () => {
  it('returns null outside dev mode', () => {
    expect(getDevLoopbackRedirectUrl('http://127.0.0.1:3000/', false)).toBeNull();
  });

  it('keeps localhost unchanged', () => {
    expect(getDevLoopbackRedirectUrl('http://localhost:3000/rooms', true)).toBeNull();
  });

  it('normalizes 127.0.0.1 to localhost in dev', () => {
    expect(
      getDevLoopbackRedirectUrl('http://127.0.0.1:3000/rooms?tab=bot#login', true),
    ).toBe('http://localhost:3000/rooms?tab=bot#login');
  });

  it('normalizes 0.0.0.0 to localhost in dev', () => {
    expect(getDevLoopbackRedirectUrl('http://0.0.0.0:3000/', true)).toBe(
      'http://localhost:3000/',
    );
  });
});
