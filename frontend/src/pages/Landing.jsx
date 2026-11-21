import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuthStore } from '../store/auth'
import LandingNav from '../components/landing/LandingNav'
import LandingPricing from '../components/landing/LandingPricing'
import ResumePreview from '../components/landing/ResumePreview'
import { Wordmark } from '../components/Brand'
import { useSiteConfig } from '../lib/siteConfig'

// Public landing page at "/". Sits outside the app shell. Theme-aware like the rest of the app.

const STEPS = [
  { title: 'Fill in your profile once', body: 'Skills, experience, projects and education. Or upload the resume you already have and we read it for you.' },
  { title: 'Paste a job', body: 'Paste the posting or a link to it. It is saved as a job, so you never paste it again for the cover letter, the answers or the interview prep.' },
  { title: 'Take what you need', body: 'A one-page resume as Word and PDF with an ATS score, a cover letter, answers to the form questions, interview prep and a message to ask for a referral.' },
]

const DETAILS = [
  { term: 'A score you can check', body: 'Scored 0 to 100 by fixed rules: required skills, keywords, action verbs and structure. The same resume always gets the same score.' },
  { term: 'Skills you confirm', body: 'When a posting asks for something your profile does not show, we list it. You tick the ones you really have. We never add a skill for you.' },
  { term: 'Nothing invented', body: 'After the model writes, a check removes any number, tool, employer or job title that is not in your profile.' },
  { term: 'Answers for the form', body: 'Paste the questions, with or without the job. Notice period and salary are asked once and remembered, never guessed. Sensitive questions are left for you.' },
  { term: 'Cover letters that fit', body: 'Set the word or character limit the form allows. The letter is written to fit and never goes over. Edit it, copy it or download it.' },
  { term: 'Interview prep', body: 'Likely questions for this role with model answers drawn from your own experience.' },
  { term: 'Every job tracked', body: 'Each job keeps its dates and what you made for it. A week after you apply, we remind you to follow up.' },
  { term: 'Your data stays yours', body: 'Download everything or delete your account from Settings, any time.' },
]

const fade = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] } }

export default function Landing() {
  const { accessToken } = useAuthStore()
  const primaryTo = accessToken ? '/dashboard' : '/register'
  const site = useSiteConfig()

  return (
    <div className="min-h-[100dvh] bg-bg text-text-primary">
      <LandingNav />

      <main>
        {/* Hero: copy on the left, a real resume on the right */}
        <section className="max-w-6xl mx-auto px-6 pt-16 pb-28 sm:pt-24 grid lg:grid-cols-12 gap-x-12 gap-y-20 items-center">
          <motion.div {...fade} className="lg:col-span-6">
            <h1 className="font-display text-[40px] sm:text-[56px] lg:text-[64px] leading-[1.04] font-medium tracking-[-0.03em]">
              Paste a job posting. Get the resume, cover letter and form answers.
            </h1>
            <p className="mt-6 text-lg leading-7 text-text-secondary max-w-[34rem]">
              ATS-Ready writes a one-page resume from your real experience, scores it against the posting, and prepares the
              application answers and interview questions for the same job. Nothing is invented.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-x-6 gap-y-3">
              <Link to={primaryTo} className="btn-primary text-base !px-6 !py-3">{accessToken ? 'Open dashboard' : 'Start your first job free'}</Link>
              <a href="#pricing" className="text-sm text-text-secondary hover:text-text-primary underline underline-offset-4 decoration-bg-border">See pricing</a>
            </div>
            <p className="mt-4 text-sm text-text-muted">The first job is free. After that it is ₹10 a job.</p>
          </motion.div>

          <motion.div {...fade} transition={{ ...fade.transition, delay: 0.08 }} className="lg:col-span-6 lg:pl-6 pb-10">
            <ResumePreview />
          </motion.div>
        </section>

        {/* How it works: an ordered list, not three cards */}
        <section id="how-it-works" className="border-t border-bg-border">
          <div className="max-w-6xl mx-auto px-6 py-24 grid lg:grid-cols-12 gap-x-12 gap-y-10">
            <h2 className="lg:col-span-4 font-display text-4xl font-medium tracking-[-0.02em] leading-tight">How it works</h2>
            <ol className="lg:col-span-8 divide-y divide-bg-border border-y border-bg-border">
              {STEPS.map((s, i) => (
                <li key={s.title} className="grid grid-cols-[3rem_1fr] sm:grid-cols-[4rem_1fr] gap-x-4 py-7">
                  <span className="font-display text-3xl text-text-muted figure leading-none pt-0.5">{i + 1}</span>
                  <div>
                    <h3 className="text-lg font-medium">{s.title}</h3>
                    <p className="mt-1.5 text-text-secondary max-w-xl">{s.body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* What you get: a ruled list */}
        <section id="features" className="border-t border-bg-border bg-bg-card">
          <div className="max-w-6xl mx-auto px-6 py-24 grid lg:grid-cols-12 gap-x-12 gap-y-10">
            <div className="lg:col-span-4">
              <h2 className="font-display text-4xl font-medium tracking-[-0.02em] leading-tight">What you get for each job</h2>
              <p className="mt-4 text-text-secondary max-w-xs">One credit covers all of it, within a few limits per job.</p>
            </div>
            <dl className="lg:col-span-8 grid sm:grid-cols-2 gap-x-10 gap-y-9">
              {DETAILS.map((d) => (
                <div key={d.term} className="border-t border-text-primary/70 pt-4">
                  <dt className="font-medium">{d.term}</dt>
                  <dd className="mt-1.5 text-sm leading-6 text-text-secondary">{d.body}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <LandingPricing />
      </main>

      <footer className="border-t border-bg-border">
        <div className="max-w-6xl mx-auto px-6 py-10 flex flex-wrap items-start justify-between gap-x-10 gap-y-6">
          <div>
            <Wordmark />
            <p className="mt-3 text-sm text-text-muted max-w-xs">Resume, cover letter, form answers and interview prep for every job you apply to.</p>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-text-secondary">
            <a href="#pricing" className="hover:text-text-primary">Pricing</a>
            <Link to="/terms" className="hover:text-text-primary">Terms</Link>
            <Link to="/privacy" className="hover:text-text-primary">Privacy</Link>
            <Link to="/refunds" className="hover:text-text-primary">Refunds and cancellation</Link>
            {site.contact_email && <a href={`mailto:${site.contact_email}`} className="hover:text-text-primary">{site.contact_email}</a>}
            {site.contact_phone && <span>{site.contact_phone}</span>}
          </nav>
          <p className="basis-full text-xs text-text-muted">
            © {new Date().getFullYear()} {site.business_name || 'ATS-Ready'}. Prices are in Indian rupees, taxes included.
          </p>
        </div>
      </footer>
    </div>
  )
}
