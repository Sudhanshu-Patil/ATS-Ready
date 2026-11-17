import { test, expect } from '@playwright/test'

// Phone layout guard: nothing in the signed-in app may be wider than the screen (the app scrolls inside <main>, so the
// page itself never shows a horizontal scrollbar even when content is cut off), and text fields stay at 16px so iOS
// does not zoom the page on focus. Runs on the phone projects only.
const JD = 'We are hiring a backend engineer to build Python and FastAPI services. '.repeat(3)

async function overflow(page) {
  return page.evaluate(() => {
    const scroller = document.querySelector('main#main > div')
    if (!scroller) return ['no scroller']
    const sr = scroller.getBoundingClientRect()
    const bad = []
    for (const el of scroller.querySelectorAll('*')) {
      const r = el.getBoundingClientRect()
      if (!r.width || r.right <= sr.right + 1) continue
      let p = el.parentElement; let held = false
      while (p && p !== scroller) { if (/(auto|scroll)/.test(getComputedStyle(p).overflowX)) { held = true; break } p = p.parentElement }
      if (!held) bad.push(`${el.tagName.toLowerCase()}.${String(el.className.baseVal ?? el.className).split(' ').slice(0, 3).join('.')} right=${Math.round(r.right)} limit=${Math.round(sr.right)}`)
    }
    return [...new Set(bad)].slice(0, 5)
  })
}

test('signed-in screens fit a phone and fields do not trigger iOS zoom', async ({ page }) => {
  test.skip((page.viewportSize()?.width ?? 1280) > 700, 'phone projects only')
  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('Phone Tester')
  await page.getByPlaceholder('you@example.com').fill(`e2e-phone-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`)
  await page.getByPlaceholder('Min. 8 characters').fill('e2e-test-pass-1')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })
  const token = await page.evaluate(async () => {
    const r = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
    return (await r.json()).access_token
  })
  await page.request.post('/api/metabase/personal', { headers: { Authorization: `Bearer ${token}` }, data: { full_name: 'Phone Tester', email: 'p@atsready-tests.dev' } })
  const job = await (await page.request.post('/api/applications', { headers: { Authorization: `Bearer ${token}` },
    data: { jd_text: JD, company: 'Acme', role: 'Backend Engineer' } })).json()

  const problems = []
  for (const path of ['/dashboard', '/jobs', `/jobs/${job.id}`, '/generate', `/generate?job=${job.id}`, '/cover-letter', '/interview-prep',
                      '/assistant', '/metabase', '/settings?section=account', '/settings?section=billing']) {
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
    for (const bad of await overflow(page)) problems.push(`${path}: ${bad}`)
    const small = await page.evaluate(() => [...document.querySelectorAll('input:not([type=checkbox]):not([type=radio]):not([type=file]):not([type=range]), select, textarea')]
      .filter((el) => el.getBoundingClientRect().width && parseFloat(getComputedStyle(el).fontSize) < 16).length)
    if (small) problems.push(`${path}: ${small} field(s) under 16px`)
  }
  expect(problems).toEqual([])
})
