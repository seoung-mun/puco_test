import { describe, expect, it } from 'vitest';

import { buildGoogleLoginSetupMessage } from '../googleOAuth';

describe('googleOAuth helpers', () => {
  it('guides the user to wire the frontend client id when it is missing', () => {
    const message = buildGoogleLoginSetupMessage({
      origin: 'http://localhost:3000',
      googleClientConfigured: false,
    });

    expect(message).toContain('VITE_GOOGLE_CLIENT_ID');
    expect(message).toContain('http://localhost:3000');
  });

  it('guides the user to add the exact origin and teammate accounts when config exists', () => {
    const message = buildGoogleLoginSetupMessage({
      origin: 'https://play.example.com',
      googleClientConfigured: true,
    });

    expect(message).toContain('https://play.example.com');
    expect(message).toContain('Authorized JavaScript origins');
    expect(message).toContain('Test users');
    expect(message).toContain('ALLOWED_ORIGINS');
  });
});
