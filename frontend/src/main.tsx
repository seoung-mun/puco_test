import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import './i18n'
import App from './App.tsx'
import { googleClientId, googleLoginConfigured } from './googleOAuth'

const app = <App />

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {googleLoginConfigured ? (
      <GoogleOAuthProvider clientId={googleClientId}>
        {app}
      </GoogleOAuthProvider>
    ) : (
      app
    )}
  </StrictMode>,
)
