# Security review bridge: BMONI MCP server

This file hands the security risks and challenges of this MCP server to the
next session. Read `resource.md` (BMONI API reference) and the server code
under `bmoni_mcp/` before acting. The server exposes 115 tools grouped as
`bmoni_users_*`, `bmoni_kyc_*`, `bmoni_wallets_*`, `bmoni_rails_*`,
`bmoni_fund_*`, `bmoni_money_*`, `bmoni_cards_*`, `bmoni_bank_accounts_*`,
`bmoni_info_*`, `bmoni_webhooks_*`, `bmoni_employer_*`.

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

## Threats & challenges (grouped)

### 1. Unrestricted agent = financial superuser
- No human-in-the-loop, no per-tool approval, no rate limiting on this side.
- Some endpoints act without an extra signature: `bmoni_money_withdraw_card`
  (card -> wallet), `bmoni_fund_deposit_crypto` (returns deposit address),
  `bmoni_money_eu_kyc`. A mis-prompted or compromised agent can therefore
  move/configure money silently for any of the partner's users.
- Signature-gated flows are only gated because BMONI requires an EIP-191/712
  signature that the user's EVM wallet produces out-of-band; the server never
  holds keys (good) — keep it that way. If the orchestration layer also holds
  the user's wallet key, that protection disappears.

### 2. Transport exposure
- stdio is safe-ish (inherits OS user permissions). http/sse default to
  127.0.0.1 but `cli.py` allows `--host 0.0.0.0` / env override with **no
  TLS, no OAuth, no API-key auth on the MCP endpoint**, and FastMCP's request
  guard/CORS are not wired up (no `allowed_origins`, no CORSMiddleware).
- Consequence of exposure: full KYC data, card PAN/CVV, transaction
  histories, and money movement reachable by any network caller.
- Suggested hardening: keep bind loopback-only; if remote is required add
  TLS + FastMCP auth provider or a reverse proxy; add `--allowed-origins` /
  `BMONI_ALLOWED_ORIGINS` + CORS middleware before any Chrome-extension or
  web client work.

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
- `BMONI_API_KEY` (and any webhook secret returned by rotate) live in env /
  `.env`; risk of committing `.env` (see `.gitignore` — only `venv` and
  langgraph dir are ignored). Key is never logged by our code today (verify
  if changed).
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

## Recommended hardening backlog (for next session)

Prioritize and implement, then extend `tests/test_server.py`:

1. **Read-only mode**: env `BMONI_READ_ONLY=1` that refuses all non-GET /
   mutation tools (money movement, KYC activate, webhook/employer writes,
   card ops) with a clear error.
2. **Audit log**: middleware that records tool name + user-supplied args
   (redacting `signature`, `pin`, `file_base64`, `pan`, sensitive fields) to
   stdout or a file; keep it off by default or clearly documented.
3. **Error redaction**: in `api.py`, mask/hide sensitive body content on
   4xx/5xx and never echo bodies containing PAN/CVV/signatures.
4. **Transport hardening**: bind loopback by default (already), and add
   `--allowed-origins`/`BMONI_ALLOWED_ORIGINS` + CORSMiddleware + optional
   token auth for the http transport before enabling web/extension clients.
5. **Upload guards**: enforce base64 size limit (~5 MB), require expected
   magic bytes / extensions, reject others before sending to BMONI.
6. **Consent confirmation for irreversible actions**: wrap destructive tools
   (deactivate card, offboard employee, webhook redirect, large withdrawals)
   with a mandatory `confirm: true` argument so agents must explicitly pass it.
7. **Per-user scoping proxy** (bigger): a thin layer that binds one API key /
   `userId` per session instead of one partner-wide key, and documents the
   403 ownership guarantee BMONI provides.
8. Update `README.md` security section + `.env.example` with the new vars.

## Verification
- `python tests/test_server.py` (contract tests, mocked transport, no live
  API) — keep it green after every change.
- Re-run stdio + http MCP smoke tests after transport changes.
