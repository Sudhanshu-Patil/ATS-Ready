import { Component } from 'react'

// Last line of defence: a render error shows a recoverable screen, not a blank page.
export default class ErrorBoundary extends Component {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  componentDidCatch(error, info) {
    console.error('UI crash', error, info?.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="min-h-screen flex items-center justify-center p-6">
        <div className="card max-w-md text-center space-y-4">
          <h1 className="font-display text-2xl font-bold text-text-primary">Something went wrong</h1>
          <p className="text-text-secondary text-sm">
            The page hit an unexpected error. Your data is safe. Reloading usually fixes it.
          </p>
          <div className="flex gap-2 justify-center">
            <button className="btn-primary text-sm" onClick={() => window.location.reload()}>Reload</button>
            <a className="btn-ghost text-sm" href="/">Go home</a>
          </div>
        </div>
      </main>
    )
  }
}
