import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { MotionConfig } from 'framer-motion'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
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
          position="top-right"
          toastOptions={{
            style: {
              background: '#13131A',
              color: '#F3F1EC',
              border: '1px solid #26262F',
              fontFamily: 'Plus Jakarta Sans, sans-serif',
            },
            success: { iconTheme: { primary: '#34D399', secondary: '#0A0A0F' } },
            error:   { iconTheme: { primary: '#FF6B35', secondary: '#0A0A0F' } },
          }}
        />
      </BrowserRouter>
    </MotionConfig>
  </React.StrictMode>
)
