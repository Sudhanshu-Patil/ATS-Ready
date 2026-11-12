import { Link } from 'react-router-dom'

function Page({ title, children }) {
  return (
    <main className="max-w-3xl mx-auto p-6 sm:p-10 text-text-secondary leading-relaxed space-y-4">
      <Link to="/" className="text-brand text-sm">← ATS-Ready</Link>
      <h1 className="font-display text-3xl font-bold text-text-primary">{title}</h1>
      <p className="text-xs">Last updated: 12 November 2026. Draft text: review before relying on it.</p>
      {children}
    </main>
  )
}
const H = ({ children }) => <h2 className="text-lg font-semibold text-text-primary pt-2">{children}</h2>

export function Privacy() {
  return (
    <Page title="Privacy policy">
      <H>What we store</H>
      <p>Your account (email, name, password hash or Google ID), the career details you add (skills, experience,
        projects, education, contact details), the job descriptions you submit, and the resumes, cover letters and
        interview prep we generate for you.</p>
      <H>Who processes it</H>
      <ul className="list-disc pl-6 space-y-1">
        <li>Groq: receives your profile and job description text to generate documents.</li>
        <li>PayPal: handles payments. We never see your card details.</li>
        <li>Google: only if you choose "Continue with Google".</li>
        <li>Apify and public job boards: receive search terms (roles, skills, location), not your identity.</li>
        <li>Sentry: error reports, without personal data, when enabled.</li>
        <li>Hosting: Render (app), Neon (database), Upstash (cache), Cloudflare R2 (files).</li>
      </ul>
      <H>Cookies</H>
      <p>Only strictly necessary cookies that keep you signed in. No advertising or tracking cookies.</p>
      <H>Your rights</H>
      <p>In Settings → Security you can download all your data and permanently delete your account, which removes
        your profile, documents and stored files. You can also sign out of every device.</p>
      <H>Retention</H>
      <p>We keep data until you delete it. Deleted data is removed from the live database immediately; backups
        expire on the provider's schedule.</p>
      <H>Contact</H>
      <p>Questions or requests: use the contact address listed on the project page.</p>
    </Page>
  )
}

export function Terms() {
  return (
    <Page title="Terms of service">
      <H>The service</H>
      <p>ATS-Ready uses AI to tailor resumes and write cover letters and interview prep. Output can contain mistakes:
        check every document before you send it. You are responsible for what you submit to employers.</p>
      <H>Your content</H>
      <p>You keep ownership of what you upload and generate. You give us permission to process it to provide the service.</p>
      <H>Acceptable use</H>
      <p>Do not abuse the service, attempt to bypass limits, or submit content you have no right to use.</p>
      <H>Payments</H>
      <p>Paid plans are billed through PayPal for the period shown at checkout and do not renew automatically.
        This project currently uses PayPal's sandbox for demonstration.</p>
      <H>No warranty</H>
      <p>The service is provided as is, and we do not guarantee interviews, offers or specific ATS scores.</p>
    </Page>
  )
}
