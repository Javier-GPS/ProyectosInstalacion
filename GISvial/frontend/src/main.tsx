import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { GisAuthProvider } from './auth/AuthContext'
import { GisI18nProvider } from './i18n'
import './index.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <GisI18nProvider>
      <GisAuthProvider>
        <App />
      </GisAuthProvider>
    </GisI18nProvider>
  </React.StrictMode>,
)
