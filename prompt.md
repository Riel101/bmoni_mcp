# Security review bridge: BMONI MCP server (v2 plan)

This file hands the security risks, agreed decisions, and the full hardening
plan for this MCP server to the next session. Read `resource.md` (BMONI API
reference) and the server code under `bmoni_mcp/` before acting. The server
exposes 115 tools grouped as `bmoni_users_*`, `bmoni_kyc_*`,
`bmoni_wallets_*`, `bmoni_rails_*`, `bmoni_fund_*`, `bmoni_money_*`,
`bmoni_cards_*`, `bmoni_bank_accounts_*`, `bmoni_info_*`,
`bmoni_webhooks_*`, `bmoni_employer_*`.

## Trust model (know this first)

- `bmoni_mcp/config.py` reads everything from env (`BMONI_BASE_URL`,
  `BMONI_API_KEY`, plus optional transport/host/port). No hard-coded secrets.
  A `.env` file is auto-loaded from CWD if python-dotenv is present.
- `bmoni_mcp/api.py` `BmoniClient` is stateless; every request sends the
  **single partner-wide API key** as `x-api-key` and creates a fresh
  `httpx.AsyncClient`. Errors re-raise `BmoniError` containing the response
  body truncated to ~2000 chars.
- The MCP layer has **no authentication/authorization of its own**; whoever
  can reach the server (stdio subprocess owner, or anyone who can hit an
  exposed http/sse port) can invoke ANY tool = full partner capability.
- BMONI enforces ownership per user (403 if a user is not the partner's),
  but the key itself is partner-scoped and un-scoped to any single end user.

## Product goal & guardrail contract

Main goal: **let users prompt any agent to do anything a fintech app can do**
by connecting the MCP server. Security hardening must therefore preserve full
capability while making every harmful action **human-approved, attributable,
and scoped to an authenticated end user**.

Non-negotiables:
- Never hold user wallet keys. BMONI EIP-191/712 signature gates and the
  per-user 403 ownership check are the outer guarantees; keep them.
- Enforce at the two choke points: `BmoniClient.request()` (all 115 tools
  funnel through it) and FastMCP middleware (all dispatch).
- Fail closed: missing/invalid security config resolves to the restricted
  behavior, never the exposed one.
- Do not go beyond BMONI API capabilities: no per-user BMONI API keys, no
  server-side settlement/limit changes, no misuse of BMONI OTP/email/webhook
  endpoints for approvals, no fabricating idempotency keys.
- Approvals are **not** a substitute for the owner's wallet signature.

## Where user info and tokens live (agreed)

- **BMONI end-user data (KYC, wallets, txns, PAN/CVV):** NOT stored by this
  server. The server is stateless; it only forwards an opaque `user_id`
  UUID. PII lives in BMONI's platform.
- **Session auth tokens:** validated, never stored/minted here. http/sse =
  bearer token verified by FastMCP `auth` (`JWTVerifier` via the operator's
  IdP is the production recommendation; `StaticTokenVerifier` allowlist is a
  simpler option whose allowlist lives in server env). stdio = identity
  pinned from `BMONI_SCOPED_USER_ID` env; trust = the OS user.
- **Partner key / webhook / approval secrets:** env only (`.env`, gitignored,
  or process env of the MCP client). Never logged (invariant-tested).
- **Approval records:** sqlite file (`BMONI_APPROVAL_DB`), transient,
  holds `user_id`, tool, args hash, amount/recipient summary, TTL, status.
- **Audit trail:** `BMONI_AUDIT_LOG` file/stdout, redacted.

## Developer sandbox — pre-production test environment (agreed)

All testing against live BMONI before production MUST use the **developer
(sandbox) API link and developer API key**, never the production endpoint or
key. Modeled as an explicit environment switch so a mistake can't silently hit
production.

Env contract:
- `BMONI_ENV` = `sandbox` | `production` (no default that implies prod;
  explicit everywhere).
- Sandbox: `BMONI_SANDBOX_BASE_URL` (developer API link) +
  `BMONI_SANDBOX_API_KEY` (developer API key).
- Production: `BMONI_BASE_URL` + `BMONI_API_KEY`.
- `config.py`/`get_client()` resolve the active endpoint + key pair purely
  from `BMONI_ENV`.

Fail-closed guards (startup + runtime):
- `BMONI_ENV=sandbox` requires the sandbox pair and refuses to run if a
  production key is set in the same process.
- `BMONI_ENV=production` requires the production pair and refuses if only
  sandbox credentials are present.
- Guardrail helper `bmoni_mcp/env_guard.py` (used by `config.py`, `cli.py`,
  and the sandbox smoke suite) exposes `is_sandbox()`, `assert_env_pair()`.
- Test/CI never holds or runs against production credentials; contract tests
  stay mocked (no network).

Where it lives:
- Developer API link + developer API key are stored ONLY in the operator's
  `.env` (sandbox section, gitignored) or process env — never committed,
  never logged, never returned by any tool.
- `.env.example` ships with an empty `BMONI_ENV=sandbox` section documenting
  both pairs so a fresh checkout runs against the sandbox by default for
  manual smoke tests.

Workflow:
1. Local dev / manual smoke: `BMONI_ENV=sandbox` → developer API link + key.
2. New `tests/test_sandbox_smoke.py` live suite: runs ONLY when
   `BMONI_ENV=sandbox` and sandbox credentials are set; skipped otherwise and
   hard-refused if it detects production credentials; covers a representative
   journey (create user → KYC options → balances → read-only checks) against
   the developer API before any production deployment.
3. Production deploy: `BMONI_ENV=production` with the production pair; the
   same fail-closed checks make a mixed/dev `.env` an explicit startup error.

## Threats & challenges (grouped)

### 1. Unrestricted agent = financial superuser
- No human-in-the-loop, no per-tool approval, no rate limiting on this side.
- Some endpoints act without an extra signature: `bmoni_money_withdraw_card`
  (card -> wallet), `bmoni_fund_deposit_crypto` (returns deposit address),
  `bmoni_money_eu_kyc`. A mis-prompted or compromised agent can therefore
  move/configure money silently for any of the partner's users.
- Signature-gated flows are only gated because BMONI requires an EIP-191/712
  signature the user's EVM wallet produces out-of-band; the server never
  holds keys (good) — keep it that way. If the orchestration layer also holds
  the user's wallet key, that protection disappears.

### 2. Transport exposure
- stdio is safe-ish (inherits OS user permissions). http/sse default to
  127.0.0.1 but `cli.py` allows `--host 0.0.0.0` / env override with **no
  TLS, no OAuth, no API-key auth on the MCP endpoint**, and FastMCP's request
  guard/CORS are not wired up (no `allowed_origins`, no CORSMiddleware).
- Consequence of exposure: full KYC data, card PAN/CVV, transaction
  histories, and money movement reachable by any network caller.

### 3. Bulk PII & sensitive data flows
- Tools return/accept: KYC profiles + presigned document URLs
  (`bmoni_kyc_get_profile`), BVN/NIN lookups, PAN/CVV
  (`bmoni_cards_sensitive_data`, `bmoni_cards_identity*`), card ledgers,
  receipts (base64 PDFs), full transaction lists with counterparties.
- Risks: MCP clients log conversations → PII persisted in model/agent logs
  (GDPR / Nigeria NDPR exposure); document uploads accept base64 images
  (identity docs, selfies) with no client-side size/type limits; error
  bodies echoed into tool results can leak provider/validation details or
  PII into logs and UI.

### 4. Misuse of partner-level, user-unscoped endpoints
- Webhooks: `bmoni_webhooks_register_config` / `_update_config` /
  `_rotate_secret` let an agent redirect signed event callbacks to an
  attacker-controlled URL (data exfiltration of deposit/card/kyc events).
- Employer: `bmoni_employer_invite_employee` / `_batch_upsert` send
  co-branded emails (spam/cost) and can offboard employees
  (`bmoni_employer_offboard`).
- Announcement/card/KYC endpoints operate on arbitrary `user_id`; there is no
  per-session user scoping — enforce/expect a proxy that pins `userId`, or
  per-tenant partner keys.

### 5. Secret & key hygiene
- `BMONI_API_KEY`, `BMONI_SANDBOX_API_KEY` and webhook/approval secrets live
  in env / `.env`; risk of committing `.env` (see `.gitignore` — only `venv`,
  langgraph dir, opencode.json and resource.md are ignored).
- No audit trail exists: tool name, caller, args, timestamp are not logged,
  so abuse is hard to attribute.

### 6. Availability & cost abuse
- No rate limiting/idempotency keys on our side; agents can loop PDF-receipt
  generation, balance polling, exchange quotes, or provider lookups → cost,
  upstream 429s, or partner rate-limit bans.

### 7. Supply chain / validation
- Accepts base64 files with guessed content types (`kyc.py`, `money.py`
  uploads) and forwards to identity/verification providers; no magic-byte
  sniffing or size caps before send.
- `EuCounterpart`/`BankPayoutDetails` models take free-form dicts in places
  (`models.py`) — schema guidance is loose for some nested bodies.

## Architecture decisions (agreed, do not relitigate)

1. **Identity model:** token subject (`sub` claim) = BMONI `user_id` for
   http/sse; `BMONI_SCOPED_USER_ID` env fallback for local stdio. Server
   validates tokens; never mints/persists them. No external IdP required to
   start.
2. **Admin boundary:** `bmoni_webhooks_*` and `bmoni_employer_*` are
   role=admin; hidden from `tools/list` and rejected for non-admin
   principals. Everything else is role=user by default.
3. **Fail-closed policy:** hard-fail at startup when binding a non-loopback
   host without auth (`BMONI_MCP_TOKEN`/`BMONI_MCP_JWT_*`) and origins
   configured. Same fail-closed rule applies to the `BMONI_ENV` credential
   pair (see Developer sandbox section).
4. **HITL scope:** balanced default — HITL on money-moving + irreversible /
   control-changing + admin writes. Gray items (KYC activate/retry/uploads,
   rail `start_*`/provision, EU KYC, card OTP steps, wallet/user create)
   default to config-safe; operator can widen via policy knobs.
5. **Approval binding:** content-matched, consume-once. An approved record
   matches `(principal, tool, args_hash)` on the identical re-call and is
   consumed once. No tool-signature churn across the 115 tools.
6. **Approval channels:** HMAC-verified approval webhook to the operator's
   companion UI (`BMONI_APPROVAL_CALLBACK_URL` +
   `BMONI_APPROVAL_WEBHOOK_SECRET`) AND human-role MCP tools
   (`bmoni_approvals_list/approve/reject`); file/log adapter for dev.
7. **Pre-production testing:** live calls before production use the developer
   API link + developer API key only, behind `BMONI_ENV=sandbox`, with a
   dedicated smoke suite and hard guards against mixing production
   credentials (see Developer sandbox section).

## Human-in-the-loop approval manager (Phase 0 — do first)

New `bmoni_mcp/policy.py` + `bmoni_mcp/approvals.py` + enforcement middleware
in `server.py`. Stdlib only (`sqlite3`, `hmac`, `hashlib`).

Flow for every harmful call:
1. Agent invokes a harmful tool → enforcement middleware classifies it; **no
   BMONI request is made**.
2. Middleware stores a PENDING approval `{id, principal, tool, args_hash,
   risk, summary, expires_at}` and notifies the human via the configured
   channels.
3. Tool returns a structured, non-error result:
   `{status: "approval_required", approval: {id, tool, summary,
   amount/currency/destination when present, expires_at}}` so the agent can
   relay it to the user.
4. A human approver (separate principal/secret) resolves it → APPROVED /
   REJECTED. Denied calls stay blocked for a cooldown window (anti-loiter).
5. The agent repeats the identical call within TTL (default 10 min).
   Middleware matches an APPROVED, unexpired, unused record on
   `(principal, tool, args_hash)`, marks it USED, then dispatches the tool.
6. Every step (pending/approve/deny/execute) is written to the audit log.

Middleware order: authn/principal → rate limit → **HITL gate** → audit →
tool.

Policy knobs (default strict, all `BMONI_*` env):
- `BMONI_APPROVAL_TTL_SECONDS` (default 600), `BMONI_APPROVAL_DENY_COOLDOWN`,
  `BMONI_APPROVAL_MAX_PENDING`, `BMONI_APPROVAL_DB`.
- Per-tool auto-approve exceptions **default empty**; widening is explicit.
- Approval records persist across restarts (sqlite) but expire by TTL.

### HITL classification inventory (balanced default)

HITL required — moves money:
`bmoni_money_send_named`, `bmoni_money_send_account`,
`bmoni_money_offramp_nigeria`, `bmoni_money_withdraw_nigeria_bank`,
`bmoni_money_withdraw_crypto`, `bmoni_money_withdraw_card`,
`bmoni_money_sepa_prepare`, `bmoni_money_sepa_complete`,
`bmoni_money_latam_cash_send`, `bmoni_money_create_bank_payout`,
`bmoni_money_submit_signature` (executes proposals),
`bmoni_money_create_proposal` (TRANSFER/SWAP/member/threshold = control
changes), `bmoni_fund_card` (wallet→card), `bmoni_cards_set_limits`.

HITL required — harmful / irreversible / control:
`bmoni_cards_deactivate` (irreversible), `bmoni_cards_sensitive_data`
(PAN/CVV), `bmoni_cards_set_pin` / `bmoni_cards_reset_pin`,
`bmoni_cards_set_status` only when `ACTIVE` (unfreeze),
`bmoni_cards_create` (fee + new spend instrument),
`bmoni_bank_accounts_add_nigeria_withdrawal` (exfil destination),
`bmoni_bank_accounts_deactivate_deposit_eu`,
`bmoni_bank_accounts_deactivate_nigeria_withdrawal`,
`bmoni_rails_link_vba_nigeria` / `bmoni_rails_link_vba_eu` /
`bmoni_rails_link_vba_usd` (esp. `restore_sweep_to_wallet_id`).

HITL required — admin/partner role:
`bmoni_webhooks_register_config`, `bmoni_webhooks_update_config` (redirect =
data exfil), `bmoni_webhooks_rotate_secret`, `bmoni_employer_invite_employee`,
`bmoni_employer_batch_upsert`, `bmoni_employer_offboard`.

NOT harmful (no HITL; still rate-limited):
`bmoni_info_*`, health, wallet/account/balance/transaction reads, receipts,
exchange rates/quotes/convert, proposal list/get/sign-payload,
`bmoni_money_reject_proposal` (protective), KYC options/readiness/status/
lookups, card transactions/limits/identity reads, bank-account list/verify,
`bmoni_fund_deposit_crypto` (inbound address), `bmoni_fund_supported_assets`.

Gray (default config-safe; widen via policy knobs if desired):
KYC `activate`/`retry`/uploads, rail `start_*`/`provision_usd_vba`, card
activation OTP request/confirm, `bmoni_money_eu_kyc`,
`bmoni_wallets_create_managed`, `bmoni_users_create`.

## Recommended hardening backlog (implement in order)

1. **Read-only mode**: env `BMONI_READ_ONLY=1` enforced in `BmoniClient`.
   Client choke point: allow GET plus a tiny explicit allowlist of pure-read
   POSTs (e.g. `cards/sensitive-data`, `payouts/validate-account`); refuse all
   other mutations with a clear error. No tool can bypass it.
2. **Error redaction**: new `bmoni_mcp/redact.py` with a recursive denylist
   scrubber (`pan, cvv, cvc, pin, signature, bvn, nin, fileBase64,dataBase64, code, otp, secret`). Apply in `api.py` `BmoniError.body` and
   every 4xx/5xx echo. Env `BMONI_ERROR_BODY_ECHO=0|1|masked` (default
   `masked`).
3. **Audit log**: `Middleware.on_call_tool` hook (timestamp, principal, tool
   name, redacted args, outcome) to `BMONI_AUDIT_LOG` file or stdout; off by
   default and clearly documented. `BMONI_AUDIT_LOG_SENSITIVE=0` strips
   sensitive results from the transcript. Records the full approval
   lifecycle too.
4. **Transport hardening**: bind loopback by default; **hard-fail startup**
   for non-loopback without auth. Add `--allowed-origins` /
   `BMONI_ALLOWED_ORIGINS` + CORS; wire FastMCP `auth`
   (`StaticTokenVerifier` with `BMONI_MCP_TOKEN`, and/or `JWTVerifier` with
   `BMONI_MCP_JWT_*` issuer/audience/jwks; token `sub` = BMONI user id). Set
   `mask_error_details=True` and `strict_input_validation=True` on the
   FastMCP server. Document TLS via reverse proxy (not terminated in-repo).
5. **Rate limiting / cost abuse**: `bmoni_mcp/limits.py` per-principal token
   bucket + max-concurrency middleware (`BMONI_RATE_LIMIT_RPS`,
   `BMONI_RATE_LIMIT_BURST`, `BMONI_MAX_CONCURRENT`). Heavy tool groups
   (receipt PDF, balance polling, quotes, provider lookups) cost more tokens.
6. **Per-user scoping + roles**: principal middleware resolving identity from
   token `sub` or `BMONI_SCOPED_USER_ID`; pin/validate every `user_id`
   argument to the principal; reject AND hide admin-role tools for non-admin
   principals. BMONI's 403 ownership stays as the second line of defense.
7. **Upload guards**: shared validator (size cap `BMONI_UPLOAD_MAX_MB` ~5 MB;
   magic-byte sniffing for jpeg/png/pdf; reject mismatches) wired into all
   three KYC uploads (`kyc.py`) and the EU file upload (`money.py`).
8. **Stricter schemas**: type remaining free-form dicts in `models.py` per
   `resource.md`; enable FastMCP `strict_input_validation`.
9. **Secret hygiene**: `.gitignore` adds `.env`, `.env.*` (keep
   `*.env.example`); test asserting neither the production nor the sandbox
   API key ever appears in error messages or tool results; expand
   `.env.example` (sandbox + production sections) and the README security
   runbook with every new `BMONI_*` variable and its fail-closed default.
10. **Dev/sandbox pairing**: `bmoni_mcp/env_guard.py` + `BMONI_ENV` switch in
    `config.py`/`cli.py`; `tests/test_sandbox_smoke.py` live suite gated on
    `BMONI_ENV=sandbox` (skips otherwise, hard-refuses with production
    credentials set).

## Non-goals

- Issuing per-end-user BMONI API keys or weakening the partner-key model.
- Custody or signing of user wallet keys server-side.
- Changing settlement/approval rules inside BMONI (HITL and limits are OUR
  middleware, not server-side).
- Terminating TLS inside this repo.
- Approvals replacing the owner's EIP-191/712 wallet signature.
- Running any live (non-mocked) test against production credentials, ever.

## Verification

- `python tests/test_server.py` (contract tests, mocked transport, no live
  API) — keep green after every change. Extend it to cover:
  - Approval gate refuses harmful calls without a human-approved record and
    dispatches after a matching consumed approval.
  - Approval TTL, deny-cooldown, consume-once (no double execution), and
    expiry behavior.
  - Role gating: admin tool hidden/rejected for non-admin principal; `user_id`
    pinning enforced.
  - Read-only mode refuses POST/PUT/PATCH/DELETE and honors the allowlist.
  - Redaction: `BmoniError` bodies never contain PAN/CVV/pin/signature/
    base64 values.
  - Key-not-logged invariant (production AND sandbox keys).
  - `BMONI_ENV` pairing: sandbox config refuses a production key; production
    config refuses missing/mismatched creds.
  - Rate limiter trips after burst; upload guard rejects oversize /
    wrong-magic files.
  - Audit hook emits redacted records when enabled.
- `python tests/test_sandbox_smoke.py` — LIVE smoke suite against the
  developer API; runs only when `BMONI_ENV=sandbox` + sandbox credentials are
  set; skipped otherwise; hard-refuses production credentials. Representative
  read-only journey, run before every production deploy.
- Re-run stdio + http MCP smoke tests after transport/auth changes.
- CI / pre-commit gate: `python tests/test_server.py` green.
