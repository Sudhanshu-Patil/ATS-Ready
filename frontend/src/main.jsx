import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { MotionConfig } from 'framer-motion'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import '@fontsource-variable/instrument-sans'
import '@fontsource-variable/newsreader'
import '@fontsource-variable/geist-mono'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {/* reducedMotion="user" strips transform/scale/layout animation under OS
        prefers-reduced-motion, leaves opacity fades — one root-level switch
        that covers every motion.* component in the app. */}
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <ErrorBoundary><App /></ErrorBoundary>
        <Toaster
          position={window.matchMedia('(max-width: 639px)').matches ? 'bottom-center' : 'top-right'}
          containerStyle={{ bottom: 20 }}
          toastOptions={{
            style: {
              background: 'rgb(var(--color-bg-card))',
              color: 'rgb(var(--color-text-primary))',
              border: '1px solid rgb(var(--color-bg-border))',
              borderRadius: '10px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.10)',
              fontFamily: 'Instrument Sans Variable, system-ui, sans-serif',
              fontSize: '14px',
            },
            success: { iconTheme: { primary: 'rgb(var(--color-score))', secondary: 'rgb(var(--color-bg-card))' } },
            error:   { iconTheme: { primary: 'rgb(var(--color-brand))', secondary: 'rgb(var(--color-bg-card))' } },
          }}
        />
      </BrowserRouter>
    </MotionConfig>
  </React.StrictMode>
)
