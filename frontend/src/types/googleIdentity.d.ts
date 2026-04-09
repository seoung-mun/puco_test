export interface GoogleCredentialResponse {
  credential?: string;
  select_by?: string;
}

export interface GoogleAccountsIdConfiguration {
  callback: (response: GoogleCredentialResponse) => void;
  cancel_on_tap_outside?: boolean;
  client_id: string;
}

export interface GoogleAccountsButtonConfiguration {
  locale?: string;
  logo_alignment?: 'center' | 'left';
  shape?: 'circle' | 'pill' | 'rectangular' | 'square';
  size?: 'large' | 'medium' | 'small';
  text?: 'continue_with' | 'signin' | 'signin_with' | 'signup_with';
  theme?: 'filled_black' | 'filled_blue' | 'outline';
  width?: number | string;
}

export interface GoogleAccountsIdApi {
  initialize: (config: GoogleAccountsIdConfiguration) => void;
  renderButton: (
    parent: HTMLElement,
    options: GoogleAccountsButtonConfiguration,
  ) => void;
}

export interface GoogleApi {
  accounts: {
    id: GoogleAccountsIdApi;
  };
}

declare global {
  interface Window {
    google?: GoogleApi;
  }
}
