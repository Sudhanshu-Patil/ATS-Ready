import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="card max-w-md text-center space-y-4">
        <p className="text-brand font-mono text-sm">404</p>
        <h1 className="font-display text-2xl font-bold text-text-primary">We can't find that page</h1>
        <p className="text-text-secondary text-sm">The link may be old or mistyped.</p>
        <Link className="btn-primary text-sm inline-block" to="/">Back to ATS-Ready</Link>
      </div>
    </main>
  )
}
