import { Link } from 'react-router-dom'
import { useSiteConfig } from '../lib/siteConfig'

function Page({ title, children }) {
  return (
    <main className="max-w-3xl mx-auto p-6 sm:p-10 text-text-secondary leading-relaxed space-y-4">
      <Link to="/" className="text-brand text-sm">← ATS-Ready</Link>
      <h1 className="font-display text-3xl font-medium text-text-primary">{title}</h1>
      <p className="text-xs">Last updated: 18 November 2026.</p>
      {children}
      <Contact />
    </main>
  )
}
function Contact() {
  const site = useSiteConfig()
  return (
    <>
      <H>Contact</H>
      <p>
        {site.business_name ? `${site.business_name}. ` : ''}
        {site.contact_email ? <>Write to <a className="text-brand underline" href={`mailto:${site.contact_email}`}>{site.contact_email}</a></> : 'Use the contact details shown on the home page'}
        {site.contact_phone ? ` or call ${site.contact_phone}` : ''}. We answer within 2 working days.
      </p>
    </>
  )
}

const H = ({ children }) => <h2 className="text-lg font-semibold text-text-primary pt-2">{children}</h2>

export function Privacy() {
  return (
    <Page title="Privacy policy">
      <H>What we store</H>
      <p>Your account (email, name, password hash or Google ID), the career details you add (skills, experience,
        projects, education, contact details), the job descriptions you submit, the resumes, cover letters, interview
        prep, application-form answers and referral messages we generate for you, the jobs you track (company, role,
        dates, notes), what the assistant learns about your answering style, and your credit balance and payment
        records (provider, amount, order and payment ids; never your card or UPI details).</p>
      <H>Who processes it</H>
      <ul className="list-disc pl-6 space-y-1">
        <li>Groq: receives your profile and job description text to generate documents.</li>
        <li>Razorpay (rupees) and PayPal (dollars): handle payments. We never see your card details.</li>
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
      <p>Credits are one-time purchases through Razorpay or PayPal at the price shown at checkout. There are no subscriptions and nothing renews. Credits do not expire and are not refunded: unused credits stay on your account for later jobs. A credit is returned automatically when the first generation for a job fails, and payment mistakes (a double charge, or no credits received) are put right; see the refunds page. Free starter and invite credits have no cash value. One job credit covers the job described by one job description, within the per-job limits shown in the app.</p>
      <H>Delivery</H>
      <p>ATS-Ready is a digital service. Credits are added to your account as soon as the payment is confirmed, and
        everything you generate is available in the app straight away.</p>
      <H>No warranty</H>
      <p>The service is provided as is, and we do not guarantee interviews, offers or specific ATS scores.</p>
    </Page>
  )
}

export function Refunds() {
  return (
    <Page title="Refunds and cancellation">
      <H>No subscriptions</H>
      <p>There is nothing to cancel. ATS-Ready sells credits as one-time purchases. No plan renews and nothing is charged again.</p>
      <H>Credits stay with your account</H>
      <p>Credits you have bought do not expire and are not refunded. Whatever you have not used stays on your account until
        you use it, so you can spend it on later jobs whenever you like.</p>
      <H>When a credit comes back</H>
      <p>If the first generation for a job fails, the credit you spent on it is returned to your balance automatically, and so
        is any use of that job's limits that did not complete.</p>
      <H>Payment mistakes</H>
      <p>If you were charged twice, or charged and did not receive your credits, we put it right: we add the missing credits
        or refund the extra payment. Credits you have already spent on a job are final, because the generation has been
        delivered. Free starter and invite credits have no cash value.</p>
      <H>How to ask and when you are paid</H>
      <p>Write to us using the contact details below with the email on your account and the payment id from your receipt.
        Approved refunds for a payment mistake go back to the original payment method (UPI, card, netbanking or PayPal) and
        usually reach you within 5 to 7 working days, depending on your bank.</p>
    </Page>
  )
}
