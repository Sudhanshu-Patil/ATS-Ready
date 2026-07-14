import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Plus, Trash2, User, Briefcase, Code, FolderGit2, Upload } from 'lucide-react'
import { metabaseAPI } from '../api/client'
import { fadeInUp, staggerContainer } from '../lib/motion'
import Tabs from '../components/Tabs'
import EmptyState from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import Spinner from '../components/Spinner'
import toast from 'react-hot-toast'
import clsx from 'clsx'

const TABS = [
  { id: 'personal',   label: 'Personal',   icon: User },
  { id: 'skills',     label: 'Skills',     icon: Code },
  { id: 'experience', label: 'Experience', icon: Briefcase },
  { id: 'projects',   label: 'Projects',   icon: FolderGit2 },
]

// ── Import from an existing resume ────────────────────────────────────────────
function ImportResumeCard({ onImported }) {
  const inputRef = useRef(null)
  const [importing, setImporting] = useState(false)

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-selecting the same file
    if (!file) return
    if (!/\.(pdf|docx)$/i.test(file.name)) {
      toast.error('Upload a .pdf or .docx file')
      return
    }
    setImporting(true)
    try {
      const { data } = await metabaseAPI.importResume(file)
      const parts = []
      if (data.skills)     parts.push(`${data.skills} skills`)
      if (data.experience) parts.push(`${data.experience} roles`)
      if (data.projects)   parts.push(`${data.projects} projects`)
      if (data.education)  parts.push(`${data.education} education`)
      if (data.personal_updated) parts.push('personal info')
      toast.success(parts.length
        ? `Imported: ${parts.join(', ')}`
        : 'Nothing new to import — your profile already has it all')
      onImported()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import failed — please try again')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="card-glass !p-4 mb-6 flex items-center justify-between gap-4 flex-wrap">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-brand-muted flex items-center justify-center flex-shrink-0">
          <Upload size={16} className="text-brand" />
        </div>
        <div>
          <p className="text-sm font-semibold text-text-primary">Already have a resume?</p>
          <p className="text-xs text-text-secondary">
            Upload it (.pdf / .docx) — the AI fills your profile automatically. Existing entries are never overwritten.
          </p>
        </div>
      </div>
      <input ref={inputRef} type="file" accept=".pdf,.docx" className="hidden" onChange={handleFile} />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={importing}
        className="btn-primary text-sm flex items-center gap-2 whitespace-nowrap"
      >
        {importing ? <Spinner size="sm" color="white" /> : <Upload size={14} />}
        {importing ? 'Parsing your resume…' : 'Import resume'}
      </button>
    </div>
  )
}

export default function Metabase() {
  const [tab, setTab] = useState('personal')
  // Bumping this remounts the active tab so it refetches after an import
  const [reloadKey, setReloadKey] = useState(0)

  return (
    <div className="p-8 max-w-6xl mx-auto">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-9 h-9 rounded-xl bg-brand-muted flex items-center justify-center">
            <User size={18} className="text-brand" />
          </div>
          <h1 className="font-display text-2xl font-bold text-text-primary">Metabase</h1>
        </div>
        <p className="text-text-secondary">Your personal knowledge base — the AI uses this to tailor every resume.</p>
      </motion.div>

      <motion.div initial="hidden" animate="visible" variants={fadeInUp}>
        <ImportResumeCard onImported={() => setReloadKey(k => k + 1)} />
        <Tabs tabs={TABS} active={tab} onChange={setTab} className="mb-6" />
      </motion.div>

      {tab === 'personal'   && <PersonalTab   key={`p-${reloadKey}`} />}
      {tab === 'skills'     && <SkillsTab     key={`s-${reloadKey}`} />}
      {tab === 'experience' && <ExperienceTab key={`e-${reloadKey}`} />}
      {tab === 'projects'   && <ProjectsTab   key={`j-${reloadKey}`} />}
    </div>
  )
}

// ── Personal ──────────────────────────────────────────────────────────────────

function PersonalTab() {
  const [form, setForm]   = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving]   = useState(false)

  useEffect(() => {
    metabaseAPI.getPersonal()
      .then(r => setForm(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      await metabaseAPI.savePersonal(form)
      toast.success('Personal info saved')
    } catch { toast.error('Save failed') }
    finally { setSaving(false) }
  }

  if (loading) return <Skeleton className="h-64 rounded-xl" />

  const field = (key, label, type = 'text', placeholder = '') => (
    <div key={key}>
      <label className="block text-sm font-medium text-text-secondary mb-1.5">{label}</label>
      {key === 'professional_summary' ? (
        <textarea
          className="input min-h-24 resize-y text-sm"
          placeholder={placeholder}
          value={form[key] || ''}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        />
      ) : (
        <input
          type={type}
          className="input text-sm"
          placeholder={placeholder}
          value={form[key] || ''}
          onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        />
      )}
    </div>
  )

  return (
    <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card space-y-4">
      <div className="grid grid-cols-2 gap-4">
        {field('full_name', 'Full name', 'text', 'Priya Sharma')}
        {field('email',     'Email',     'email', 'you@example.com')}
        {field('phone',     'Phone',     'tel',   '+91-98765-43210')}
        {field('location',  'Location',  'text',  'Bangalore, India')}
        {field('linkedin',  'LinkedIn',  'url',   'https://linkedin.com/in/...')}
        {field('github',    'GitHub',    'url',   'https://github.com/...')}
      </div>
      {field('portfolio',            'Portfolio URL',          'url',  'https://...')}
      {field('professional_summary', 'Professional summary',  'text', 'Senior engineer with...')}

      <div className="flex justify-end pt-2">
        <button onClick={save} disabled={saving} className="btn-primary">
          {saving ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </motion.div>
  )
}

// ── Skills ────────────────────────────────────────────────────────────────────

function SkillsTab() {
  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ name: '', category: 'Programming Languages', proficiency: 'Intermediate', years_experience: 1 })

  const load = () => {
    metabaseAPI.getSkills()
      .then(r => setSkills(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const add = async () => {
    if (!form.name.trim()) { toast.error('Skill name required'); return }
    try {
      await metabaseAPI.addSkill(form)
      toast.success(`${form.name} added`)
      setForm(f => ({ ...f, name: '' }))
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to add skill')
    }
  }

  const del = async (id, name) => {
    try {
      await metabaseAPI.deleteSkill(id)
      toast.success(`${name} removed`)
      setSkills(s => s.filter(x => x.id !== id))
    } catch { toast.error('Delete failed') }
  }

  const profColors = { Expert: 'text-score', Advanced: 'text-brand', Intermediate: 'text-yellow-400', Beginner: 'text-text-muted' }

  const grouped = skills.reduce((acc, s) => {
    ;(acc[s.category] = acc[s.category] || []).push(s)
    return acc
  }, {})

  return (
    <div className="space-y-5">
      {/* Add form */}
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
        <p className="text-sm font-semibold text-text-primary mb-3">Add skill</p>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <input className="input text-sm" placeholder="Skill name (e.g. Python)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input className="input text-sm" placeholder="Category" value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))} />
          <select className="input text-sm" value={form.proficiency} onChange={e => setForm(f => ({ ...f, proficiency: e.target.value }))}>
            {['Beginner', 'Intermediate', 'Advanced', 'Expert'].map(p => <option key={p}>{p}</option>)}
          </select>
          <input type="number" className="input text-sm" placeholder="Years" min="0" max="30" value={form.years_experience} onChange={e => setForm(f => ({ ...f, years_experience: parseFloat(e.target.value) }))} />
        </div>
        <button onClick={add} className="btn-primary text-sm flex items-center gap-2">
          <Plus size={14} /> Add skill
        </button>
      </motion.div>

      {/* Skills list — stagger only the category cards; nested per-chip
          stagger would multiply trickle-time with skill count. */}
      {loading ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : skills.length === 0 ? (
        <div className="card">
          <EmptyState icon={Code} title="No skills added yet" description="Add your first skill above — the AI uses these to tailor every resume." />
        </div>
      ) : (
        <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-5">
          {Object.entries(grouped).map(([cat, items]) => (
            <motion.div key={cat} variants={fadeInUp} className="card">
              <p className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-3">{cat}</p>
              <div className="flex flex-wrap gap-2">
                {items.map(s => (
                  <div key={s.id} className="flex items-center gap-2 bg-bg-hover border border-bg-border rounded-lg px-3 py-1.5 group">
                    <span className="text-sm text-text-primary">{s.name}</span>
                    <span className={clsx('text-xs', profColors[s.proficiency] || 'text-text-muted')}>{s.proficiency}</span>
                    <button onClick={() => del(s.id, s.name)} className="text-text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}

// ── Experience ────────────────────────────────────────────────────────────────

function ExperienceTab() {
  const [exps, setExps]     = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm]     = useState({ company: '', role: '', start_date: '', end_date: '', is_current: false, location: '' })

  const load = () => {
    metabaseAPI.getExperience()
      .then(r => setExps(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const add = async () => {
    if (!form.company || !form.role || !form.start_date) {
      toast.error('Company, role, and start date are required')
      return
    }
    try {
      await metabaseAPI.addExperience({ ...form, bullets: [] })
      toast.success('Experience added')
      setForm({ company: '', role: '', start_date: '', end_date: '', is_current: false, location: '' })
      load()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  const del = async (id) => {
    if (!confirm('Delete this experience?')) return
    try { await metabaseAPI.deleteExperience(id); toast.success('Deleted'); load() }
    catch { toast.error('Delete failed') }
  }

  return (
    <div className="space-y-5">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
        <p className="text-sm font-semibold text-text-primary mb-3">Add experience</p>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <input className="input text-sm" placeholder="Company" value={form.company} onChange={e => setForm(f => ({ ...f, company: e.target.value }))} />
          <input className="input text-sm" placeholder="Role" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))} />
          <input className="input text-sm" placeholder="Location" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
          <input className="input text-sm" placeholder="Start date (e.g. Jan 2022)" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} />
          <input className="input text-sm" placeholder="End date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} disabled={form.is_current} />
          <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
            <input type="checkbox" className="rounded" checked={form.is_current} onChange={e => setForm(f => ({ ...f, is_current: e.target.checked, end_date: '' }))} />
            Current role
          </label>
        </div>
        <button onClick={add} className="btn-primary text-sm flex items-center gap-2">
          <Plus size={14} /> Add experience
        </button>
      </motion.div>

      {loading ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : exps.length === 0 ? (
        <div className="card">
          <EmptyState icon={Briefcase} title="No experience added yet" />
        </div>
      ) : (
        <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-3">
          {exps.map(e => (
            <motion.div key={e.id} variants={fadeInUp} className="card flex items-start justify-between">
              <div>
                <p className="font-semibold text-text-primary">{e.role}</p>
                <p className="text-sm text-text-secondary">{e.company}</p>
                <p className="text-xs text-text-muted mt-1">{e.start_date} — {e.is_current ? 'Present' : e.end_date || '—'}</p>
              </div>
              <button onClick={() => del(e.id)} className="text-text-muted hover:text-red-400 transition-colors p-1">
                <Trash2 size={15} />
              </button>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}

// ── Projects ──────────────────────────────────────────────────────────────────

function ProjectsTab() {
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [form, setForm] = useState({ title: '', description: '', tech_stack: '', github_url: '', is_featured: true })

  const load = () => {
    metabaseAPI.getProjects()
      .then(r => setProjects(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const add = async () => {
    if (!form.title || !form.description) { toast.error('Title and description required'); return }
    try {
      await metabaseAPI.addProject({
        ...form,
        tech_stack: form.tech_stack.split(',').map(s => s.trim()).filter(Boolean),
        bullets: [],
      })
      toast.success('Project added')
      setForm({ title: '', description: '', tech_stack: '', github_url: '', is_featured: true })
      load()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  const del = async (id) => {
    if (!confirm('Delete this project?')) return
    try { await metabaseAPI.deleteProject(id); toast.success('Deleted'); load() }
    catch { toast.error('Delete failed') }
  }

  return (
    <div className="space-y-5">
      <motion.div initial="hidden" animate="visible" variants={fadeInUp} className="card">
        <p className="text-sm font-semibold text-text-primary mb-3">Add project</p>
        <div className="space-y-3">
          <input className="input text-sm" placeholder="Project title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <textarea className="input text-sm min-h-20 resize-y" placeholder="Description" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <input className="input text-sm" placeholder="Tech stack (comma separated: Python, FastAPI, Redis)" value={form.tech_stack} onChange={e => setForm(f => ({ ...f, tech_stack: e.target.value }))} />
          <input className="input text-sm" placeholder="GitHub URL (optional)" value={form.github_url} onChange={e => setForm(f => ({ ...f, github_url: e.target.value }))} />
        </div>
        <button onClick={add} className="btn-primary text-sm flex items-center gap-2 mt-3">
          <Plus size={14} /> Add project
        </button>
      </motion.div>

      {loading ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : projects.length === 0 ? (
        <div className="card">
          <EmptyState icon={FolderGit2} title="No projects added yet" />
        </div>
      ) : (
        <motion.div initial="hidden" animate="visible" variants={staggerContainer} className="space-y-3">
          {projects.map(p => (
            <motion.div key={p.id} variants={fadeInUp} className="card flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-text-primary">{p.title}</p>
                {p.tech_stack?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {p.tech_stack.map(t => (
                      <span key={t} className="badge bg-brand-muted text-brand">{t}</span>
                    ))}
                  </div>
                )}
              </div>
              <button onClick={() => del(p.id)} className="text-text-muted hover:text-red-400 transition-colors p-1 flex-shrink-0">
                <Trash2 size={15} />
              </button>
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  )
}
