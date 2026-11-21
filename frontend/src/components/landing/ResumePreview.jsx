// The one rich moment on the landing page: a real one-page resume, set in code, with the score and the skills a
// posting asked for that this profile does not show. The paper stays light in both themes because it is a page.
const SKILLS = ['Python', 'FastAPI', 'PostgreSQL', 'Redis', 'Docker', 'AWS']

export default function ResumePreview() {
  return (
    <figure className="relative mx-auto w-full max-w-[460px] lg:max-w-none pb-48 sm:pb-44" aria-label="Example of a generated one-page resume with its ATS score">
      <div className="bg-[#fffdf9] text-[#1f1b16] rounded-md border border-[#e4ddd0] shadow-[0_1px_2px_rgba(31,27,22,0.06),0_18px_40px_-12px_rgba(31,27,22,0.18)] px-8 py-9 sm:px-10 sm:py-10 select-none"
           style={{ fontFamily: "'Instrument Sans Variable', system-ui, sans-serif" }}>
        <div className="flex items-baseline justify-between gap-4 border-b border-[#e4ddd0] pb-3">
          <p className="text-[22px] leading-none font-display" style={{ fontFamily: "'Newsreader Variable', Georgia, serif", fontWeight: 500 }}>Meera Nair</p>
          <p className="text-[11px] text-[#6b6256]">Pune · meera.nair@mail.example</p>
        </div>
        <p className="mt-4 text-[12px] leading-[1.55] text-[#3d362d]">
          Backend engineer with four years building payment and ledger services in Python. Cut reconciliation time for a
          fintech team from 6 hours to 40 minutes.
        </p>

        <p className="mt-5 text-[10.5px] font-semibold tracking-wide text-[#6b6256]">Experience</p>
        <div className="mt-1.5 text-[12px] leading-[1.5]">
          <div className="flex justify-between gap-3"><span className="font-semibold">Backend engineer, Razorlane Payments</span><span className="text-[#6b6256] whitespace-nowrap">2022 to now</span></div>
          <ul className="mt-1 space-y-1 pl-4 list-disc text-[#3d362d] marker:text-[#9b9285]">
            <li>Built the settlement service in <mark className="bg-[#f6e0d3] text-inherit px-0.5 rounded-[2px]">FastAPI</mark> and <mark className="bg-[#f6e0d3] text-inherit px-0.5 rounded-[2px]">PostgreSQL</mark>, handling 1.8M transactions a day</li>
            <li>Moved batch jobs onto a <mark className="bg-[#f6e0d3] text-inherit px-0.5 rounded-[2px]">Redis</mark> queue; failed runs fell from 3.1% to 0.4%</li>
            <li>Wrote the on-call runbook the team still uses</li>
          </ul>
        </div>
        <div className="mt-3 text-[12px] leading-[1.5]">
          <div className="flex justify-between gap-3"><span className="font-semibold">Software engineer, Kiln Labs</span><span className="text-[#6b6256] whitespace-nowrap">2020 to 2022</span></div>
          <ul className="mt-1 space-y-1 pl-4 list-disc text-[#3d362d] marker:text-[#9b9285]">
            <li>Shipped the invoicing API used by 140 small businesses</li>
          </ul>
        </div>

        <p className="mt-5 text-[10.5px] font-semibold tracking-wide text-[#6b6256]">Skills</p>
        <p className="mt-1.5 text-[12px] leading-[1.6] text-[#3d362d]">
          {SKILLS.map((s, i) => (
            <span key={s}>{i ? ', ' : ''}<span className={['FastAPI', 'PostgreSQL', 'Redis'].includes(s) ? 'bg-[#f6e0d3] px-0.5 rounded-[2px]' : ''}>{s}</span></span>
          ))}
        </p>
        <p className="mt-5 text-[10.5px] font-semibold tracking-wide text-[#6b6256]">Education</p>
        <p className="mt-1.5 text-[12px] text-[#3d362d]">B.Tech, Computer Engineering, College of Engineering Pune, 2020</p>
      </div>

      {/* The check, laid over the corner of the page */}
      <figcaption className="absolute bottom-0 left-0 sm:-left-6 w-[300px] max-w-full bg-bg-card border border-bg-border rounded-xl p-4 shadow-[0_1px_2px_rgba(31,27,22,0.06),0_14px_32px_-12px_rgba(31,27,22,0.22)]">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium text-text-primary pr-3">ATS score for this posting</span>
          <span className="figure font-mono text-2xl text-text-primary whitespace-nowrap">87<span className="text-sm text-text-muted"> / 100</span></span>
        </div>
        <dl className="mt-3 space-y-1.5 text-xs">
          {[['Required skills', 92], ['Keywords', 84], ['Action verbs', 80], ['Structure', 90]].map(([k, v]) => (
            <div key={k} className="flex items-center gap-3">
              <dt className="w-28 text-text-secondary">{k}</dt>
              <dd className="flex-1 h-1 rounded-sm bg-bg-hover overflow-hidden"><div className="h-full bg-text-primary/70" style={{ width: `${v}%` }} /></dd>
              <dd className="figure font-mono text-text-secondary w-6 text-right">{v}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 pt-3 border-t border-bg-border text-xs text-text-secondary">
          The posting also asks for <strong className="font-medium text-text-primary">Kafka</strong> and <strong className="font-medium text-text-primary">Terraform</strong>.
          Not on your profile, so we left them out. Add them if you have used them.
        </p>
      </figcaption>
    </figure>
  )
}
