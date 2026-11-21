import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { motion } from 'framer-motion'
import { ExternalLink, RefreshCw, Briefcase, MapPin, Zap, AlertCircle, Search, X } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import api, { recommendationsAPI } from '../api/client'
import toast from 'react-hot-toast'
import { fadeInUp } from '../lib/motion'
import ScoreRing from './ScoreRing'
import { Skeleton } from './Skeleton'
import EmptyState from './EmptyState'
import clsx from 'clsx'

// Cap what's actually rendered, independent of how many matched jobs the
// backend returns (up to 60) — keeps the grid/stagger animation bounded and
// predictable regardless of filter state. Filters narrow WITHIN this larger
// fetched pool rather than re-fetching, so they usually have real results to
// show instead of emptying out a set that was already truncated to ~20.
const DISPLAY_CAP = 20

// ── Source badge ──────────────────────────────────────────────────────────────
function SourceBadge({ source }) {
  return <span className="text-[11px] text-text-muted">{source}</span>
}

// ── Relative time ─────────────────────────────────────────────────────────────
function relativeTime(dateStr) {
  if (!dateStr) return null
  try {
    const diff = Date.now() - new Date(dateStr).getTime()
    const hours = Math.floor(diff / 3_600_000)
    if (hours < 1) return 'just now'
    if (hours < 24) return `${hours}h ago`
    const days = Math.floor(hours / 24)
    if (days < 30) return `${days}d ago`
    return `${Math.floor(days / 30)}mo ago`
  } catch {
    return null
  }
}

function exactTime(dateStr) {
  const d = new Date(dateStr)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' })
}

// Which day heading a posting belongs under (used when the list is sorted by newest).
function dayGroup(postedAt) {
  if (!postedAt) return 'Date not given'
  const days = Math.floor((Date.now() - new Date(postedAt).getTime()) / 86_400_000)
  if (days < 1) return 'Today'
  if (days < 2) return 'Yesterday'
  if (days < 7) return 'This week'
  if (days < 30) return 'This month'
  return 'Older'
}

// ── Filters ──────────────────────────────────────────────────────────────────
const DATE_FILTERS = [
  { id: 'any', label: 'Any time' },
  { id: '3h',  label: 'Last 3 hours',  hours: 3 },
  { id: '1d',  label: 'Last 24 hours', hours: 24 },
  { id: '3d',  label: 'Last 3 days',   hours: 24 * 3 },
  { id: '7d',  label: 'Last 7 days',   hours: 24 * 7 },
  { id: '30d', label: 'Last 30 days',  hours: 24 * 30 },
]

const SCORE_FILTERS = [
  { id: 'any', label: 'Any match', min: 0 },
  { id: '50',  label: '50%+ match', min: 50 },
  { id: '70',  label: '70%+ match', min: 70 },
]

const DEFAULT_FILTERS = { q: '', location: 'any', source: 'any', date: 'any', score: 'any', sort: 'match', remote: false }
const STORE_KEY = 'ats.jobFilters'
// The choices (not the search words) are remembered between visits.
function loadFilters() {
  try { return { ...DEFAULT_FILTERS, ...JSON.parse(localStorage.getItem(STORE_KEY) || '{}'), q: '' } } catch { return DEFAULT_FILTERS }
}
const isRemote = (j) => /remote|anywhere|worldwide/i.test(`${j.location} ${j.title}`)
const matchesQuery = (j, q) => {
  const hay = `${j.title} ${j.company} ${j.location} ${(j.matched_skills || []).join(' ')} ${j.description || ''}`.toLowerCase()
  return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w))
}

function jobWithinDateFilter(postedAt, filterId) {
  if (filterId === 'any') return true
  if (!postedAt) return false // can't verify recency, exclude rather than assume
  const bucket = DATE_FILTERS.find(f => f.id === filterId)
  const hoursAgo = (Date.now() - new Date(postedAt).getTime()) / 3_600_000
  return hoursAgo <= bucket.hours
}

function FilterBar({ filters, setFilter, locationOptions, sourceOptions, onClear, isActive }) {
  return (
    <div className="flex items-center gap-2 flex-wrap mb-4">
      <div className="relative w-full sm:w-64">
        <Search size={14} aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input type="search" aria-label="Search jobs" className="input text-sm !pl-9 py-1.5" placeholder="Search title, company or skill"
               value={filters.q} onChange={(e) => setFilter('q', e.target.value)} />
      </div>
      <select aria-label="Sort" className="input text-xs !w-auto py-1.5" value={filters.sort} onChange={(e) => setFilter('sort', e.target.value)}>
        <option value="match">Best match first</option>
        <option value="new">Newest first</option>
      </select>
      <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer px-1">
        <input type="checkbox" checked={filters.remote} onChange={(e) => setFilter('remote', e.target.checked)} /> Remote only
      </label>
      <select
        className="input text-xs !w-auto py-1.5"
        value={filters.location}
        onChange={(e) => setFilter('location', e.target.value)}
      >
        <option value="any">All locations</option>
        {locationOptions.map(loc => <option key={loc} value={loc}>{loc}</option>)}
      </select>

      <select
        className="input text-xs !w-auto py-1.5"
        value={filters.date}
        onChange={(e) => setFilter('date', e.target.value)}
      >
        {DATE_FILTERS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
      </select>

      <select
        className="input text-xs !w-auto py-1.5"
        value={filters.source}
        onChange={(e) => setFilter('source', e.target.value)}
      >
        <option value="any">All sources</option>
        {sourceOptions.map(src => <option key={src} value={src}>{src}</option>)}
      </select>

      <select
        className="input text-xs !w-auto py-1.5"
        value={filters.score}
        onChange={(e) => setFilter('score', e.target.value)}
      >
        {SCORE_FILTERS.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
      </select>

      {isActive && (
        <button
          onClick={onClear}
          className="flex items-center gap-1 text-xs text-text-muted hover:text-bad transition-colors"
        >
          <X size={12} /> Clear filters
        </button>
      )}
    </div>
  )
}

// ── Single job card ───────────────────────────────────────────────────────────
function JobCard({ job }) {
  const navigate = useNavigate()
  const visibleSkills = job.matched_skills.slice(0, 4)
  const extraSkills   = job.matched_skills.length - visibleSkills.length
  const posted        = relativeTime(job.posted_at)

  // Deliberately NOT a motion element: per-card entrance variants replayed
  // on every filter change (cards trickling in at scattered positions reads
  // as broken layout). The grid container fades once; filtering is instant.
  return (
    <div
      className="group relative rounded-xl border border-bg-border bg-bg-card p-4 flex flex-col gap-3
                 hover:border-text-muted/60 transition-all duration-300"
    >
      {/* Top row: score ring + title/company */}
      <div className="flex items-start gap-3">
        <ScoreRing score={job.match_score} size="sm" />
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-text-primary leading-tight line-clamp-2 group-hover:text-brand transition-colors">
            {job.title}
          </h3>
          <p className="text-xs text-text-secondary mt-0.5 truncate">{job.company}</p>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            <span className="inline-flex items-center gap-1 text-[11px] text-text-muted">
              <MapPin size={10} /> {job.location}
            </span>
            {posted && (
              <time dateTime={job.posted_at} title={exactTime(job.posted_at)} className="text-[11px] text-text-muted">{posted}</time>
            )}
            <SourceBadge source={job.source} />
          </div>
        </div>
      </div>

      {/* Matched skills chips */}
      {visibleSkills.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {visibleSkills.map(skill => (
            <span
              key={skill}
              className="px-2 py-0.5 rounded-full bg-bg-hover border border-bg-border text-brand text-[10px] font-medium"
            >
              {skill}
            </span>
          ))}
          {extraSkills > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-bg-hover text-text-muted text-[10px]">
              +{extraSkills} more
            </span>
          )}
        </div>
      )}

      {job.match_reasons?.length > 0 && (
        <p className="text-[11px] text-text-muted">Why: {job.match_reasons.join(' · ')}</p>
      )}

      {/* Action buttons */}
      <div className="flex gap-2 mt-auto pt-1">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg
                     border border-bg-border text-xs text-text-secondary
                     hover:border-text-muted/60 hover:text-brand transition-colors"
        >
          <ExternalLink size={11} /> View Job
        </a>
        <button
          onClick={() => startJob(job).then((id) => id && navigate(`/jobs/${id}`))}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg
                     bg-bg-hover border border-bg-border text-xs text-brand font-medium
                     hover:bg-bg-hover transition-colors"
        >
          <Zap size={11} /> Start this job
        </button>
      </div>
      <button
        onClick={() => startJob(job).then((id) => id && navigate(`/cover-letter?job=${id}&tab=referral`, { state: { jobUrl: job.url } }))}
        className="text-[11px] text-text-muted hover:text-brand transition-colors text-left"
      >
        Draft a LinkedIn referral request →
      </button>
    </div>
  )
}

// A listing becomes a job: its text (or link) is saved once and every tool then works from it.
async function startJob(job) {
  try {
    const description = (job.description || '').trim()
    const { data } = await api.post('/applications', {
      company: job.company || undefined, role: job.title || undefined, job_url: job.url || undefined,
      ...(description.length >= 200 ? { jd_text: `${job.title} at ${job.company}\n\n${description}` } : {}),
    })
    return data.id
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Could not start this job')
    return null
  }
}

// ── Loading skeleton ──────────────────────────────────────────────────────────
function SkeletonCard() {
  return (
    <div className="rounded-xl border border-bg-border bg-bg-card p-4 space-y-3">
      <div className="flex items-start gap-3">
        <Skeleton className="w-14 h-14 rounded-full flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-3.5 w-4/5" />
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      </div>
      <div className="flex gap-1.5">
        <Skeleton className="h-5 rounded-full w-16" />
        <Skeleton className="h-5 rounded-full w-20" />
        <Skeleton className="h-5 rounded-full w-14" />
      </div>
      <div className="flex gap-2 pt-1">
        <Skeleton className="flex-1 h-8 rounded-lg" />
        <Skeleton className="flex-1 h-8 rounded-lg" />
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
// `bare` drops the top margin when it is the main content of a tab; `compact` (dashboard) shows only a few and links on.
export default function JobRecommendations({ bare = false }) {
  const [jobs, setJobs]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError]         = useState(null)
  const [lastFetched, setLastFetched] = useState(null)
  const [total, setTotal]         = useState(0)
  const [filters, setFilters]     = useState(loadFilters)
  const [shown, setShown]         = useState(DISPLAY_CAP)

  // The server answers at once; a cold fetch (live job-board crawls) continues in the
  // background and reports status "pending" until it is done, so poll rather than wait.
  const pollTimer = useRef(null)
  const polls = useRef(0)
  const MAX_POLLS = 60            // x 4s: stop after ~4 minutes

  const fetchJobs = useCallback(async (forceRefresh = false) => {
    clearTimeout(pollTimer.current)
    if (forceRefresh) { setRefreshing(true); polls.current = 0 }
    else if (polls.current === 0) setLoading(true)
    setError(null)

    try {
      const { data } = await recommendationsAPI.get(forceRefresh)
      setJobs(data.jobs || [])
      setTotal(data.total || 0)
      if (data.status === 'pending' && polls.current < MAX_POLLS) {
        polls.current += 1
        pollTimer.current = setTimeout(() => fetchJobs(false), 4000)
        return                                  // keep the loading/refreshing state on
      }
      polls.current = 0
      setLastFetched(new Date())
    } catch (err) {
      if (err?.response?.status === 429 && polls.current < MAX_POLLS) {   // too many checks too fast: wait, look again
        polls.current += 1
        pollTimer.current = setTimeout(() => fetchJobs(false), 15000)
        return
      }
      polls.current = 0
      setError(err?.response?.data?.detail || 'Failed to load job recommendations.')
    }
    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    fetchJobs()
    return () => clearTimeout(pollTimer.current)
  }, [fetchJobs])

  // Filter option lists are derived from whatever's actually in the current
  // fetched set — locations/sources are freeform strings from 6 different
  // job boards, so a fixed dropdown list would either miss values or show
  // options with zero matching jobs. Recomputes only when `jobs` changes,
  // not on every filter tweak (filters themselves don't affect this).
  const locationOptions = useMemo(
    () => [...new Set(jobs.map(j => j.location).filter(Boolean))].sort(),
    [jobs]
  )
  const sourceOptions = useMemo(
    () => [...new Set(jobs.map(j => j.source).filter(Boolean))].sort(),
    [jobs]
  )

  const filteredJobs = useMemo(() => {
    const minScore = SCORE_FILTERS.find(f => f.id === filters.score)?.min ?? 0
    const out = jobs.filter(job =>
      (filters.location === 'any' || job.location === filters.location) &&
      (filters.source   === 'any' || job.source === filters.source) &&
      jobWithinDateFilter(job.posted_at, filters.date) &&
      job.match_score >= minScore &&
      (!filters.remote || isRemote(job)) &&
      (!filters.q.trim() || matchesQuery(job, filters.q))
    )
    if (filters.sort === 'new') {
      const t = (j) => (j.posted_at ? new Date(j.posted_at).getTime() : 0)
      out.sort((a, b) => t(b) - t(a))
    }
    return out
  }, [jobs, filters])

  useEffect(() => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify({ ...filters, q: '' })) } catch { /* private mode */ }
    setShown(DISPLAY_CAP)
  }, [filters])

  const visibleJobs = filteredJobs.slice(0, shown)
  const filtersActive = filters.q !== '' || filters.remote || filters.location !== 'any' || filters.source !== 'any' || filters.date !== 'any' || filters.score !== 'any'
  const isEmpty = !loading && !refreshing && jobs.length === 0
  const isFilteredEmpty = !loading && !refreshing && jobs.length > 0 && filteredJobs.length === 0

  const setFilter = (key, value) => setFilters(f => ({ ...f, [key]: value }))
  const clearFilters = () => setFilters((f) => ({ ...DEFAULT_FILTERS, sort: f.sort }))

  return (
    <section className={bare ? '' : 'mt-10'} id="job-recommendations">
      {/* Section header */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2.5">
          <div>
            <h2 className="text-base font-semibold text-text-primary leading-tight">
              Jobs matching your skills
            </h2>
            {!loading && !error && (
              <p className="text-xs text-text-muted mt-0.5">
                {total > 0
                  ? filtersActive
                    ? `${filteredJobs.length} of ${total} openings match your filters`
                    : `${total} openings with strong match · ${filters.sort === 'new' ? 'newest first' : 'best match first'}`
                  : 'Fetching fresh listings…'}
                {lastFetched && (
                  <span className="ml-2">
                    · updated {relativeTime(lastFetched.toISOString())}
                  </span>
                )}
              </p>
            )}
          </div>
        </div>

        <button
          onClick={() => fetchJobs(true)}
          disabled={loading || refreshing}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all',
            loading || refreshing
              ? 'border-bg-border text-text-muted cursor-not-allowed'
              : 'border-bg-border text-text-secondary hover:border-text-muted/60 hover:text-brand'
          )}
          title="Refresh job listings"
        >
          <RefreshCw
            size={12}
            className={clsx(refreshing && 'animate-spin')}
          />
          Refresh
        </button>
      </div>

      {/* Filter bar — only worth showing once there's something to filter */}
      {!loading && !error && jobs.length > 0 && (
        <FilterBar
          filters={filters}
          setFilter={setFilter}
          locationOptions={locationOptions}
          sourceOptions={sourceOptions}
          onClear={clearFilters}
          isActive={filtersActive}
        />
      )}

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-xl border border-bad/20 bg-bad/5 text-sm text-bad mb-4">
          <AlertCircle size={16} className="flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Loading skeletons */}
      {(loading || refreshing) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {/* Empty state — no jobs fetched at all */}
      {isEmpty && !error && (
        <div className="rounded-xl border border-dashed border-bg-border">
          <EmptyState
            icon={Briefcase}
            title="No strong matches found yet"
            description="Add more skills to your profile to improve matching, or try refreshing to fetch new listings."
          />
        </div>
      )}

      {/* Empty state — jobs exist, but none pass the current filters */}
      {isFilteredEmpty && !error && (
        <div className="rounded-xl border border-dashed border-bg-border">
          <EmptyState
            icon={Briefcase}
            title="No jobs match your filters"
            description="Try a different search word, or widen the location, time or match filter."
            actionLabel="Clear filters"
            onAction={clearFilters}
          />
        </div>
      )}

      {/* Job cards grid — ONE whole-grid fade on first reveal. Cards are
          plain divs on purpose: per-card stagger replayed on every filter
          change, which read as cards randomly placing themselves. */}
      {!loading && !refreshing && visibleJobs.length > 0 && (
        <motion.div initial="hidden" whileInView="visible" viewport={{ once: true, margin: '-60px' }} variants={fadeInUp}>
          {(filters.sort === 'new' ? [...new Set(visibleJobs.map((j) => dayGroup(j.posted_at)))] : [null]).map((group) => (
            <div key={group || 'all'} className="mb-6">
              {group && <h3 className="eyebrow mb-3">{group}</h3>}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {visibleJobs.filter((j) => !group || dayGroup(j.posted_at) === group).map((job, i) => (
                  <JobCard key={job.url || i} job={job} />
                ))}
              </div>
            </div>
          ))}
          {filteredJobs.length > shown && (
            <div className="text-center">
              <button onClick={() => setShown((n) => n + DISPLAY_CAP)} className="btn-ghost text-sm">
                Show {Math.min(DISPLAY_CAP, filteredJobs.length - shown)} more of {filteredJobs.length - shown}
              </button>
            </div>
          )}
        </motion.div>
      )}
    </section>
  )
}
