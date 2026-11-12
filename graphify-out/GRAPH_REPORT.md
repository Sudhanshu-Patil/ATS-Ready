# Graph Report - ATS-Ready  (2026-11-12)

## Corpus Check
- 196 files · ~153,040 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 18 file(s) not represented in the graph (top: (none) 9, .ini 2, .css 2)

## Summary
- 1428 nodes · 3531 edges · 92 communities (77 shown, 15 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 220 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 84
- Community 85

## God Nodes (most connected - your core abstractions)
1. `User` - 98 edges
2. `unique_email()` - 48 edges
3. `Spinner()` - 32 edges
4. `App()` - 29 edges
5. `JobApplication` - 28 edges
6. `useAuthStore` - 28 edges
7. `register()` - 28 edges
8. `react` - 27 edges
9. `bearer()` - 27 edges
10. `react-router-dom` - 26 edges

## Surprising Connections (you probably didn't know these)
- `agent()` --uses--> `AIAgent`  [INFERRED]
  tests/test_prompts.py → app/agents/ai_agent.py
- `test_every_llm_call_carries_the_injection_guard()` --calls--> `AIAgent`  [EXTRACTED]
  tests/test_prompts.py → app/agents/ai_agent.py
- `generate()` --calls--> `init_db()`  [INFERRED]
  cli.py → app/db/database.py
- `history()` --calls--> `init_db()`  [INFERRED]
  cli.py → app/db/database.py
- `_cleanup_test_users()` --uses--> `User`  [INFERRED]
  tests/conftest.py → app/db/models.py

## Import Cycles
- None detected.

## Communities (92 total, 15 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (40): export_user_data(), _plain(), Account data export and permanent deletion (privacy: portability + erasure)., _row(), _add_hyperlink(), _add_plain_run(), _add_rule(), Path (+32 more)

### Community 1 - "Community 1"
Cohesion: 0.07
Nodes (41): estimate_tokens(), Rough, provider-agnostic (~4 chars per token for English)., _BadOutput, LLMClient, LLMContextTooLarge, LLMUnavailable, Exception, app/services/llm_client.py ────────────────────────── One place that talks to… (+33 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (46): _apify_crawl_html(), _apify_run_allowed(), _dedupe(), _fetch_all_jobs(), _fetch_apify_indeed(), _fetch_apify_linkedin(), _fetch_apify_naukri(), _fetch_arbeitnow() (+38 more)

### Community 3 - "Community 3"
Cohesion: 0.10
Nodes (45): add_experience(), add_project(), add_skill(), delete_experience(), delete_project(), delete_skill(), download_resume(), get_experience() (+37 more)

### Community 4 - "Community 4"
Cohesion: 0.11
Nodes (40): ensure_profile(), _check_jd(), Config, CoverLetterRequest, delete_cover_letter(), delete_interview_prep(), _enqueue_or_fail(), generate_cover_letter() (+32 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (19): BillingService, Any, AsyncClient, Capture an approved order. Returns the PayPal order JSON or None., PayPal REST calls. All methods are graceful no-ops when disabled., Returns {"order_id", "approve_url"}, or None if disabled / failed., CacheService, Any (+11 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (27): import_resume(), Import an existing resume: extract text (PDF/DOCX) → AI-parse into a structured…, Base, init_db(), Create all tables. Only used in development / tests., Education, ExperienceBullet, PersonalInfo (+19 more)

### Community 7 - "Community 7"
Cohesion: 0.13
Nodes (29): app/api/activity_routes.py ────────────────────────── One view of everything a…, Admin analytics. Access is by email allowlist (ADMIN_EMAILS), verified-only., app/api/billing_routes.py ────────────────────────── PayPal billing endpoints.…, get_current_user(), get_current_user_optional(), AsyncSession, Like get_current_user but returns None instead of raising 401. Use for…, Resolve the current authenticated user from a JWT. Checks Authorization header… (+21 more)

### Community 8 - "Community 8"
Cohesion: 0.11
Nodes (27): Admin, App(), CoverLetter, Dashboard, ForgotPassword, Generator, InterviewPrep, Landing (+19 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (32): _compact_json(), compact_profile(), bullet_score(), proj_score(), size(), trim_bullets(), ground_skills(), _keyword_norms() (+24 more)

### Community 10 - "Community 10"
Cohesion: 0.18
Nodes (22): authAPI, contentAPI, metabaseAPI, GoogleButton(), loadGoogleScript(), renderButton(), ThemeToggle(), ForgotPassword() (+14 more)

### Community 11 - "Community 11"
Cohesion: 0.14
Nodes (27): UsageEvent, add_usage(), Called by LLMClient after every successful completion., Store one event; never raises (accounting must not fail a finished job)., record_usage(), start_tally(), wrapper(), Session revocation, account export and deletion. (+19 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (26): jobsAPI, resumeAPI, FILTERS, formatDate(), ResumeHistory(), STATUS_CONFIG, scoreColor(), scoreColorClass() (+18 more)

### Community 13 - "Community 13"
Cohesion: 0.07
Nodes (18): devDependencies, @axe-core/playwright, @playwright/test, name, private, scripts, test, type (+10 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (26): confirmDialog(), EmptyState(), Skeleton(), SkeletonRow(), SkeletonText(), Tabs(), CoverLetter(), ExpandedCoverLetter() (+18 more)

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (5): app/services/billing_service.py ──────────────────────────────── PayPal billing…, httpx, sqlalchemy_dialects, sqlalchemy_dialects_postgresql, typing

### Community 16 - "Community 16"
Cohesion: 0.10
Nodes (25): build_context(), friendly_error(), ProfileIncomplete, AsyncSession, Exception, UUID, User-facing failure text (stored on the row, shown in the queue panel)., Returns (profile, parsed_jd, tailored, job_app). Profile is shrunk locally to… (+17 more)

### Community 17 - "Community 17"
Cohesion: 0.12
Nodes (19): CursorFX(), CARDS, FeatureCards(), LandingNav(), CascadeToken(), CoreCard(), ORBIT_CHIPS, OrbitChip() (+11 more)

### Community 18 - "Community 18"
Cohesion: 0.14
Nodes (24): delete_all_failed_jobs(), delete_job(), get_job(), _get_job_or_404(), get_user_stats(), _job_summary(), list_jobs(), Any (+16 more)

### Community 19 - "Community 19"
Cohesion: 0.22
Nodes (20): unique_email(), bearer(), login(), Auth flow integration tests — register, login, profile update, password change.…, register(), test_change_password_full_flow(), test_change_password_rejects_short_new(), test_login_roundtrip() (+12 more)

### Community 20 - "Community 20"
Cohesion: 0.12
Nodes (20): _age_days(), _compute(), get_recommendations_for_user(), load_user_profile(), peek_recommendations(), Any, AsyncSession, UUID (+12 more)

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (22): board_json_to_text(), extract_densest_block(), extract_jsonld(), extract_next_data(), extract_selectors(), _html_to_text(), _iter_jsonld(), Any (+14 more)

### Community 22 - "Community 22"
Cohesion: 0.11
Nodes (15): field_validator, Path, True when S3/R2 credentials are configured., Fail fast at startup rather than run production with dev secrets., Settings, _slugify(), BaseSettings, model_validator (+7 more)

### Community 23 - "Community 23"
Cohesion: 0.10
Nodes (19): name, private, type, version, autoprefixer, axios, eslint, @eslint/js (+11 more)

### Community 24 - "Community 24"
Cohesion: 0.19
Nodes (12): AIAgent, Any, Parse raw resume text into metabase-shaped profile data., Select and rewrite resume content to match JD. Returns a structured dict ready…, Simulate ATS scoring of the tailored resume., Generate a personalized cover letter. Args: parsed_jd — structured JD from…, Single JSON-mode completion. Every caller prompts for JSON-only output, so JSON…, Generate tailored interview questions + model answers. Returns: { questions: [… (+4 more)

### Community 25 - "Community 25"
Cohesion: 0.17
Nodes (16): billingAPI, ProtectedRoute(), COLORS, SIZES, Spinner(), Admin(), fmt(), Stat() (+8 more)

### Community 26 - "Community 26"
Cohesion: 0.18
Nodes (16): _fail_row(), fixture, Cover letters / interview prep run as background jobs; /api/activity reports…, stub(), test_cap_of_three_active(), test_cover_letter_post_is_202_and_enqueues(), test_failed_cover_letter_and_prep_can_be_retried(), test_other_users_rows_hidden() (+8 more)

### Community 27 - "Community 27"
Cohesion: 0.25
Nodes (18): _clean_url(), Drop tracking query params so the same job isn't listed twice., job(), Job recommendation scoring: the failure modes that made suggestions bad., scored(), test_aliases_js_and_k8s(), test_clean_url_keeps_real_params(), test_company_name_is_not_searched() (+10 more)

### Community 28 - "Community 28"
Cohesion: 0.11
Nodes (19): devDependencies, autoprefixer, eslint, @eslint/js, eslint-plugin-react, eslint-plugin-react-hooks, globals, jsdom (+11 more)

### Community 29 - "Community 29"
Cohesion: 0.25
Nodes (16): claims(), configured(), google(), fixture, Google sign-in: new accounts, returning users, safe linking, failure modes., stub_google(), test_google_only_user_cannot_change_password_without_one(), test_invalid_token_rejected() (+8 more)

### Community 30 - "Community 30"
Cohesion: 0.18
Nodes (18): google_login(), GoogleLoginRequest, login(), logout(), logout_all(), AsyncSession, post, Response (+10 more)

### Community 31 - "Community 31"
Cohesion: 0.16
Nodes (17): Set a new password using a reset token from the email link. Tokens are single-…, reset_password(), create_reset_token(), decode_token(), hash_password(), _pw_fingerprint(), Return the user_id if valid AND the password hasn't changed since issue., Verify a Google Identity Services ID token (signature, expiry, issuer and that… (+9 more)

### Community 32 - "Community 32"
Cohesion: 0.24
Nodes (11): ScraperService, client_for(), Scraper: SSRF guard, redirect handling, caps, and extraction., test_404_is_not_retried(), test_body_is_capped(), test_follows_safe_redirect(), test_non_html_content_type_rejected(), test_redirect_loop_gives_up() (+3 more)

### Community 33 - "Community 33"
Cohesion: 0.18
Nodes (13): forgot_password(), ForgotPasswordRequest, BaseModel, field_validator, patch, Update the current user's full_name., Send a password-reset link if the account exists. ALWAYS returns the same 200…, RegisterRequest (+5 more)

### Community 34 - "Community 34"
Cohesion: 0.15
Nodes (16): billing_status(), cancel_subscription(), CheckoutRequest, create_checkout(), list_plans(), AsyncSession, BaseModel, get (+8 more)

### Community 35 - "Community 35"
Cohesion: 0.13
Nodes (15): close_db(), Dispose the engine connection pool on shutdown., contextlib, fastapi_middleware_cors, fastapi_middleware_gzip, fastapi_responses, fastapi_staticfiles, lifespan() (+7 more)

### Community 36 - "Community 36"
Cohesion: 0.16
Nodes (14): Exception, RobotsBlocked, ScraperError, generate(), history(), CLI Tool — Generate resume from command line without running the server. Usage:…, Show previously generated resumes., Generate a tailored resume for a job description. (+6 more)

### Community 37 - "Community 37"
Cohesion: 0.13
Nodes (14): compilerOptions, allowJs, checkJs, isolatedModules, jsx, lib, module, moduleResolution (+6 more)

### Community 38 - "Community 38"
Cohesion: 0.16
Nodes (9): board_api_url(), _clean_text(), AsyncClient, Collapse whitespace; drop SHORT boilerplate lines only (a long line that merely…, robots.txt via the async client (the old urllib read blocked the event loop…, GET with SSRF-checked manual redirects, size cap and transient retries. Returns…, Scrape a JD page. Returns (job_text, warning_message). Raises ScraperError /…, test_board_api_urls() (+1 more)

### Community 39 - "Community 39"
Cohesion: 0.14
Nodes (14): dependencies, axios, clsx, @fontsource/jetbrains-mono, @fontsource-variable/bricolage-grotesque, @fontsource-variable/plus-jakarta-sans, framer-motion, lucide-react (+6 more)

### Community 40 - "Community 40"
Cohesion: 0.26
Nodes (9): api, Layout(), NAV, NavItem(), LABEL, QueuePanel(), LABEL, useActivityStore (+1 more)

### Community 41 - "Community 41"
Cohesion: 0.24
Nodes (12): recommendationsAPI, DATE_FILTERS, DEFAULT_FILTERS, FilterBar(), JobCard(), JobRecommendations(), jobWithinDateFilter(), relativeTime() (+4 more)

### Community 42 - "Community 42"
Cohesion: 0.21
Nodes (12): auth_config(), export_my_data(), get, Public client settings the login page needs (no secrets)., Everything we store about the user, as JSON (data portability)., Resend the verification email for the logged-in user., Create a new account with email + password. Returns tokens immediately — no…, register() (+4 more)

### Community 43 - "Community 43"
Cohesion: 0.20
Nodes (8): build_csp(), _inline_script_hashes(), Security headers and request-body size limit (pure ASGI, no extra deps)., CSP hashes for the inline scripts in the built index.html (the theme…, SecurityHeadersMiddleware, base64, hashlib, re

### Community 44 - "Community 44"
Cohesion: 0.27
Nodes (10): _button_html(), app/services/email_service.py ────────────────────────────── Zero-dependency…, Send an email. Returns True on success, False otherwise — never raises., send_email(), send_password_reset_email(), _send_sync(), send_verification_email(), email_message (+2 more)

### Community 45 - "Community 45"
Cohesion: 0.20
Nodes (7): agent(), fixture, parametrize, Renders every LLM prompt with the fake provider. Catches f-string bugs (e.g.…, test_cover_letter_sparse(), test_every_llm_call_carries_the_injection_guard(), test_interview_prep_sparse()

### Community 46 - "Community 46"
Cohesion: 0.27
Nodes (7): AI Agent Orchestration ----------------------- Two-stage AI pipeline: Stage 1:…, app/services/cache_service.py ────────────────────────────── Redis caching…, Shared setup for cover-letter / interview-prep generation (runs in the worker)., json, logging, redis_asyncio, redis_exceptions

### Community 47 - "Community 47"
Cohesion: 0.24
Nodes (3): FakeRedis, test_blocks_after_limit_then_fails_open(), User

### Community 48 - "Community 48"
Cohesion: 0.27
Nodes (9): _job_event_stream(), get, UUID, app/api/sse_routes.py ────────────────────── Server-Sent Events endpoint for…, Format a dict as an SSE event string., Stream real-time job status updates via Server-Sent Events. Connect once —…, Async generator that yields SSE-formatted strings. Polls the DB until the job…, _sse_event() (+1 more)

### Community 49 - "Community 49"
Cohesion: 0.42
Nodes (4): MetabaseService, Any, AsyncSession, Build and return the complete candidate profile dict for a given user. Used by…

### Community 50 - "Community 50"
Cohesion: 0.20
Nodes (9): authoringSkill, media, autoProxy, paths, assets, blocks, components, registry (+1 more)

### Community 51 - "Community 51"
Cohesion: 0.25
Nodes (7): generate_resume(), _get_arq_pool(), Create a one-shot ARQ connection to enqueue a job., Enqueue a resume generation job. Returns HTTP 202 Accepted immediately with a…, GenerateResumeRequest, field_validator, POST /api/generate-resume Provide EITHER jd_url OR jd_text (not both, not…

### Community 52 - "Community 52"
Cohesion: 0.28
Nodes (5): GET /recommendations answers immediately; a cold fetch runs in the background., test_cold_cache_returns_pending_and_starts_one_fetch(), peek(), start(), test_warm_cache_is_ready_immediately()

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (8): name, private, scripts, check, dev, publish, render, type

### Community 54 - "Community 54"
Cohesion: 0.28
Nodes (3): ErrorBoundary, captureException(), SentryModule

### Community 56 - "Community 56"
Cohesion: 0.29
Nodes (8): count_active(), ensure_capacity(), get_activity(), _item(), AsyncSession, get, Free-tier AI quota is shared by everyone: cap one user's parallel work and…, {active: [...oldest first], recent: [...finished in the last 15 min]}.

### Community 57 - "Community 57"
Cohesion: 0.25
Nodes (8): compact_jd(), head_tail(), _is_heading(), Keep the start AND the end of long text (education/links sit at the end)., Shrink a job description to `limit` chars. Short JDs are returned as is.…, test_compact_jd_drops_boilerplate_keeps_requirements(), test_compact_jd_short_text_unchanged(), test_head_tail_keeps_both_ends()

### Community 58 - "Community 58"
Cohesion: 0.25
Nodes (8): scripts, build, dev, lint, preview, test, test:watch, typecheck

### Community 60 - "Community 60"
Cohesion: 0.33
Nodes (6): delete_my_account(), DeleteAccountRequest, delete, Permanently delete the account, its data and its generated files., delete_user_and_data(), Remove stored files, then the user row (FKs cascade to every table), then…

### Community 61 - "Community 61"
Cohesion: 0.33
Nodes (6): Set httpOnly auth cookies and return the access token string., _set_auth_cookies(), create_access_token(), create_refresh_token(), Create a signed JWT access token. Expires in JWT_ACCESS_EXPIRE_MINUTES (default…, Create a signed JWT refresh token. Expires in JWT_REFRESH_EXPIRE_DAYS (default…

### Community 62 - "Community 62"
Cohesion: 0.33
Nodes (4): per_user_limit(), app/api/rate_limit.py ────────────────────── Per-IP rate limiting for auth…, slowapi, slowapi_util

### Community 63 - "Community 63"
Cohesion: 0.33
Nodes (5): enqueue(), Enqueue arq jobs from API routes., One-shot connection: enqueue `function` and return the arq job., arq, arq_connections

### Community 64 - "Community 64"
Cohesion: 0.47
Nodes (5): copy, blob(), check(), main(), Quality + safety evals against the REAL model. Run by hand (or nightly), not on…

### Community 65 - "Community 65"
Cohesion: 0.33
Nodes (5): frontend_src_index, @fontsource/jetbrains-mono, @fontsource-variable/bricolage-grotesque, @fontsource-variable/plus-jakarta-sans, react-dom

### Community 66 - "Community 66"
Cohesion: 0.33
Nodes (6): health(), get, Readiness: the database must answer. Redis being down only degrades. Reports…, ready(), root(), serve_spa()

### Community 67 - "Community 67"
Cohesion: 0.40
Nodes (5): pytest, _cleanup_test_users(), client(), fixture, Test fixtures — integration tests against the real app + dev database. Run…

### Community 68 - "Community 68"
Cohesion: 0.40
Nodes (5): change_password(), ChangePasswordRequest, Change password — requires current password for verification. Every other…, Return True if plain matches the bcrypt hash., verify_password()

### Community 70 - "Community 70"
Cohesion: 0.40
Nodes (5): Return the URL if it is safe to fetch, else raise ScraperError. shortcut: DNS…, validate_public_url(), parametrize, test_allows_public_url(), test_blocks_unsafe_urls()

### Community 72 - "Community 72"
Cohesion: 0.50
Nodes (4): fastapi_routing, _depends_on_auth(), Every API route must require auth unless it is on the explicit public list., test_every_api_route_requires_auth_or_is_allowlisted()

### Community 73 - "Community 73"
Cohesion: 0.80
Nodes (4): H(), Page(), Privacy(), Terms()

### Community 74 - "Community 74"
Cohesion: 0.40
Nodes (3): subprocess, sys, The eval suite runs end to end against the fake provider, so its wiring cannot…

### Community 75 - "Community 75"
Cohesion: 0.50
Nodes (4): _count(), AsyncSession, get, stats()

### Community 76 - "Community 76"
Cohesion: 0.50
Nodes (4): is_admin(), require_admin(), get_me(), Return the current authenticated user's profile.

### Community 77 - "Community 77"
Cohesion: 0.50
Nodes (4): _extract_resume_text(), Prepend the document's hyperlink URLs so the LLM can fill…, Extract plain text from an uploaded PDF or DOCX (sync — run in a thread)., _with_links()

### Community 78 - "Community 78"
Cohesion: 0.83
Nodes (3): applyTheme(), getInitialTheme(), useThemeStore

### Community 80 - "Community 80"
Cohesion: 0.50
Nodes (3): ImmutableAssets, Vite fingerprints every file in /assets, so browsers may cache them forever., StaticFiles

### Community 82 - "Community 82"
Cohesion: 0.67
Nodes (3): _is_transient(), Network blips / 5xx worth one retry — never 4xx (won't succeed on retry)., BaseException

## Knowledge Gaps
- **124 isolated node(s):** `$schema`, `registry`, `blocks`, `components`, `assets` (+119 more)
  These have ≤1 connection - possible missing edges. (Counts symbols only; 540 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `User` connect `Community 4` to `Community 3`, `Community 6`, `Community 7`, `Community 11`, `Community 18`, `Community 19`, `Community 29`, `Community 30`, `Community 31`, `Community 33`, `Community 34`, `Community 42`, `Community 48`, `Community 51`, `Community 56`, `Community 60`, `Community 61`, `Community 62`, `Community 67`, `Community 68`, `Community 75`, `Community 76`, `Community 81`, `Community 84`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `CacheService` connect `Community 5` to `Community 46`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Why does `JobApplication` connect `Community 18` to `Community 34`, `Community 3`, `Community 4`, `Community 36`, `Community 6`, `Community 7`, `Community 75`, `Community 46`, `Community 48`, `Community 16`, `Community 51`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Are the 77 inferred relationships involving `User` (e.g. with `get_activity()` and `is_admin()`) actually correct?**
  _`User` has 77 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `registry`, `blocks` to the rest of the system?**
  _124 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05367231638418079 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07205387205387205 - nodes in this community are weakly interconnected._