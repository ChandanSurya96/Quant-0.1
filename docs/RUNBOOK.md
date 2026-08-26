# Operations Runbook

Operating procedures for the execution stack in `quant/`. Configuration
semantics live in [ENV.md](ENV.md); development workflow in
[CONTRIBUTING.md](CONTRIBUTING.md).

> **There is no live-trading daemon and no CLI entry point for the runners.**
> `python -m markov2.run` is the only `__main__` in the repository. The runners
> (`quant/runner/*.py`) are library classes an operator composes in a session or
> script, passing an explicit `DatabaseManager`, `BrokerAdapter`, and config.
> This is deliberate: there is nothing that can start trading by being launched.

## Safety model

Live execution requires several independent conditions to be true at once.
Each is checked at config construction; none defaults to permissive.

| Gate | Safe default | Enforced in |
|------|--------------|-------------|
| `BROKER_ENV` | `PAPER` | `LiveExecutionConfig`, `AutonomousExecutionConfig` |
| `LIVE_EXECUTION_ENABLED` | `false` | both configs |
| `AUTONOMOUS_EXECUTION_ENABLED` | `false` | `AutonomousExecutionConfig` |
| `APPROVAL_MODE` | `MANUAL_APPROVAL` | `AutonomousExecutionConfig` |
| `EMERGENCY_STOP` | `false` (inactive) | both configs |
| `LIVE_CAPITAL_LIMIT` | `25000.0`, must be `> 0` in LIVE | `LiveExecutionConfig` |
| `MAX_LIVE_CAPITAL` | unset — blocks LIVE autonomous | `AutonomousExecutionConfig` |
| Instrument whitelist | 16 symbols, must be non-empty in LIVE | both configs |
| Order batches per day | `1` | both configs |
| Approval TTL | `15.0` minutes | `ManualApprovalGate` |
| Gross exposure ceiling | `1.0` | `AutonomousExecutionConfig` |
| Circuit-breaker drawdown | `-0.15` | `AutonomousExecutionConfig` |

Failures raise `ModeViolationError` or `ValueError` at startup. A
misconfigured system does not start in a degraded mode — it refuses.

## Promotion ladder

Never skip a rung. Each stage has an artifact that must exist before the next
begins.

### 1. Research (simulation only)

No broker, no credentials. Physical-share simulation via
`quant/portfolio/simulator.py`.

```bash
python scripts/run_cand014_research.py
```

Artifact: JSON in `results/`, a row in `EXPERIMENT_REGISTRY.md`, and an
audit `.md` at the repository root.

### 2. Paper runner

`BROKER_ENV=PAPER`, everything else at defaults. Uses `PaperBroker`
(`quant/broker/paper_broker.py`) or an IBKR paper connection. Compose
`PaperTradingRunner` with a persistent `QUANT_STATE_DB` — `:memory:` discards
the state you are trying to validate.

Artifact: a 30-day deterministic validation via
`Deterministic30DayHarness.run_validation()` (`quant/runner/harness.py`).

### 3. IBKR paper burn-in (P8.5)

Ten real orders against Interactive Brokers Paper.

```
IBKR_HOST=127.0.0.1
IBKR_PORT=7497
IBKR_ACCOUNT=<paper account>
BROKER_ENV=PAPER
```

`IBKRPaperBurnInRunner` re-checks `BROKER_ENV == "PAPER"` in its constructor
and raises `ModeViolationError` otherwise — submission to a live account from
the burn-in path is structurally impossible.

Procedure:

1. Start TWS or IB Gateway in **paper** mode and confirm the port matches
   `IBKR_PORT`. `7497` is TWS paper; `7496` is TWS live.
2. Call `verify_environment()`. It returns an `IBKREnvironmentProof` recording
   `broker_env`, connection status, host, port, `is_paper`, and a redacted
   account (`DU***4567`). Keep this proof — it is the tamper-evident record
   that the burn-in ran against paper.
3. Run `run_10_order_burnin_suite(current_prices)`.
4. Review the `BurnInSummary` and the `BurnInLedgerRepository` rows.

Artifact: the environment proof plus a clean 10-order burn-in summary.

### 4. Autonomous canary (P9.1)

The first rung where autonomous order generation is enabled. Zero tolerance:
a single unexpected result stops the promotion.

```
APPROVAL_MODE=AUTONOMOUS
AUTONOMOUS_EXECUTION_ENABLED=true
BROKER_ENV=PAPER          # promote to LIVE only after a clean paper canary
```

For a LIVE canary, `LIVE_EXECUTION_ENABLED=true` and an explicit
`MAX_LIVE_CAPITAL` greater than zero are both mandatory. There is no implicit
financial default; startup is blocked without one.

`IBKRAutonomousCanaryRunner.execute_canary_order()` re-validates the safety
locks on every call — not just at construction — and rejects the order if
`EMERGENCY_STOP` became active or autonomous execution was disabled since
startup. Each order runs pre-trade reconciliation before submission.

Only strategies in `autonomous_strategy_whitelist`
(`systematic_macro_v1`, `systematic_macro`) are accepted.

Artifact: `CanaryRecord` rows in `CanaryLedgerRepository`.

### 5. Controlled live execution

```
BROKER_ENV=LIVE
LIVE_EXECUTION_ENABLED=true
LIVE_CAPITAL_LIMIT=<explicit, > 0>
APPROVAL_MODE=MANUAL_APPROVAL
IBKR_PORT=7496            # or 4001 for Gateway live
```

`LiveTradingRunner` is a two-phase, human-in-the-loop flow:

1. `prepare_order_preview(...)` — builds the batch, runs risk evaluation, and
   returns a preview. Nothing is transmitted.
2. An operator reviews the preview and grants approval through
   `ManualApprovalGate.grant_approval(...)`. The token expires after
   **15 minutes**.
3. `execute_approved_batch(...)` — submits, but only against a valid,
   unexpired, uninvalidated token.

Approval is per batch. It cannot be reused, and
`invalidate_batch(order_batch_id, reason)` revokes it immediately. One batch
per day, maximum.

## Health checks and monitoring

There is **no HTTP health endpoint and no metrics exporter**. Health is
evaluated in-process before execution is permitted.

`quant/observability/health.py`:

| Function | Checks |
|----------|--------|
| `check_data_health(...)` | Market data freshness and integrity |
| `check_persistence_health(db_manager)` | SQLite reachable, schema intact |
| `check_broker_health(broker)` | Broker adapter connectivity |
| `check_risk_health(...)` | Risk engine state |

Each returns a `ComponentHealth` with `is_healthy` and `to_dict()`. They
compose into a `SystemHealthSnapshot`, whose
**`is_execution_permitted()` is the single question to ask before trading.**
If it is false, do not trade — investigate the failing component.

`IBKRHealthTracker` (`quant/broker/ibkr/health.py`) tracks connection
lifecycle: `record_connected()`, `record_disconnected(error)`,
`record_heartbeat()`, and `check_health()`. A stale heartbeat surfaces a
degraded broker before an order is attempted.

Structured logs come from `StructuredLogger`
(`quant/observability/logging.py`), with run and order context attached via
`quant/observability/context.py`.

## Alerting and escalation

`AlertDispatcher` (`quant/observability/alerts.py`) fans an `Alert` out to
registered sinks. **The only sink shipped is `LoggingAlertSink`, which writes
to the `quant.alerts` logger.** There is no pager, email, or Slack
integration in this repository — if you need one, implement `AlertSink` and
register it with `register_sink()`.

`scripts/send-brief.js` sends ad-hoc text via Telegram or Gmail. It is a
manual notification tool, not wired into the alert path.

### Escalation

| Severity | Condition | Action |
|----------|-----------|--------|
| Critical | Reconciliation break, unexplained fill, position mismatch | Set `EMERGENCY_STOP=true`, restart, then reconcile before anything else |
| Critical | Drawdown breaches `circuit_breaker_drawdown_limit` (`-0.15`) | Halt autonomous execution; do not restart until the cause is understood |
| High | `is_execution_permitted()` false at session start | Do not trade; diagnose the failing `ComponentHealth` |
| High | Broker disconnect mid-session with orders in flight | Reconcile before resubmitting anything — never blind-retry an order |
| Medium | Approval TTL expiring before review completes | Re-run the preview; do not extend the TTL to accommodate a slow review |

## Emergency stop

```bash
echo "EMERGENCY_STOP=true" >> .env
```

Then restart the process. Configs read the environment at construction, so a
running process does not observe the change — **the kill switch is only armed
by a restart.** For a live process you must stop, set the flag, and confirm
that startup now refuses.

With `EMERGENCY_STOP` active:

- `LiveExecutionConfig.validate_safety_locks()` raises in `LIVE`.
- `AutonomousExecutionConfig.validate_safety_locks()` raises whenever
  autonomous execution is enabled.
- `IBKRAutonomousCanaryRunner.execute_canary_order()` rejects every order.

To disarm, remove or set the flag false and restart. Do not disarm before the
reconciliation that follows an emergency stop is complete.

## Rollback

There is no deployment artifact to roll back — rollback means reverting code
and reconciling state.

### Code

```bash
git revert <sha>
```

```bash
python -m pytest tests/ -q
```

Prefer `git revert` over `reset --hard` on `main`; the research audit
Markdown at the repository root is part of the history and should not be
silently rewritten.

### Execution state

State lives in the SQLite database at `QUANT_STATE_DB`
(`quant/persistence/schema.sql`, `SCHEMA_VERSION = 1`), covering runs,
orders, fills, holdings, snapshots, risk evaluations, and reconciliation.

1. Stop the process. Set `EMERGENCY_STOP=true`.
2. Copy the database file before touching it. It is the audit record.
3. Run `RecoveryManager.reconcile_and_recover(...)`
   (`quant/reconciliation/recovery.py`) to rebuild internal state from broker
   truth. Broker truth wins over local state — never edit the database to
   make a mismatch disappear.
4. Confirm `ReconciliationEngine.reconcile(...)` reports no breaks.
5. Only then clear the emergency stop and restart.

Crash-recovery behavior is covered by
`tests/reconciliation/test_crash_recovery.py`.

## Common issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PolygonAuthenticationError: POLYGON_API_KEY is not set` | Key missing or empty | Set `POLYGON_API_KEY` in `.env`. The provider fails closed rather than returning partial data. |
| `ValueError: Ambiguous or invalid BROKER_ENV=...` | Value is not exactly `PAPER` or `LIVE` | Fix the value. Case is normalized via `.upper()`; whitespace is not stripped. |
| `ModeViolationError: LIVE execution blocked: ... requires LIVE_EXECUTION_ENABLED=true` | `BROKER_ENV=LIVE` alone | Both conditions are required by design. Confirm you intend live trading. |
| `ModeViolationError: ... MAX_LIVE_CAPITAL > 0 is mandatory` | Autonomous + LIVE without an explicit ceiling | Set `MAX_LIVE_CAPITAL`. There is no default. |
| `ModeViolationError: Cannot enable autonomous execution while EMERGENCY_STOP is active` | Kill switch armed | Intended. Investigate before disarming. |
| `ModeViolationError: P8.5 Burn-In strictly requires BROKER_ENV=PAPER` | Burn-in attempted against live | Intended. Burn-in never runs against a live account. |
| `IBKRLiveSafetyLockedError` | `is_paper=False` with `live_execution_enabled=False` | Constructor-level lock, separate from env vars. Set both explicitly. |
| Approval rejected as expired | More than 15 minutes since `grant_approval` | Re-run the preview and re-approve. Do not raise the TTL to fit a slow review. |
| State empty after restart | `QUANT_STATE_DB` left at `:memory:` | Set a file path. Anything you intend to reconcile needs durable storage. |
| Connection refused on `127.0.0.1:7497` | TWS/Gateway not running, or API not enabled | Start it; enable the API in settings; confirm paper vs live port. |
| Second batch of the day rejected | `max_live_order_batches_per_day = 1` | Intended. Wait for the next session. |
| `DeprecationWarning` fails a test run | `filterwarnings = ["error::DeprecationWarning:markov2.*"]` | Fix the deprecation in `markov2` rather than suppressing it. |

## Pre-session checklist

- [ ] `python -m pytest tests/ -q` green (342 tests).
- [ ] `EMERGENCY_STOP` is false and intentionally so.
- [ ] `BROKER_ENV` matches the port in `IBKR_PORT`.
- [ ] `QUANT_STATE_DB` points at the intended durable database.
- [ ] `SystemHealthSnapshot.is_execution_permitted()` is true.
- [ ] Prior session reconciled clean, with no open breaks.
- [ ] For LIVE: capital limit set explicitly, and an operator is available to
      approve within the 15-minute TTL.
