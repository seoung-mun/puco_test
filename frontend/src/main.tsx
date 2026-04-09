import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import './i18n'
import App from './App.tsx'
import { getDevLoopbackRedirectUrl } from './utils/devOrigin'

const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || ''
const redirectUrl =
  typeof window !== 'undefined'
    ? getDevLoopbackRedirectUrl(window.location.href, import.meta.env.DEV)
    : null

if (redirectUrl && typeof window !== 'undefined') {
  window.location.replace(redirectUrl)
} else {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <GoogleOAuthProvider clientId={googleClientId}>
        <App />
      </GoogleOAuthProvider>
    </StrictMode>,
  )
}
