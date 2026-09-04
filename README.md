# BMONI_MCP

An [MCP](https://modelcontextprotocol.io) server that exposes the **BMONI Embedded API** (wallets, cards, KYC, rails, deposits, withdrawals, SEPA/LATAM/payouts, webhooks) as tools an AI agent can call to build wallet & card solutions.

Built with [FastMCP](https://gofastmcp.com) (Python). Validated against the API contract in [`resource.md`](./resource.md).

## What it can do

The 115+ tools are grouped by lifecycle stage so agents can drive a full journey end to end:

| Capability | Tool prefix | Example tools |
|---|---|---|
| **Create the user** | `bmoni_users_*` | `bmoni_users_create` |
| **Provision the smart wallet** | `bmoni_wallets_*` | `bmoni_wallets_owner_proof_challenge`, `bmoni_wallets_create_managed` |
| **Verify identity (KYC)** | `bmoni_kyc_*` | `bmoni_kyc_update_profile`, `bmoni_kyc_upload_identification`, `bmoni_kyc_activate`, `bmoni_kyc_status` |
| **Activate the rail** | `bmoni_rails_*` | `bmoni_rails_start_usa`, `bmoni_rails_provision_usd_vba`, `bmoni_rails_onboarding_status`, VBA link/unlink |
| **Fund the wallet** | `bmoni_fund_*` | `bmoni_fund_deposit_crypto`, `bmoni_fund_card`, `bmoni_fund_latam_cash` |
| **Move money** | `bmoni_money_*` | sends, proposals + `bmoni_money_submit_signature`, exchange, withdrawals, offramps, SEPA, bank payouts |
| **Information about BMONI** | `bmoni_info_*` | health, supported countries/subdivisions/cities |
| Supporting | `bmoni_cards_*`, `bmoni_bank_accounts_*`, `bmoni_employer_*`, `bmoni_webhooks_*` | card lifecycle, bank accounts, employee invites, webhook config |
| **Human approvals** | `bmoni_approvals_*` | list/approve/reject HITL approval records (admin) |

List every tool with:

```bash
python server.py --list-tools
```

## Configuration

Everything is read from the environment (no hard-coded endpoints/keys). See [`.env.example`](./.env.example).

```bash
cp .env.example .env   # then fill in your BMONI_ENV + the matching credential pair
```

### Environment selection (fail closed)

`BMONI_ENV` picks the active credential pair — there is **no default that
implies production**. A fresh checkout runs against the sandbox for manual
smoke tests; production requires an explicit `BMONI_ENV=production`.

| Variable | Used when | Description |
|---|---|---|
| `BMONI_ENV` | always | `sandbox` \| `production` |
| `BMONI_SANDBOX_BASE_URL` | `sandbox` | Developer API link |
| `BMONI_SANDBOX_API_KEY` | `sandbox` | Developer API key |
| `BMONI_BASE_URL` | `production` | Production Embedded API host |
| `BMONI_API_KEY` | `production` | Partner key, sent as `x-api-key` |

Mixing credentials across environments is a **hard startup error** (`bmoni_mcp/env_guard.py`), never a silent fallback. The same guard runs in the sandbox smoke suite.

### Security runbook

All knobs fail closed — the restricted behavior is the default:

| Variable | Default | Purpose |
|---|---|---|
| `BMONI_READ_ONLY` | `0` | `1` refuses every mutating BMONI request inside `BmoniClient` (GET + a tiny pure-read POST allowlist only) |
| `BMONI_ERROR_BODY_ECHO` | `masked` | `0` = never echo bodies, `masked` = generic, `1` = echo the always-redacted body |
| `BMONI_SCOPED_USER_ID` | unset | stdio identity: the BMONI user id this local session is scoped to (trust = OS user) |
| `BMONI_ADMIN_SUBJECTS` | unset | comma-separated subjects with `role=admin` (admin + approval tools). Empty = nobody is admin |
| `BMONI_MCP_TOKENS` | unset | static bearer allowlist for http/sse, `sub:token[,sub:token...]` |
| `BMONI_MCP_JWT_*` | unset | JWT verification for http/sse (issuer/audience/JWKS/public key); token `sub` = BMONI user id |
| `BMONI_ALLOWED_ORIGINS` | unset | browser origins allowed on http/sse; **required for a non-loopback bind** |
| `BMONI_AUDIT_LOG` | unset | JSONL audit file or `stdout`; empty = off |
| `BMONI_APPROVAL_*` | see below | HITL knobs (TTL 600s, deny cooldown 300s, max pending 100, sqlite db) |
| `BMONI_AUTO_APPROVE_TOOLS` | empty | explicit per-tool auto-approve widening |
| `BMONI_HITL_GRAY` | `0` | widen config-safe "gray" tools to require approval |
| `BMONI_RATE_LIMIT_RPS/BURST` | `10`/`20` | per-principal token bucket |
| `BMONI_MAX_CONCURRENT` | `0` | max in-flight tool calls (0 = unlimited) |
| `BMONI_UPLOAD_MAX_MB` | `5` | uploaded file size cap (magic-byte sniffed) |

Transport rules enforced in `cli.py`:
- http/sse bind **loopback by default**. Binding a non-loopback host **without
  auth (`BMONI_MCP_TOKENS` or `BMONI_MCP_JWT_*`) or without
  `BMONI_ALLOWED_ORIGINS` is a startup error** — the endpoint is never
  exposed unauthenticated. TLS is terminated by your reverse proxy, not here.
- stdio is trusted to the OS user; scope it with `BMONI_SCOPED_USER_ID`.

### Human-in-the-loop approvals (HITL)

Money-moving, irreversible/control-changing and partner/admin writes go
through an approval gate (see `bmoni_mcp/policy.py`). No BMONI request is
made until a human approves:

1. The agent calls a harmful tool → the middleware returns a structured,
   **non-error** result: `{"status": "approval_required", "approval": {...}}`.
2. A human approver (a principal in `BMONI_ADMIN_SUBJECTS`) lists and resolves
   the PENDING record with `bmoni_approvals_list` / `_approve` / `_reject`
   (optionally notified via the HMAC-signed `BMONI_APPROVAL_CALLBACK_URL`).
3. The agent repeats the *identical* call; the middleware matches
   `(principal, tool, args_hash)`, consumes the record once, then dispatches.
4. Denied calls stay blocked for `BMONI_APPROVAL_DENY_COOLDOWN` seconds.

Approvals never replace the owner's EIP-191/712 wallet signature — BMONI's
signature gates are untouched.

## Install & run

Requires Python 3.10+.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### stdio (desktop MCP clients)

```bash
export BMONI_ENV=sandbox
export BMONI_SCOPED_USER_ID=<your-bmoni-user-id>
python server.py
```

Example Claude Desktop / Cursor / similar config:

```json
{
  "mcpServers": {
    "bmoni": {
      "command": "python",
      "args": ["/path/to/bmoni_mcp/server.py"],
      "env": {
        "BMONI_ENV": "sandbox",
        "BMONI_SANDBOX_BASE_URL": "https://<dev-api-link>",
        "BMONI_SANDBOX_API_KEY": "<developer-api-key>",
        "BMONI_SCOPED_USER_ID": "<your-bmoni-user-id>"
      }
    }
  }
}
```

### HTTP / SSE (remote agents)

```bash
python server.py --transport http --host 127.0.0.1 --port 8000
# endpoint: http://127.0.0.1:8000/mcp
```

For a non-loopback bind you MUST configure auth and origins first:

```bash
export BMONI_MCP_TOKENS='3f4a2b91-...:some-long-random-token'
export BMONI_ALLOWED_ORIGINS='https://app.example.com'
python server.py --transport http --host 0.0.0.0 --port 8000
# clients call with: Authorization: Bearer some-long-random-token
```

Or run the package directly: `python -m bmoni_mcp --transport http`.

## Typical agent journey

1. `bmoni_users_create` — create the wallet holder.
2. `bmoni_wallets_owner_proof_challenge` + `bmoni_wallets_create_managed` — provision a smart wallet (challenge must be signed by the user's EVM wallet; the agent orchestrates the signing).
3. `bmoni_kyc_update_profile` / `bmoni_kyc_upload_identification` → `bmoni_kyc_activate` → poll `bmoni_kyc_status` — verify identity.
4. `bmoni_rails_start_usa` (or `start_nigeria`/`start_monerium`/…) and `bmoni_rails_provision_usd_vba` — activate a rail.
5. `bmoni_fund_deposit_crypto` — fund the wallet.
6. `bmoni_money_send_account` / `bmoni_money_withdraw_nigeria_bank` — move money; money-moving tools are approval-gated, and when a tool returns a sign payload, the owner signs it and submits with `bmoni_money_submit_signature`.

## Layout

```
server.py                  # CLI entry point (stdio/http/sse)
bmoni_mcp/
  config.py                # env-only configuration + fail-fast errors
  env_guard.py             # BMONI_ENV sandbox/production pairing guards
  redact.py                # recursive sensitive-key scrubber (PAN/CVV/pin/...)
  uploads.py               # magic-byte + size validation for file uploads
  policy.py                # HITL/role classification inventory
  approvals.py             # sqlite human-approval store (content-matched, consume-once)
  audit.py                 # JSONL audit trail (redacted)
  limits.py                # per-principal token bucket + concurrency
  authn.py                 # principal/role resolution + http/sse auth provider
  middleware.py            # FastMCP enforcement middleware (scope/HITL/rate/audit)
  api.py                   # async HTTP client (x-api-key), read-only + redaction
  models.py                # pydantic bodies for nested payloads
  server.py                # FastMCP assembly + middleware + auth
  cli.py / __main__.py     # arg parsing
  tools/
    users.py  kyc.py  wallets.py  rails.py  fund.py
    money.py  cards.py  bank_accounts.py
    info.py  employer.py  webhooks.py  approvals_tools.py
tests/test_server.py       # contract + security tests (no live API)
tests/test_sandbox_smoke.py# LIVE suite against the developer API (sandbox only)
```

## Tests

### Contract + security (no live API, no credentials)

```bash
python tests/test_server.py
```

Validates registration/schemas, read-only mode, error redaction, key-not-logged
invariants, `BMONI_ENV` pairing, approval gate (refuse → approve → consume-once),
TTL/cooldown, role gating + user-id pinning, rate limiting and upload guards.

### Sandbox smoke (live, sandbox only)

Runs a representative **read-only** journey against the developer API. It only
runs when `BMONI_ENV=sandbox` + sandbox credentials are set, is skipped
otherwise, and hard-refuses if it detects production credentials:

```bash
BMONI_ENV=sandbox python tests/test_sandbox_smoke.py
```

Run this before every production deploy.

## Notes

- Endpoints marked internal/HMAC-signed in `resource.md` (e.g. `/v1/internal/*`, receiving webhook events) are intentionally not exposed.
- Binary responses (receipt PDFs) and uploaded files are transported as base64 so they stay JSON-serializable. Uploads are size-capped and magic-byte sniffed before being forwarded.
- `signature`-bearing flows return the payload/message to sign; cryptographic signing is left to the wallet owner, and the signature is submitted via `bmoni_money_submit_signature`.
- This server never stores BMONI end-user PII, never holds wallet keys, and never runs live tests against production credentials.
