import { useEffect, useState } from 'react'
import api from '../api/client'
import Spinner from '../components/Spinner'

const fmt = (n) => Number(n || 0).toLocaleString()

function Stat({ label, value, hint }) {
  return (
    <div className="card">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="text-2xl font-display font-bold text-text-primary mt-1">{value}</p>
      {hint && <p className="text-xs text-text-secondary mt-1">{hint}</p>}
    </div>
  )
}

export default function Admin() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/admin/stats').then((r) => setData(r.data)).catch(() => setError('Not available.'))
  }, [])

  if (error) return <div className="p-8 text-text-secondary">{error}</div>
  if (!data) return <div className="p-8 flex justify-center"><Spinner size="lg" /></div>

  const { users, llm, queue, daily, resumes_by_status: statuses } = data
  const capPct = llm.daily_cap ? Math.round((llm.tokens_today / llm.daily_cap) * 100) : null
  const maxRuns = Math.max(1, ...daily.map((d) => d.runs))

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto space-y-6">
      <h1 className="font-display text-2xl font-bold text-text-primary">Admin</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat label="Users" value={fmt(users.total)}
              hint={Object.entries(users.plans).map(([p, c]) => `${c} ${p}`).join(' · ')} />
        <Stat label="Active (24h / 7d)" value={`${fmt(users.active_24h)} / ${fmt(users.active_7d)}`} />
        <Stat label="Queue now" value={`${fmt(queue.running)} running`} hint={`${fmt(queue.pending)} waiting`} />
        <Stat label="AI tokens today" value={fmt(llm.tokens_today)}
              hint={capPct === null ? 'no cap' : `${capPct}% of ${fmt(llm.daily_cap)} daily cap`} />
      </div>

      <section className="card">
        <h2 className="font-semibold text-text-primary mb-3">Runs per day (last 14 days)</h2>
        <div className="flex items-end gap-1.5 h-32" role="img"
             aria-label={`Runs per day: ${daily.map((d) => `${d.date} ${d.runs}`).join(', ')}`}>
          {daily.map((d) => (
            <div key={d.date} className="flex-1 flex flex-col justify-end h-full" title={`${d.date}: ${d.runs} runs, ${d.failed} failed, ${d.signups} signups`}>
              <div className="bg-brand/80 rounded-sm" style={{ height: `${(d.runs / maxRuns) * 100}%`, minHeight: d.runs ? 3 : 0 }} />
            </div>
          ))}
        </div>
        <p className="text-xs text-text-muted mt-2">Hover a bar for the day's runs, failures and signups.</p>
      </section>

      <section className="card overflow-x-auto">
        <h2 className="font-semibold text-text-primary mb-3">By kind (last 30 days)</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-text-muted">
            <tr><th className="py-1 pr-4">Kind</th><th className="pr-4">Runs</th><th className="pr-4">Tokens</th><th className="pr-4">Avg time</th><th>Failure rate</th></tr>
          </thead>
          <tbody className="text-text-secondary">
            {llm.by_kind_30d.map((k) => (
              <tr key={k.kind} className="border-t border-bg-border">
                <td className="py-1.5 pr-4">{k.kind}</td><td className="pr-4">{fmt(k.runs)}</td>
                <td className="pr-4">{fmt(k.tokens)}</td><td className="pr-4">{k.avg_seconds}s</td>
                <td>{Math.round(k.failure_rate * 100)}%</td>
              </tr>
            ))}
            {!llm.by_kind_30d.length && <tr><td colSpan={5} className="py-3">No runs yet.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2 className="font-semibold text-text-primary mb-2">Resume jobs by status</h2>
        <p className="text-sm text-text-secondary">
          {Object.entries(statuses).map(([s, c]) => `${c} ${s}`).join(' · ') || 'None yet'}
        </p>
      </section>
    </div>
  )
}
