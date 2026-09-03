# BMONI_MCP

An [MCP](https://modelcontextprotocol.io) server that exposes the **BMONI Embedded API** (wallets, cards, KYC, rails, deposits, withdrawals, SEPA/LATAM/payouts, webhooks) as tools an AI agent can call to build wallet & card solutions.

Built with [FastMCP](https://gofastmcp.com) (Python). Validated against the API contract in [`resource.md`](./resource.md).

## What it can do

The 115 tools are grouped by lifecycle stage so agents can drive a full journey end to end:

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

List every tool with:

```bash
python server.py --list-tools
```

## Configuration

The server reads everything from the environment (no hard-coded endpoints/keys). See [`.env.example`](./.env.example).

| Variable | Required | Description |
|---|---|---|
| `BMONI_BASE_URL` | yes | Base URL of the BMONI Embedded API host |
| `BMONI_API_KEY` | yes | Partner key, sent as `x-api-key` |
| `BMONI_TIMEOUT_SECONDS` | no | HTTP timeout (default 30) |
| `BMONI_TRANSPORT` | no | stdio (default) / http / sse |
| `BMONI_HOST`, `BMONI_PORT` | no | Bind address for http/sse (default 127.0.0.1:8000) |

```bash
cp .env.example .env   # then fill in BMONI_BASE_URL and BMONI_API_KEY
```

## Install & run

Requires Python 3.10+.

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### stdio (desktop MCP clients)

Point your MCP client at the project:

```bash
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
        "BMONI_BASE_URL": "https://<your-bmoni-host>",
        "BMONI_API_KEY": "<your-api-key>"
      }
    }
  }
}
```

### HTTP / SSE (remote agents)

```bash
python server.py --transport http --host 0.0.0.0 --port 8000
# endpoint: http://127.0.0.1:8000/mcp
```

Or run the package directly: `python -m bmoni_mcp --transport http`.

## Typical agent journey

1. `bmoni_users_create` — create the wallet holder.
2. `bmoni_wallets_owner_proof_challenge` + `bmoni_wallets_create_managed` — provision a smart wallet (challenge must be signed by the user's EVM wallet; the agent orchestrates the signing).
3. `bmoni_kyc_update_profile` / `bmoni_kyc_upload_identification` → `bmoni_kyc_activate` → poll `bmoni_kyc_status` — verify identity.
4. `bmoni_rails_start_usa` (or `start_nigeria`/`start_monerium`/…) and `bmoni_rails_provision_usd_vba` — activate a rail.
5. `bmoni_fund_deposit_crypto` — fund the wallet.
6. `bmoni_money_send_account` / `bmoni_money_withdraw_nigeria_bank` — move money; when a tool returns a sign payload, have the owner sign it and submit with `bmoni_money_submit_signature`.

## Layout

```
server.py                  # CLI entry point (stdio/http/sse)
bmoni_mcp/
  config.py                # env-only configuration + fail-fast errors
  api.py                   # async HTTP client (x-api-key), PDF->base64
  models.py                # pydantic bodies for nested payloads
  server.py                # FastMCP assembly + agent instructions
  cli.py / __main__.py     # arg parsing
  tools/
    users.py  kyc.py  wallets.py  rails.py  fund.py
    money.py  cards.py  bank_accounts.py
    info.py  employer.py  webhooks.py
tests/test_server.py       # contract + registration tests (no live API)
```

## Tests

Contract-only validation: tools are registered, schemas are clean, and representative calls produce HTTP requests (method, path, query, JSON body) that match the API reference — using a mocked transport, so no API key or network is needed.

```bash
python tests/test_server.py
```

## Notes

- Endpoints marked internal/HMAC-signed in `resource.md` (e.g. `/v1/internal/*`, receiving webhook events) are intentionally not exposed.
- Binary responses (receipt PDFs) and uploaded files are transported as base64 so they stay JSON-serializable.
- `signature`-bearing flows return the payload/message to sign; cryptographic signing is left to the wallet owner, and the signature is submitted via `bmoni_money_submit_signature`.
