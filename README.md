# Quant-Algorithm: Systematic Macro Strategy & Markov 2.0 Research Framework

This repository contains quantitative research and trading pipelines comprising:
1. **Systematic Global Macro Strategy:** Cross-sectional relative-value allocation (Momentum / Value / Carry) across multi-asset ETFs.
2. **Markov 2.0 Statistical Framework:** Discrete Markov regime detection, rigorous econometric gating (data integrity, signal admissibility, permutation null distributions), and cointegration testing.

---

## 1. Systematic Global Macro Strategy (Production Baseline)

The primary tradeable framework is a systematic global macro strategy trading a universe of 12 liquid ETFs across 4 asset classes:
* **Equities:** SPY (US), EWJ (Japan), EFA (Developed), EEM (Emerging)
* **Bonds:** TLT (20+ Yr US), IEF (7-10 Yr US), BNDX (Total Intl Hedged), IGOV (Intl Treasury)
* **Currencies:** UUP (USD), FXE (EUR), FXY (JPY), FXB (GBP)
* **Commodities:** GLD (Gold), DBC (Commodity Index), USO (Oil), CORN (Corn)

### Signal Architecture
Monthly cross-sectional scoring combines three fundamental factor families:
* **Momentum:** 12-month trailing total return
* **Value:** 3-year z-score mean reversion (inverted)
* **Carry:** Asset-specific income/yield proxies and interest rate differentials

Signals are normalized cross-sectionally (z-scores) and equally weighted to construct a market-neutral / relative-value portfolio: Long the Top 4 assets and Short the Bottom 4 assets with inverse-volatility risk parity sizing.

---

## 2. Empirical Validation & Deprecation of the Markov Gate

### Initial Hypothesis
The Markov 2.0 regime filter was originally designed as a single-asset time-series risk overlay: projecting discrete transition probability matrices out-of-sample (walk-forward) to reject Long allocations entering BEAR regimes and Short allocations entering BULL regimes.

### Empirical Verdict: NO EVIDENCE OF EDGE (Deprecated)
As comprehensively documented in [walkthrough_cross_sectional.md](file:///c:/Quant/Quant-Algorithm/walkthrough_cross_sectional.md), a large-scale empirical study across 50 liquid equities over 10 years of walk-forward history resulted in the **formal rejection of the Markov regime overlay**:

| Hypothesis / Metric | Cross-Sectional Empirical Finding | Required Gate | Status |
| :--- | :--- | :--- | :--- |
| **All-Gate Pass Rate** | **0 / 50 (0.0%)** | 4/4 gates passed simultaneously | **REJECTED** |
| **Alpha vs Matrix-Free Baseline** | **$t = -6.2154$ ($p = 8.5 \times 10^{-8}$)** | Mean $\Delta\text{Sharpe} > 0$ | **Systematic Degradation** |
| **Transition Memory (9/9 CIs)** | **50 / 50 (100.0%)** cover base rate | Cells must depart from base rates | **Zero Memory** |
| **Permutation Null Pass Rate** | **2 / 50 (4.0%)** | $\ge 95\text{th}$ percentile vs null | **Pure Noise** (matches 5% $\alpha$) |

**Key Takeaway:** The single-asset Markov transition matrix exhibits zero conditional memory—9/9 transition cells fall within binomial confidence intervals of unconditional base rates. Adding the Markov gate systematically degrades risk-adjusted returns compared to the matrix-free trailing-return baseline.

**Status:** The Markov regime overlay is **empirically deprecated for live execution** and retained strictly as a rigorous statistical audit framework and baseline comparison harness.

---

## 3. Run Instructions

Requires Python 3.9+ and dependencies (`yfinance`, `numpy`, `pandas`, `scipy`, `statsmodels`, `matplotlib`).

```bash
# Run the Systematic Global Macro baseline strategy
python -m markov2.run --macro

# Run single-asset Markov 2.0 audit and econometric gates on a ticker
python -m markov2.run --ticker SPY

# Run Cointegration screening and validation benchmarks
python -m markov2.run --cointegration
python -m markov2.run --benchmark-cointegration

# Run unit and regression test suite
python -m pytest tests/ -q
```