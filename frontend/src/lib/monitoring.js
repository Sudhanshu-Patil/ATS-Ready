import { authAPI } from '../api/client'

// Error tracking + web vitals. The DSN comes from the server at runtime
// (/auth/config), so enabling Sentry needs no rebuild. The SDK is loaded lazily
// and only when a DSN is configured, so it costs nothing otherwise.
let sentry = null

export async function initMonitoring() {
  try {
    const { data } = await authAPI.config()
    if (!data.sentry_dsn) return
    sentry = await import('@sentry/react')
    sentry.init({
      dsn: data.sentry_dsn,
      environment: data.environment,
      integrations: [sentry.browserTracingIntegration()],
      tracesSampleRate: 0.1,
      sendDefaultPii: false,
      // Never attach request bodies or user data: resumes are personal.
      beforeSend(event) {
        if (event.request) delete event.request.data
        return event
      },
    })
  } catch {
    // Monitoring must never break the app.
  }
}

export function captureException(error) {
  try { sentry?.captureException(error) } catch { /* ignore */ }
}
