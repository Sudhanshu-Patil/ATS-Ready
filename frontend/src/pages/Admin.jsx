import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { RefreshCw } from 'lucide-react'
import api from '../api/client'
import Spinner from '../components/Spinner'
import {
  ChartCard, Columns, HBars, Heatmap, KIND_LABEL, LineChart, Meter, Sparkline, VizStyles, compact, fmt, kindColor,
} from '../components/charts'

const RANGES = [7, 14, 30, 90]
const rupees = (v) => `₹${fmt(v)}`
const pct = (v) => `${(v * 100).toFixed(v && v < 0.1 ? 1 : 0)}%`

function Stat({ label, value, hint, spark, color }) {
  return (
    <div className="card">
      <p className="text-xs text-text-muted">{label}</p>
      <p className="text-2xl font-display font-bold text-text-primary mt-1 tabular-nums">{value}</p>
      {hint && <p className="text-xs text-text-secondary mt-1">{hint}</p>}
      {spark && <Sparkline values={spark} color={color} />}
    </div>
  )
}

const sum = (rows, key) => rows.reduce((t, r) => t + (r[key] || 0), 0)

export default function Admin() {
  const [days, setDays] = useState(30)
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(null)

  const load = (d = days) => {
    setLoading(true)
    api.get('/admin/stats', { params: { days: d } })
      .then((r) => { setData(r.data); setUpdated(new Date()); setError('') })
      .catch(() => setError('Not available.'))
      .finally(() => setLoading(false))
  }
  useEffect(() => { load(days) }, [days])  // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !data) return <div className="p-8 text-text-secondary">{error}</div>
  if (!data) return <div className="p-8 flex justify-center"><Spinner size="lg" /></div>

  const { users, llm, queue, daily, credits, funnel, money, heatmap, resumes_by_status: statuses } = data
  const runs = sum(daily, 'runs'); const failed = sum(daily, 'failed')
  const spark = (key) => daily.map((d) => d[key])
  const kinds = llm.kinds.map((k) => ({ key: k, label: KIND_LABEL[k] || k, color: kindColor(k) }))
  const tokenRows = daily.map((d) => ({ date: d.date, ...d.tokens_by_kind }))
  const unlocksTotal = sum(daily, 'unlocks')
  const funnelTop = funnel[0].users || 1

  return (
    <div className={clsx('viz-root bg-transparent p-4 sm:p-8 max-w-6xl mx-auto space-y-6 transition-opacity', loading && 'opacity-70')}>
      <VizStyles />
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Admin</h1>
          <p className="text-xs text-text-muted mt-1">
            Last {data.days} days{updated ? ` · updated ${updated.toLocaleTimeString()}` : ''} · times are UTC
          </p>
        </div>
        <div className="flex items-center gap-2" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button key={r} onClick={() => setDays(r)} aria-pressed={days === r}
                    className={clsx('px-3 py-1.5 rounded-lg text-sm border transition-colors',
                      days === r ? 'border-brand/50 bg-brand-muted text-brand' : 'border-bg-border text-text-secondary hover:text-text-primary')}>
              {r}d
            </button>
          ))}
          <button onClick={() => load()} aria-label="Refresh" className="btn-ghost p-2"><RefreshCw size={15} className={loading ? 'animate-spin' : ''} /></button>
        </div>
      </div>

      {/* Headline numbers */}
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-4">
        <Stat label="Revenue" value={rupees(money.revenue_inr)} spark={spark('revenue_inr')} color="var(--s3)"
              hint={money.revenue_usd ? `+ $${fmt(money.revenue_usd)} via PayPal` : `${fmt(credits.paying_users)} paying users all time`} />
        <Stat label="Signups" value={fmt(sum(daily, 'signups'))} spark={spark('signups')}
              hint={`${fmt(users.total)} users · ${fmt(users.verified)} verified`} />
        <Stat label="Active users today" value={fmt(users.active_24h)} spark={spark('active_users')}
              hint={`${fmt(users.active_7d)} in 7 days`} />
        <Stat label="Jobs unlocked" value={fmt(unlocksTotal)} spark={spark('unlocks')} color="var(--s2)"
              hint={`${fmt(sum(daily, 'refunds'))} refunded`} />
        <Stat label="Runs" value={fmt(runs)} spark={spark('runs')} hint={`${pct(runs ? failed / runs : 0)} failed`} />
        <Stat label="Est. AI cost" value={rupees(money.est_ai_cost_inr)}
              hint={`${money.margin_inr >= 0 ? 'Margin' : 'Loss'} ${rupees(Math.abs(money.margin_inr))} after AI cost`} />
      </div>

      {/* Growth */}
      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="People" subtitle="Signups, verified signups and users who ran something, per day"
          table={{ columns: [{ key: 'date', label: 'Day' }, { key: 'signups', label: 'Signups' }, { key: 'verified_signups', label: 'Verified' }, { key: 'active_users', label: 'Active' }], rows: daily }}>
          <LineChart data={daily} label={`Signups, verified and active users per day over ${data.days} days`}
            series={[{ key: 'signups', label: 'Signups', color: 'var(--s1)' }, { key: 'verified_signups', label: 'Verified', color: 'var(--s3)' },
                     { key: 'active_users', label: 'Active users', color: 'var(--s2)' }]} />
        </ChartCard>
        <ChartCard title="Sign-up to paying" subtitle="Everyone so far"
          table={{ columns: [{ key: 'step', label: 'Step' }, { key: 'users', label: 'Users' }], rows: funnel }}>
          <HBars items={funnel.map((f) => ({ label: f.step, value: f.users }))}
                 note={(i, idx) => (idx === 0 ? null : `${pct(i.value / funnelTop)} of sign-ups`)} />
          <p className="text-xs text-text-muted mt-4">
            {pct(funnel[4].users / funnelTop)} of sign-ups pay. Steps are counted separately, so a later step can exceed an earlier one (people can start a job before verifying).
          </p>
        </ChartCard>
      </div>

      {/* Money */}
      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="Revenue per day (₹)" subtitle="Rupee payments captured. PayPal dollar payments are in the headline note."
          table={{ columns: [{ key: 'date', label: 'Day' }, { key: 'revenue_inr', label: '₹' }, { key: 'revenue_usd', label: '$' }], rows: daily }}>
          <Columns data={daily} valueFmt={rupees} label={`Revenue per day over ${data.days} days`}
                   keys={[{ key: 'revenue_inr', label: 'Revenue', color: 'var(--s3)' }]} />
        </ChartCard>
        <ChartCard title="Packs sold" subtitle="All time"
          table={{ columns: [{ key: 'pack', label: 'Pack' }, { key: 'payments', label: 'Sold' }], rows: credits.by_pack }}>
          {credits.by_pack.length ? (
            <HBars items={[...credits.by_pack].sort((a, b) => b.payments - a.payments).map((p) => ({ label: `${p.pack} (₹${credits.pack_prices_inr[p.pack] ?? '?'})`, value: p.payments }))} />
          ) : <p className="text-sm text-text-secondary">No payments yet.</p>}
          <p className="text-xs text-text-muted mt-4">
            Unspent credits: {fmt(credits.credits.outstanding_job)} job · {fmt(credits.credits.outstanding_resume)} resume-only
          </p>
        </ChartCard>
      </div>

      <ChartCard title="Credits per day" subtitle="Bought, given free (sign-up and invites) and spent unlocking jobs"
        table={{ columns: [{ key: 'date', label: 'Day' }, { key: 'credits_bought', label: 'Bought' }, { key: 'credits_free', label: 'Free' }, { key: 'unlocks', label: 'Unlocks' }], rows: daily }}>
        <LineChart data={daily} label={`Credits bought, given free and spent per day over ${data.days} days`}
          series={[{ key: 'credits_bought', label: 'Bought', color: 'var(--s3)' }, { key: 'credits_free', label: 'Free', color: 'var(--s1)' },
                   { key: 'unlocks', label: 'Spent (jobs unlocked)', color: 'var(--s2)' }]} />
        <p className="text-xs text-text-muted mt-3">
          Free credits far above bought is normal early. Watch the ratio of spent to bought once people run out of free ones.
        </p>
      </ChartCard>

      {/* Usage and cost */}
      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="AI tokens per day, by feature" subtitle="What the model is spent on"
          table={{ columns: [{ key: 'date', label: 'Day' }, ...llm.kinds.map((k) => ({ key: k, label: KIND_LABEL[k] || k, render: (r) => fmt(r[k] || 0) }))], rows: tokenRows }}>
          {kinds.length ? <Columns data={tokenRows} keys={kinds} valueFmt={compact} label={`AI tokens per day by feature over ${data.days} days`} />
                        : <p className="text-sm text-text-secondary">No AI runs in this period.</p>}
        </ChartCard>
        <ChartCard title="Runs and failures" subtitle="Per day"
          table={{ columns: [{ key: 'date', label: 'Day' }, { key: 'runs', label: 'Runs' }, { key: 'failed', label: 'Failed' }], rows: daily }}>
          <LineChart data={daily} height={170} label={`Runs and failed runs per day over ${data.days} days`}
            series={[{ key: 'runs', label: 'Runs', color: 'var(--s1)' }, { key: 'failed', label: 'Failed', color: 'var(--s8)' }]} />
        </ChartCard>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <ChartCard className="lg:col-span-2" title="By feature" subtitle="Cost and speed per run. Compare tokens per run with what the prices assume."
          table={null}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-text-muted text-xs">
                <tr><th className="py-1 pr-4 font-medium">Feature</th><th className="pr-4 font-medium">Runs</th><th className="pr-4 font-medium">Tokens/run</th>
                  <th className="pr-4 font-medium">≈ ₹/run</th><th className="pr-4 font-medium">Avg</th><th className="pr-4 font-medium">Slowest 5%</th><th className="font-medium">Failed</th></tr>
              </thead>
              <tbody className="text-text-secondary tabular-nums">
                {llm.by_kind.map((k) => (
                  <tr key={k.kind} className="border-t border-bg-border">
                    <td className="py-1.5 pr-4"><span aria-hidden="true" className="inline-block w-2.5 h-2.5 rounded-sm mr-2" style={{ background: kindColor(k.kind) }} />{KIND_LABEL[k.kind] || k.kind}</td>
                    <td className="pr-4">{fmt(k.runs)}</td><td className="pr-4">{fmt(k.tokens_per_run)}</td>
                    <td className="pr-4">{(k.tokens_per_run / 1000 * money.cost_per_1k_tokens_inr).toFixed(2)}</td>
                    <td className="pr-4">{k.avg_seconds}s</td><td className="pr-4">{k.p95_seconds}s</td>
                    <td className={k.failure_rate > 0.1 ? 'text-red-400' : ''}>{pct(k.failure_rate)}{k.failure_rate > 0.1 ? ' ▲' : ''}</td>
                  </tr>
                ))}
                {!llm.by_kind.length && <tr><td colSpan={7} className="py-3">No runs yet.</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-text-muted mt-3">
            Tokens per unlocked job: <strong className="text-text-primary">{credits.last_30d.tokens_per_unlock === null ? 'no unlocks yet' : fmt(credits.last_30d.tokens_per_unlock)}</strong>{' '}
            (prices assume about 40,000, roughly ₹2). Cost uses ₹{money.cost_per_1k_tokens_inr} per 1,000 tokens (<code>LLM_COST_INR_PER_1K_TOKENS</code>).
          </p>
        </ChartCard>

        <ChartCard title="Right now" subtitle="Live">
          <div className="space-y-4">
            <Meter label="AI tokens today (all users)" value={llm.tokens_today} max={llm.daily_cap} />
            <p className="text-xs text-text-muted -mt-2">Per-user daily cap {llm.per_user_cap ? fmt(llm.per_user_cap) : 'off'}.</p>
            <div className="text-sm text-text-secondary">
              <p><strong className="text-text-primary tabular-nums">{fmt(queue.running)}</strong> running · <strong className="text-text-primary tabular-nums">{fmt(queue.pending)}</strong> waiting</p>
              <p className="mt-1 text-xs text-text-muted">Resume jobs: {Object.entries(statuses).map(([s, c]) => `${fmt(c)} ${s}`).join(' · ') || 'none yet'}</p>
            </div>
            <p className="text-xs text-text-muted">Referrals: {fmt(credits.referrals.rewarded)} rewarded · {fmt(credits.referrals.pending)} waiting on a first job</p>
          </div>
        </ChartCard>
      </div>

      <ChartCard title="When people use it" subtitle="Runs by weekday and hour"
        table={{ columns: [{ key: 'day', label: 'Day' }, ...Array.from({ length: 24 }, (_, h) => ({ key: `h${h}`, label: String(h) }))],
                 rows: heatmap.map((row, i) => ({ day: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][i], ...Object.fromEntries(row.map((v, h) => [`h${h}`, v])) })) }}>
        <Heatmap grid={heatmap} />
      </ChartCard>
    </div>
  )
}
