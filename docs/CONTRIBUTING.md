# Contributing

Research and execution code for a systematic trading stack. The bar for a
change is not "it runs" — it is "the number it prints is defensible."

## Development environment

### Prerequisites

<!-- AUTO-GENERATED: prerequisites -->
| Requirement | Version | Source |
|-------------|---------|--------|
| Python | `>=3.10` | `pyproject.toml` → `requires-python` |
| Node.js | any LTS with global `fetch` (18+) | `scripts/send-brief.js` |

Runtime dependencies (`pyproject.toml` → `dependencies`):

| Package | Constraint |
|---------|-----------|
| `numpy` | `>=1.24` |
| `pandas` | `>=2.0` |
| `yfinance` | `>=0.2` |
| `matplotlib` | `>=3.7` |

Optional extras (`pyproject.toml` → `optional-dependencies`):

| Extra | Packages | Purpose |
|-------|----------|---------|
| `test` | `pytest>=7.4` | Test suite |
| `enhanced` | `scikit-learn>=1.3` | `markov2 --enhanced` mode |
| `hmm` | `hmmlearn>=0.3` | `markov2 --hmm` mode |

Packaged modules: `markov2`, `quant` (`[tool.setuptools] packages`).
<!-- /AUTO-GENERATED: prerequisites -->

The Polygon provider uses only `urllib` from the standard library — no HTTP
client dependency is required for market data ingestion.

### Setup

```bash
python -m venv .venv
```

```bash
.venv/Scripts/activate
```

```bash
pip install -e ".[test]"
```

```bash
cp .env.example .env
```

Then fill in `.env`. Nothing in `.env` is required to run the test suite —
the defaults in [ENV.md](ENV.md) keep every run in paper/simulation mode.

## Commands

<!-- AUTO-GENERATED: command-reference -->

### Test and framework entry points

| Command | Description |
|---------|-------------|
| `python -m pytest tests/ -q` | Full suite. `testpaths = ["tests"]` is set in `pyproject.toml`, so bare `python -m pytest` is equivalent. |
| `python -m pytest tests/unit -q` | Unit tests only. |
| `python -m markov2.run --ticker SPY` | Markov 2.0 CLI. Prints a DATA / REGIME / STRATEGY / NULL report. |
| `node scripts/send-brief.js "<text>"` | Send a text brief via Telegram, else Gmail, else stdout. |

`package.json` defines no usable scripts — its `test` script is the npm
placeholder stub that exits 1. Use the Python commands above.

### `markov2` CLI flags

`python -m markov2.run [flags]`

| Flag | Default | Description |
|------|---------|-------------|
| `--ticker` | `SPY` | Symbol to fetch. |
| `--years` | `10` | History window. |
| `--window` | `20` | Regime labelling window in bars. |
| `--threshold` | `0.05` | Return threshold for state labelling. |
| `--stride` | `--window` | Stride between sampled windows. |
| `--stride-mode` | `phase` | `phase` or `single`. |
| `--mode` | `filter` | `filter` or `standalone`. |
| `--signal-threshold` | `0.10` | Signal admissibility threshold. |
| `--cap` | `1.0` | Position cap. |
| `--scale` | `0.50` | Position scale. |
| `--min-train` | `756` | Minimum training bars before walk-forward starts. |
| `--cost-bps` | `10.0` | Round-trip transaction cost in bps. |
| `--permutations` | `nulls.DEFAULT_N_PERM` | Permutation-null draw count. |
| `--null-method` | `rotate` | `rotate` (circular rotation) or `iid`. |
| `--no-null` | off | Skip the null. Research only — a result without a null is never tradeable. |
| `--corp-action-threshold` | `gates.CORP_ACTION_THRESHOLD` | Corporate-action detection threshold. |
| `--splice` | _(empty)_ | Comma-separated dates to back-adjust. |
| `--csv` | _(empty)_ | Load OHLCV from a CSV instead of yfinance. |
| `--enhanced` | off | Requires the `enhanced` extra. |
| `--hmm` | off | Requires the `hmm` extra. |
| `--no-plot` | off | Skip chart output. |
| `--macro` | off | Multi-asset macro strategy with Markov gating. |
| `--cointegration` | off | Cointegration subsystem screening. |
| `--benchmark-cointegration` | off | Condition-number and cointegration benchmark suite. |

Output is written to `output/` (gitignored).

### Research scripts

Every script under `scripts/` is a standalone `python scripts/<name>.py`
entry point. None take command-line arguments — parameters are edited in the
script and the run is recorded in `EXPERIMENT_REGISTRY.md`. JSON and CSV
artifacts land in `results/`.

**Candidate strategy engines**

| Script | Description |
|--------|-------------|
| `validate_cand_001.py` | CAND-001 momentum-dominant strategy full validation engine. |
| `run_cand001_deep_audit.py` | Deep adversarial alpha audit, parameter stability, universe leave-one-out, regimes, candidate validations. |
| `run_cand002_single_stock_pairs.py` | CAND-002 broad liquid US equity single-stock pairs subsystem. |
| `run_cand008_research.py` | CAND-008 S&P 500 single-stock dynamic pairs research engine. |
| `run_cand011_research.py` | CAND-011 multi-strategy risk ensemble — skip-month momentum plus Yale distance stat-arb. |
| `run_cand012_research.py` | CAND-012 survivorship-free and borrow-aware single-stock pairs (EXP-027). |
| `run_cand013_research.py` | CAND-013 asymmetric macro-hedged volatility targeting and turnover hysteresis (EXP-028). |
| `run_cand014_research.py` | CAND-014 regime-conditional momentum and Sharpe improvement (EXP-029). |
| `run_dynamic_carry_research.py` | Dynamic carry runner and 4-gate econometric validation against CAND-001-FROZEN-CONTROL-V2. |
| `run_momentum_factor_deep_study.py` | Momentum signal formulations, volatility estimators, hysteresis, rebalance frequencies, short decomposition, Deflated Sharpe Ratio. |

**Audits and integrity checks**

| Script | Description |
|--------|-------------|
| `run_adversarial_audit.py` | Adversarial alpha audit engine for systematic global macro. |
| `run_adversarial_cand001_audit.py` | Adversarial CAND-001 audit and H1–H8 hypothesis testing. |
| `audit_cand_001_reproducibility.py` | CAND-001 reproducibility and Gate 3 permutation p-value calculation. |
| `audit_portfolio_correlation.py` | Portfolio correlation and ensemble mathematics audit. |
| `run_factor_attribution_audit.py` | Factor attribution and ablation under physical-share accounting. |
| `run_physical_share_audit.py` | Physical-share vs legacy forward-filled backtest integrity audit. |
| `compare_legacy_vs_physical.py` | Legacy vectorized vs physical-share simulator parity fixture. Test fixture, not research performance data. |

**Pairs trading**

| Script | Description |
|--------|-------------|
| `run_pairs_distance.py` | Yale / Gatev distance pairs experiments (PAIRS-001 to PAIRS-004). |
| `run_pairs_cointegration.py` | Cointegration pairs experiments (PAIRS-005 to PAIRS-007). |
| `run_pairs_comparison.py` | Portfolio combination and six-factor / macro risk diagnostics (PAIRS-008). |

**Macro strategy**

| Script | Description |
|--------|-------------|
| `evaluate_macro_baseline.py` | Raw unoptimized factor baseline vs optimized strategy (rank hysteresis + risk parity). |
| `optimize_macro_factors.py` | Sweeps momentum (63/126/252/504) × value (252/504/756/1008) windows over 16 parameter pairs; reports TRAIN, VALIDATION, TRUE_OOS Sharpe and OOS degradation. |
| `evaluate_final_macro.py` | End-to-end tear sheet; writes `results/final_macro_equity_curve.png`. |

**Markov 2.0 studies**

| Script | Description |
|--------|-------------|
| `cross_sectional_markov_study.py` | 50-equity cross-sectional validation study of the regime transition matrix. |
| `suzlon_stress_test.py` | Seven-pillar framework stress test on pinned SUZLON.NS data. |
| `tatamotors_stress_test.py` | Seven-pillar framework stress test on pinned TATAMOTORS.NS data. |

<!-- /AUTO-GENERATED: command-reference -->

## Testing

The suite is 342 tests across accounting, broker, drift, factors, integration,
live, observability, OMS, pairs, persistence, reconciliation, risk, runner,
strategies, and unit directories. It runs in roughly 40 seconds and requires
no network access or API keys — data comes from fixtures.

```bash
python -m pytest tests/ -q
```

### Writing tests

- Mirror the package layout: code in `quant/risk/` is tested in `tests/risk/`.
- Use `quant/data/providers/fixture_provider.py` for market data. Do not write
  a test that reaches the network; a test that needs a live vendor is a test
  that will fail in someone else's clone.
- Safety-lock behavior is tested by asserting the exception, not by asserting
  a return value. A config that should refuse to start must raise
  `ModeViolationError` or `ValueError`.
- `filterwarnings = ["error::DeprecationWarning:markov2.*"]` is set in
  `pyproject.toml`: a `DeprecationWarning` raised from `markov2` fails the run.

### Research changes carry a heavier burden

A change to a strategy, factor, or backtest is not done when tests pass. It is
done when the result is reproducible and the claim is falsifiable:

- Record the run in `EXPERIMENT_REGISTRY.md` with a CAND / EXP identifier.
- Report the permutation null. A Sharpe without a null distribution is a
  number, not a finding.
- Compare against the matrix-free baseline, not against zero.
- State whether the result is in-sample, validation, or true out-of-sample.
  The 2023–2026 partition is the OOS holdout and is not for tuning.
- Keep costs on: 10 bps transaction cost and 25 bps short borrow, under
  physical-share simulation (`quant/portfolio/simulator.py`).

Label anything that does not clear its gates `RESEARCH_ONLY`. The repository
already documents a deprecated strategy in the README; a negative result that
is written down honestly is a contribution.

## Code style

There is no enforced linter config and no pre-commit hooks in the repository.
Match what surrounds you:

- `from __future__ import annotations` at the top of every module.
- Type hints on public functions; `X | None` union syntax, not `Optional[X]`.
- `@dataclass(frozen=True)` for configuration; `field(default_factory=...)`
  for anything reading the environment.
- One-line docstrings on modules, classes, and public methods.
- Errors are domain-specific and subclass from `quant/core/exceptions.py`.
  Fail closed: raise rather than return an empty frame or a zero.

A `.ruff_cache/` exists at the parent directory from ad-hoc runs. If you run
`ruff`, treat its output as advisory — do not reformat unrelated files.

## Pull request checklist

- [ ] `python -m pytest tests/ -q` passes in full — 342 tests, no skips added.
- [ ] New behavior has a test in the mirrored `tests/` directory.
- [ ] No network calls or credentials in tests.
- [ ] Any new environment variable is added to `.env.example` and [ENV.md](ENV.md).
- [ ] Safety-lock changes are stated explicitly in the PR body and reviewed
      against [RUNBOOK.md](RUNBOOK.md).
- [ ] Research changes are registered in `EXPERIMENT_REGISTRY.md` with null,
      baseline, and OOS status.
- [ ] Performance claims say whether they are in-sample, validation, or true OOS.
- [ ] No secrets: `.env` stays gitignored, `results/` artifacts contain no keys.
