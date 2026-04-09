import { useEffect, useRef } from 'react';
import type {
  GoogleAccountsButtonConfiguration,
  GoogleAccountsIdApi,
  GoogleCredentialResponse,
} from '../types/googleIdentity';

interface Props {
  clientId: string;
  onSuccess: (credentialResponse: GoogleCredentialResponse) => void;
}

const GOOGLE_BUTTON_OPTIONS: GoogleAccountsButtonConfiguration = {
  theme: 'filled_black',
  size: 'large',
  shape: 'rectangular',
  text: 'continue_with',
  logo_alignment: 'left',
  width: 280,
};

let initializedClientId: string | null = null;
let latestSuccessHandler: ((credentialResponse: GoogleCredentialResponse) => void) | null = null;

function getGoogleIdentityApi(): GoogleAccountsIdApi | null {
  return window.google?.accounts?.id ?? null;
}

export default function GoogleIdentityButton({
  clientId,
  onSuccess,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!clientId) {
      return;
    }

    latestSuccessHandler = onSuccess;

    let intervalId: number | null = null;

    const mountButton = () => {
      const googleIdentity = getGoogleIdentityApi();
      const container = containerRef.current;

      if (!googleIdentity || !container) {
        return false;
      }

      if (initializedClientId !== clientId) {
        googleIdentity.initialize({
          client_id: clientId,
          callback: (response) => {
            latestSuccessHandler?.(response);
          },
          cancel_on_tap_outside: true,
        });
        initializedClientId = clientId;
      }

      container.innerHTML = '';
      googleIdentity.renderButton(container, GOOGLE_BUTTON_OPTIONS);
      return true;
    };

    if (!mountButton()) {
      intervalId = window.setInterval(() => {
        if (mountButton() && intervalId !== null) {
          window.clearInterval(intervalId);
          intervalId = null;
        }
      }, 50);
    }

    return () => {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
      }
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
      if (latestSuccessHandler === onSuccess) {
        latestSuccessHandler = null;
      }
    };
  }, [clientId, onSuccess]);

  return <div ref={containerRef} aria-label="google-login-button" />;
}
