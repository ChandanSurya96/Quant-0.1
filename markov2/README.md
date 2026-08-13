# Markov 2.0

Observable Markov regime framework with the statistical guards added after the
August 2026 validation study. Original framework by Roan (@RohOnChain); Markov
2.0 by Lewis Jackson.

```bash
python -m markov2.run --ticker TCS.NS
python -m markov2.run --ticker TMPV.NS --splice 2025-10-14
python -m markov2.run --ticker TCS.NS --csv tests/fixtures/TCS.NS.csv --no-null
```

## What the modules do

| module | role |
|---|---|
| `states.py` | label generation — `label_threshold` is the ±5% / 20-bar rule |
| `matrix.py` | `counts_stride` (corrected) and `counts_overlapping` (legacy, biased) |
| `backtest.py` | walk-forward, incremental signals, costs, turnover |
| `verify.py` | Fix 2 — label verification before anything renders |
| `data.py` | yfinance fetch and `splice` for unadjusted corporate actions |
| `stats.py` | n_eff, Wilson intervals, base-rate lift, percentile/p-value |
| `nulls.py` | circular-rotation permutation null (primary) |
| `baseline.py` | the matrix-free control every result must beat |
| `gates.py` | data / signal / null gates → tradeability status |
| `report.py` | the four report sections |

## The four gates

A result is only called `VALIDATED_AS_TRADEABLE` when all pass:

1. **Data** — no unhandled single bar beyond ±25%. Detected, never auto-spliced:
   a large move can be genuine, and back-adjusting a real one corrupts the
   series just as badly as leaving an artefact in.
2. **Signal** — `max|signal| >= signal_threshold`. TMPV.NS peaks at 0.073
   against a 0.10 gate, so it reports `NO_ADMISSIBLE_SIGNAL` rather than a
   backtest of the flat-position path.
3. **Null** — real Sharpe at or above the 95th percentile of 1,000 circular
   rotations. Rotation preserves state counts, run lengths, autocorrelation and
   stride geometry, breaking only label/return alignment. **i.i.d. shuffling is
   available but is never a gate** — it destroys the autocorrelation, narrows
   the null and produces anti-conservative p-values.
4. **Baseline** — must beat "flat while the trailing 20-bar return ≤ −5%", which
   uses no transition matrix at all.

`NOT_VALIDATED_AS_TRADEABLE` is a statement about **evidence, not correctness**.
Diagnostics stay fully visible; `--no-null` skips the null for research work.

## Why the baseline is mandatory

On TCS.NS the trailing-return rule and the "flat in BEAR" overlay produce
Sharpe 0.5302 — identical to four decimals, because they are the same rule. That
performance is a momentum/volatility effect and calling it Markov alpha is the
specific error this package now prevents.

## Standalone mode

Deprecated. It sat at the 1st percentile of the null on TCS.NS (Sharpe 0.024)
and returned −0.798 on TMPV.NS — worse than randomly rotated labels. Still
callable for reproducibility; emits `DeprecationWarning` and a CLI banner.

## Costs

`--cost-bps` defaults to 10 bps per unit of |position change|. `--cost-bps 0`
restores the original zero-cost convention and reproduces every previously
published number. Gross and net are always reported side by side, with turnover.

## Tests

```bash
python -m pytest tests/ -q
```

Fixtures are pinned OHLCV CSVs, so the suite is deterministic and offline.
`tests/test_markov2.py` pins the verified TCS.NS and TMPV.NS results and asserts
the incremental walk-forward matches a from-scratch rebuild to `rtol=1e-9`.
