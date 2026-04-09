import { StrictMode } from 'react';
import { render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import GoogleIdentityButton from '../GoogleIdentityButton';

describe('GoogleIdentityButton', () => {
  const initialize = vi.fn();
  const renderButton = vi.fn();

  beforeEach(() => {
    initialize.mockReset();
    renderButton.mockReset();

    window.google = {
      accounts: {
        id: {
          initialize,
          renderButton,
        },
      },
    };
  });

  afterEach(() => {
    delete window.google;
  });

  it('initializes Google Identity only once in StrictMode', async () => {
    render(
      <StrictMode>
        <GoogleIdentityButton
          clientId="test-client-id.apps.googleusercontent.com"
          onSuccess={vi.fn()}
        />
      </StrictMode>,
    );

    await waitFor(() => expect(renderButton).toHaveBeenCalled());
    expect(initialize).toHaveBeenCalledTimes(1);
  });
});
