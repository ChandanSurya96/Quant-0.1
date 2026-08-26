# Environment Variables

Configuration reference for Quant-Algorithm. Every variable is read through
`os.getenv` at dataclass construction time, so changes require a process
restart — nothing re-reads the environment mid-run.

Copy `.env.example` to `.env` (gitignored) and fill in what you need.

<!-- AUTO-GENERATED: env-reference -->

## Market data — Polygon.io

Source: `quant/data/providers/polygon/models.py`

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POLYGON_API_KEY` | **Yes**, when `PolygonProvider` is used | _(none)_ | API key for Polygon.io. `PolygonConfig.validate_credentials()` raises `PolygonAuthenticationError` when empty — the provider is never reachable anonymously and fails closed rather than returning partial data. |
| `POLYGON_BASE_URL` | No | `https://api.polygon.io` | API host override, for proxies or a mock server in tests. |
| `POLYGON_PACE_SECONDS` | No | `0.0` | Float seconds slept between requests. Raise this on rate-limited free tiers. |

Non-env `PolygonConfig` defaults, for reference: `timeout_seconds=10.0`,
`retries=3`, `pause=2.0`, `adjusted=True`, `max_pages=10`.

## Broker — Interactive Brokers

Source: `quant/broker/ibkr/models.py`

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBKR_HOST` | No | `127.0.0.1` | TWS or IB Gateway host. |
| `IBKR_PORT` | No | `7497` | Integer port. Conventionally `7497` TWS paper, `7496` TWS live, `4002` Gateway paper, `4001` Gateway live. |
| `IBKR_CLIENT_ID` | No | `1` | Integer client id. Must be unique per concurrent connection. |
| `IBKR_ACCOUNT` | No | _(empty)_ | Account id used for order routing and reconciliation. |

`IBKRConfig.is_paper` and `live_execution_enabled` are **constructor fields, not
environment variables**, and both default to the safe value. Connecting with
`is_paper=False` while `live_execution_enabled=False` raises
`IBKRLiveSafetyLockedError`.

## Persistence

Source: `quant/persistence/database.py`

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `QUANT_STATE_DB` | No | `:memory:` | SQLite path holding run, order, fill, holding, snapshot, risk, and reconciliation state (`quant/persistence/schema.sql`, `SCHEMA_VERSION = 1`). The `:memory:` default keeps nothing across processes — correct for tests and research, wrong for anything you intend to reconcile or recover. |

## Execution safety boundary

Sources: `quant/runner/live_config.py`, `quant/runner/autonomous_config.py`

These variables interlock; setting one without the others is rejected at
startup rather than silently downgraded. See [RUNBOOK.md](RUNBOOK.md) for the
promotion ladder.

| Variable | Required | Default | Valid values | Description |
|----------|----------|---------|--------------|-------------|
| `BROKER_ENV` | No | `PAPER` | `PAPER`, `LIVE` | Broker environment. Any other value raises `ValueError` — there is no ambiguous default. |
| `LIVE_EXECUTION_ENABLED` | No | `false` | `true`/`1`/`yes` vs anything else | Second condition for live trading. `BROKER_ENV=LIVE` without this raises `ModeViolationError`. |
| `LIVE_CAPITAL_LIMIT` | No | `25000.0` | float > 0 | Hard USD ceiling for controlled live execution. Must be `> 0` in `LIVE`. |
| `EMERGENCY_STOP` | No | `false` | `true`/`1`/`yes` vs anything else | Kill switch. When active, live execution and autonomous enablement are both blocked unconditionally. |
| `APPROVAL_MODE` | No | `MANUAL_APPROVAL` | `MANUAL_APPROVAL`, `AUTONOMOUS` | Order-approval policy. Any other value raises `ValueError`. |
| `AUTONOMOUS_EXECUTION_ENABLED` | No | `false` | `true`/`1`/`yes` vs anything else | Enables unattended cycles. Requires `APPROVAL_MODE=AUTONOMOUS`. |
| `MAX_LIVE_CAPITAL` | **Yes**, for `LIVE` + autonomous | _(unset)_ | float > 0 | Operator-supplied ceiling for autonomous live execution. Unset is a blocking condition — no implicit financial default is permitted. |

Boolean parsing is `value.lower() in ("true", "1", "yes")`. Every other string,
including `"TRUE "` with trailing whitespace, reads as false.

### Interlock rules, as enforced

`AutonomousExecutionConfig.validate_safety_locks()` raises when:

- `BROKER_ENV` is not `PAPER` or `LIVE`
- `APPROVAL_MODE` is not `MANUAL_APPROVAL` or `AUTONOMOUS`
- `AUTONOMOUS_EXECUTION_ENABLED=true` and `APPROVAL_MODE != AUTONOMOUS`
- autonomous + `BROKER_ENV=LIVE` and `LIVE_EXECUTION_ENABLED != true`
- autonomous + `BROKER_ENV=LIVE` and `MAX_LIVE_CAPITAL` is unset or `<= 0`
- `EMERGENCY_STOP=true` and `AUTONOMOUS_EXECUTION_ENABLED=true`

`LiveExecutionConfig.validate_safety_locks()` raises when:

- `BROKER_ENV` is not `PAPER` or `LIVE`
- `BROKER_ENV=LIVE` and `LIVE_EXECUTION_ENABLED != true`
- `BROKER_ENV=LIVE` and `LIVE_CAPITAL_LIMIT <= 0`
- `BROKER_ENV=LIVE` and the instrument whitelist is empty
- `BROKER_ENV=LIVE` and `EMERGENCY_STOP=true`

Non-env live policy constants: `max_live_order_batches_per_day=1`,
`approval_ttl_minutes=15.0`, and a 16-symbol instrument whitelist. Autonomous
adds `max_autonomous_gross_exposure=1.0`,
`max_autonomous_order_batches_per_day=1`, a strategy whitelist of
`systematic_macro_v1` / `systematic_macro`, and
`circuit_breaker_drawdown_limit=-0.15`.

## Notifications

Source: `scripts/send-brief.js`

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | No | _(none)_ | Bot token. Tried first; needs `TELEGRAM_CHAT_ID` set too. |
| `TELEGRAM_CHAT_ID` | No | _(none)_ | Destination chat id. |
| `GMAIL_USER` | No | _(none)_ | Gmail address, used as both sender and recipient. Fallback channel. |
| `GMAIL_APP_PASSWORD` | No | _(none)_ | Gmail app password (not the account password). Requires `nodemailer`, which is **not** in `package.json` — install it before relying on this path. |

With neither channel configured the brief is printed to stdout.

<!-- /AUTO-GENERATED: env-reference -->
