import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'

/**
 * Small SVG charts for the admin page (no chart library). Colours are roles, not hex: the categorical slots are the
 * validated 8-hue order (adjacent pairs pass the colour-blind and normal-vision floors in both modes; three light-mode
 * slots are under 3:1 contrast on the surface, so every chart also has a legend, direct values and a table view).
 * Text never takes a series colour; a mark beside it carries the identity.
 */
const STYLE = `
.viz-root {
  color-scheme: light;
  --viz-surface: #fcfcfb; --viz-grid: #e7e6e2; --viz-axis: #9b9a94;
  --viz-ink: #0b0b0b; --viz-ink-2: #52514e; --viz-ink-3: #7a7973;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100; --s5: #e87ba4; --s6: #008300; --s7: #6250d6; --s8: #e34948;
  --seq-1: #cde2fb; --seq-2: #9ec5f4; --seq-3: #5598e7; --seq-4: #256abf; --seq-5: #104281;
  --good: #0ca30c; --bad: #d03b3b;
}
:root[data-theme='dark'] .viz-root {
  color-scheme: dark;
  --viz-surface: #1a1a19; --viz-grid: #2b2b29; --viz-axis: #6b6a65;
  --viz-ink: #f0efec; --viz-ink-2: #c3c2b7; --viz-ink-3: #8f8e86;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500; --s5: #d55181; --s6: #0ca30c; --s7: #9085e9; --s8: #e66767;
  --seq-1: #184f95; --seq-2: #1c5cab; --seq-3: #2a78d6; --seq-4: #5598e7; --seq-5: #9ec5f4;
}
.viz-root .viz-hit:focus-visible { outline: 2px solid var(--s1); outline-offset: 2px; }
`
export function VizStyles() { return <style>{STYLE}</style> }

// A fixed slot per entity, so a colour never changes with what else is on screen.
const KIND_SLOT = { resume: 1, cover_letter: 2, interview_prep: 3, assistant: 4, referral: 5, follow_up: 6, import: 7 }
export const kindColor = (kind) => `var(--s${KIND_SLOT[kind] || 8})`
export const KIND_LABEL = { resume: 'Resume', cover_letter: 'Cover letter', interview_prep: 'Interview prep', assistant: 'Answers',
                            referral: 'Reach-out', follow_up: 'Follow-up', import: 'Resume import' }

export const fmt = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 1 })
export const compact = (n) => (Math.abs(n) >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : Math.abs(n) >= 1e4 ? `${+(n / 1e3).toFixed(1)}K` : fmt(n))
const shortDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

function niceTicks(max, count = 4) {
  if (!max || max <= 0) return [0, 1]
  const raw = max / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const top = Math.ceil(max / step) * step
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => +(i * step).toFixed(6))
}

function useWidth() {
  const ref = useRef(null)
  const [w, setW] = useState(640)
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === 'undefined') return undefined
    const ro = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, w]
}

// ── Card with a chart/table switch (the table is the accessible twin of every chart) ─────────────────────────
export function ChartCard({ title, subtitle, table, children, className }) {
  const [view, setView] = useState('chart')
  return (
    <section className={clsx('card min-w-0', className)}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h2 className="font-semibold text-text-primary">{title}</h2>
          {subtitle && <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>}
        </div>
        {table && (
          <button onClick={() => setView(view === 'chart' ? 'table' : 'chart')}
                  className="text-xs text-text-muted hover:text-text-primary underline flex-shrink-0 py-1 px-1">
            {view === 'chart' ? 'Table view' : 'Chart view'}
          </button>
        )}
      </div>
      {view === 'table' && table ? <DataTable {...table} /> : children}
    </section>
  )
}

export function DataTable({ columns, rows }) {
  return (
    <div className="overflow-auto max-h-72">
      <table className="w-full text-xs">
        <thead className="text-left text-text-muted sticky top-0 bg-bg-card">
          <tr>{columns.map((c) => <th key={c.key} className="py-1 pr-4 font-medium">{c.label}</th>)}</tr>
        </thead>
        <tbody className="text-text-secondary">
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-bg-border">
              {columns.map((c) => <td key={c.key} className="py-1 pr-4 tabular-nums">{c.render ? c.render(r) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Legend({ items }) {
  if (items.length < 2) return null
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 mb-2" aria-label="Legend">
      {items.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5 text-xs text-text-secondary">
          <span aria-hidden="true" className="inline-block w-3 h-0.5 rounded" style={{ background: s.color, height: 3 }} />{s.label}
        </li>
      ))}
    </ul>
  )
}

function Tip({ x, width, children }) {
  const left = Math.min(Math.max(x, 0), width)
  return (
    <div role="status" className="pointer-events-none absolute top-0 z-10 rounded-lg border border-bg-border bg-bg-card shadow-lg px-3 py-2 text-xs"
         style={{ left, transform: `translateX(${left > width * 0.6 ? '-105%' : '8px'})`, minWidth: 140 }}>
      {children}
    </div>
  )
}

const PAD = { l: 44, r: 12, t: 8, b: 22 }

// ── Line / area chart: one y axis, crosshair tooltip listing every series ────────────────────────────────────
export function LineChart({ data, series, height = 190, area = false, valueFmt = fmt, label }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState(null)
  const n = data.length
  const plotW = width - PAD.l - PAD.r
  const plotH = height - PAD.t - PAD.b
  const max = Math.max(1, ...series.flatMap((s) => data.map((d) => d[s.key] || 0)))
  const ticks = niceTicks(max)
  const top = ticks[ticks.length - 1]
  const x = (i) => PAD.l + (n <= 1 ? 0 : (i / (n - 1)) * plotW)
  const y = (v) => PAD.t + plotH - (v / top) * plotH
  const path = (key) => data.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d[key] || 0).toFixed(1)}`).join('')
  const move = (clientX, rect) => setHover(Math.max(0, Math.min(n - 1, Math.round(((clientX - rect.left - PAD.l) / plotW) * (n - 1)))))
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(plotW / 70))))
  const h = hover === null ? null : data[hover]

  return (
    <div ref={ref} className="relative min-w-0 w-full">
      <Legend items={series} />
      <svg width={width} height={height} role="img" aria-label={label}
           tabIndex={0} className="viz-hit block max-w-full" style={{ touchAction: 'pan-y' }}
           onPointerDown={(e) => move(e.clientX, e.currentTarget.getBoundingClientRect())}
           onPointerMove={(e) => move(e.clientX, e.currentTarget.getBoundingClientRect())}
           onPointerLeave={() => setHover(null)}
           onKeyDown={(e) => {
             if (e.key === 'ArrowRight') setHover((v) => Math.min(n - 1, (v ?? -1) + 1))
             if (e.key === 'ArrowLeft') setHover((v) => Math.max(0, (v ?? n) - 1))
             if (e.key === 'Escape') setHover(null)
           }}
           onBlur={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={width - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth="1" />
            <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--viz-ink-3)">{compact(t)}</text>
          </g>
        ))}
        {data.map((d, i) => (i % labelEvery === 0 ? (
          <text key={d.date} x={x(i)} y={height - 5} textAnchor="middle" fontSize="10" fill="var(--viz-ink-3)">{shortDate(d.date)}</text>
        ) : null))}
        {area && series.length === 1 && (
          <path d={`${path(series[0].key)}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`} fill={series[0].color} opacity="0.1" />
        )}
        {series.map((s) => (
          <g key={s.key}>
            <path d={path(s.key)} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            {n > 0 && <circle cx={x(n - 1)} cy={y(data[n - 1][s.key] || 0)} r="4" fill={s.color} stroke="var(--viz-surface)" strokeWidth="2" />}
          </g>
        ))}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + plotH} stroke="var(--viz-axis)" strokeWidth="1" />
            {series.map((s) => <circle key={s.key} cx={x(hover)} cy={y(h[s.key] || 0)} r="4" fill={s.color} stroke="var(--viz-surface)" strokeWidth="2" />)}
          </g>
        )}
      </svg>
      {h && (
        <Tip x={x(hover)} width={width}>
          <p className="text-text-muted mb-1">{shortDate(h.date)}</p>
          {series.map((s) => (
            <p key={s.key} className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block w-3 rounded" style={{ background: s.color, height: 3 }} />
              <strong className="text-text-primary tabular-nums">{(s.fmt || valueFmt)(h[s.key] || 0)}</strong>
              <span className="text-text-secondary">{s.label}</span>
            </p>
          ))}
        </Tip>
      )}
    </div>
  )
}

// ── Columns (optionally stacked): <= 24px wide, 4px rounded tops, 2px gaps between segments ──────────────────
export function Columns({ data, keys, height = 190, valueFmt = fmt, label }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState(null)
  const n = data.length
  const plotW = width - PAD.l - PAD.r
  const plotH = height - PAD.t - PAD.b
  const totals = data.map((d) => keys.reduce((t, k) => t + (d[k.key] || 0), 0))
  const ticks = niceTicks(Math.max(1, ...totals))
  const top = ticks[ticks.length - 1]
  const slot = plotW / Math.max(1, n)
  const bw = Math.min(24, Math.max(3, slot - 3))
  const y = (v) => PAD.t + plotH - (v / top) * plotH
  const labelEvery = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(plotW / 70))))
  const h = hover === null ? null : data[hover]

  return (
    <div ref={ref} className="relative min-w-0 w-full">
      <Legend items={keys} />
      <svg width={width} height={height} role="img" aria-label={label} tabIndex={0} className="viz-hit block max-w-full"
           style={{ touchAction: 'pan-y' }} onPointerLeave={() => setHover(null)}
           onKeyDown={(e) => {
             if (e.key === 'ArrowRight') setHover((v) => Math.min(n - 1, (v ?? -1) + 1))
             if (e.key === 'ArrowLeft') setHover((v) => Math.max(0, (v ?? n) - 1))
             if (e.key === 'Escape') setHover(null)
           }} onBlur={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PAD.l} x2={width - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--viz-grid)" strokeWidth="1" />
            <text x={PAD.l - 8} y={y(t) + 4} textAnchor="end" fontSize="10" fill="var(--viz-ink-3)">{compact(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = PAD.l + slot * i + slot / 2
          let acc = 0
          const live = keys.filter((k) => d[k.key] > 0)
          return (
            <g key={d.date} opacity={hover === null || hover === i ? 1 : 0.55}>
              {live.map((k, idx) => {
                const y1 = y(acc + d[k.key]); const y0 = y(acc)
                acc += d[k.key]
                const topSeg = idx === live.length - 1
                const hgt = Math.max(1, y0 - y1 - (idx ? 2 : 0))   // 2px surface gap between stacked segments
                const yy = y1
                const r = Math.min(4, hgt / 2, bw / 2)
                return topSeg
                  ? <path key={k.key} fill={k.color} d={`M${cx - bw / 2},${yy + hgt}V${yy + r}Q${cx - bw / 2},${yy} ${cx - bw / 2 + r},${yy}H${cx + bw / 2 - r}Q${cx + bw / 2},${yy} ${cx + bw / 2},${yy + r}V${yy + hgt}Z`} />
                  : <rect key={k.key} x={cx - bw / 2} y={yy} width={bw} height={hgt} fill={k.color} />
              })}
              <rect x={PAD.l + slot * i} y={PAD.t} width={slot} height={plotH} fill="transparent" className="cursor-default"
                    onPointerEnter={() => setHover(i)} onPointerDown={() => setHover(i)} onPointerMove={() => setHover(i)} />
              {i % labelEvery === 0 && <text x={cx} y={height - 5} textAnchor="middle" fontSize="10" fill="var(--viz-ink-3)">{shortDate(d.date)}</text>}
            </g>
          )
        })}
      </svg>
      {h && (
        <Tip x={PAD.l + slot * hover + slot / 2} width={width}>
          <p className="text-text-muted mb-1">{shortDate(h.date)}</p>
          {keys.filter((k) => h[k.key] > 0).map((k) => (
            <p key={k.key} className="flex items-center gap-2">
              <span aria-hidden="true" className="inline-block w-3 rounded" style={{ background: k.color, height: 3 }} />
              <strong className="text-text-primary tabular-nums">{(k.fmt || valueFmt)(h[k.key])}</strong>
              <span className="text-text-secondary">{k.label}</span>
            </p>
          ))}
          {keys.length > 1 && <p className="text-text-muted mt-1 border-t border-bg-border pt-1">Total {valueFmt(totals[hover])}</p>}
          {!totals[hover] && <p className="text-text-muted">Nothing that day</p>}
        </Tip>
      )}
    </div>
  )
}

// ── Ranked horizontal bars (and the funnel): value at the tip, one hue ────────────────────────────────────────
export function HBars({ items, valueFmt = fmt, color = 'var(--s1)', note }) {
  const max = Math.max(1, ...items.map((i) => i.value))
  return (
    <ul className="space-y-2.5">
      {items.map((i, idx) => (
        <li key={i.label} title={i.title}>
          <div className="flex items-baseline justify-between text-xs mb-1 gap-2">
            <span className="text-text-secondary">{i.label}</span>
            <span className="text-text-primary tabular-nums">
              <strong>{valueFmt(i.value)}</strong>{note && note(i, idx) ? <span className="text-text-muted"> · {note(i, idx)}</span> : null}
            </span>
          </div>
          <div className="h-2.5 rounded-sm bg-bg-hover/60 overflow-hidden" aria-hidden="true">
            <div style={{ width: `${(i.value / max) * 100}%`, background: i.color || color, minWidth: i.value ? 3 : 0 }}
                 className="h-full rounded-r" />
          </div>
        </li>
      ))}
    </ul>
  )
}

// ── Heatmap: weekday x hour, one hue light -> dark ───────────────────────────────────────────────────────────
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
export function Heatmap({ grid }) {
  const [hover, setHover] = useState(null)
  const max = Math.max(1, ...grid.flat())
  const step = (v) => (v === 0 ? null : `var(--seq-${Math.min(5, 1 + Math.floor((v / max) * 4.999))})`)
  return (
    <div className="relative overflow-x-auto" role="img" aria-label="Runs by weekday and hour, UTC">
      <div className="min-w-[560px]">
        {grid.map((row, d) => (
          <div key={DAYS[d]} className="flex items-center gap-[2px] mb-[2px]">
            <span className="w-9 text-[10px] text-text-muted flex-shrink-0">{DAYS[d]}</span>
            {row.map((v, h) => (
              <div key={h} onPointerEnter={() => setHover({ d, h, v })} onPointerLeave={() => setHover(null)}
                   className={clsx('flex-1 h-5 rounded-[3px]', hover?.d === d && hover?.h === h && 'outline outline-2 outline-[var(--viz-ink)]')}
                   style={{ background: step(v) || 'var(--viz-grid)', opacity: step(v) ? 1 : 0.6 }} />
            ))}
          </div>
        ))}
        <div className="flex items-center gap-[2px] mt-1">
          <span className="w-9" />
          {Array.from({ length: 24 }, (_, h) => <span key={h} className="flex-1 text-center text-[9px] text-text-muted">{h % 3 === 0 ? h : ''}</span>)}
        </div>
      </div>
      <p className="text-xs text-text-muted mt-2" aria-live="polite">
        {hover ? <><strong className="text-text-primary">{fmt(hover.v)}</strong> run{hover.v === 1 ? '' : 's'} · {DAYS[hover.d]} {String(hover.h).padStart(2, '0')}:00 UTC</>
               : 'Hours are UTC (IST is 5 h 30 m ahead). Darker is busier.'}
      </p>
    </div>
  )
}

export function Sparkline({ values, color = 'var(--s1)' }) {
  const w = 96; const h = 28
  const max = Math.max(1, ...values)
  const pts = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * (w - 6) + 3},${h - 4 - (v / max) * (h - 8)}`)
  return (
    <svg width={w} height={h} aria-hidden="true" className="mt-2">
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {pts.length > 0 && <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]} r="3" fill={color} stroke="var(--viz-surface)" strokeWidth="2" />}
    </svg>
  )
}

/** A single ratio against a limit. */
export function Meter({ value, max, label, color = 'var(--s1)' }) {
  const pct = max ? Math.min(100, (value / max) * 100) : 0
  const hot = pct >= 80
  return (
    <div>
      <div className="flex justify-between text-xs mb-1"><span className="text-text-secondary">{label}</span>
        <span className="text-text-primary tabular-nums">{fmt(value)} / {max ? fmt(max) : 'no cap'}{hot ? ' · high' : ''}</span></div>
      <div className="h-2.5 rounded-sm bg-bg-hover/60 overflow-hidden" role="meter" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max || undefined} aria-label={label}>
        <div className="h-full rounded-r" style={{ width: `${pct}%`, background: hot ? 'var(--bad)' : color }} />
      </div>
    </div>
  )
}
