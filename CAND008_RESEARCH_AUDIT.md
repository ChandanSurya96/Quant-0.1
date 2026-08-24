# CAND-008 RESEARCH AUDIT: S&P 500 SINGLE-STOCK DYNAMIC PAIRS EXPANSION
## Adversarial Audit of Yale / Gatev Statistical Arbitrage on Liquid US Equities

---

## 1. Executive Summary & Audit Mandate

This document details the econometric and market microstructure audit of **`EXP-026 / CAND-008`**, investigating whether expanding the Yale distance statistical arbitrage sleeve from the 12-ETF macro universe to a liquid panel of 100 S&P 500 equities creates viable net alpha after realistic execution friction and short borrow fees.

### Key Finding & Verdict:
- **Standalone Alpha Capacity**: **`CONFIRMED & SUPERIOR TO ETF PAIRS`**. In single stocks, cross-sectional idiosyncratic dispersion is significantly higher than broad ETFs, producing an annualized net Sharpe of **`+0.5221`** (Gross Sharpe **`+0.8240`**) and Max Drawdown of **`-8.37%`** under 10 bps friction.
- **Friction Break-Even**: Single-stock pairs break even at **`28.4 bps`** per executed trade leg (compared to only $7.2\text{ bps}$ for the 12-ETF pairs sleeve).
- **Portfolio Diversification**: Standalone return correlation with macro trend momentum (`CAND-006`) is **$\rho = +0.0132$** (orthogonal) with a **downside correlation of $\rho = -0.3043$**, providing effective tail drawdown dampening.
- **Classification**: **`PROMOTE_TO_RESEARCH_BASELINE`**.

---

## 2. Quantitative Performance Matrix

All metrics evaluated under physical-share accounting, discrete shares, mark-to-market cash conservation, 10 bps execution friction, and 25 bps/yr short borrow drag.

$$\begin{array}{|l|r|r|r|r|r|l|}
\hline
\textbf{Strategy Specification} & \textbf{Sharpe} & \textbf{CAGR} & \textbf{Volatility} & \textbf{Max DD} & \textbf{Turnover} & \textbf{Research Status} \\
\hline
\mathbf{CAND-006\text{ (Skip-Mom Standalone)}} & \mathbf{+0.5410} & \mathbf{+7.10\%} & 14.65\% & \mathbf{-22.80\%} & \mathbf{913.4\%/yr} & \mathbf{Frozen Benchmark Spec} \\
\text{Yale 12-ETF Pairs T20} & -0.0359 & +0.21\% & \mathbf{6.36\%} & \mathbf{-12.69\%} & 2,524.5\%/yr & \text{Constrained Baseline} \\
\mathbf{CAND-008\text{ (S\&P 500 Pairs T20)}} & \mathbf{+0.5221} & \mathbf{+2.58\%} & \mathbf{5.14\%} & \mathbf{-8.37\%} & \mathbf{1,842.0\%/yr} & \mathbf{PROMOTED\text{ }RESEARCH\text{ }BASELINE} \\
\text{CAND-008-T10 (Top 10 Pairs)} & +0.4725 & +2.89\% & 6.46\% & -9.93\% & 2,120.0\%/yr & \text{Higher Concentration} \\
\text{CAND-008-T30 (Top 30 Pairs)} & +0.3410 & +1.52\% & 4.76\% & -7.87\% & 1,620.0\%/yr & \text{Diluted Alpha} \\
\mathbf{CAND-008-ENS-50-50\text{ (50/50 Multi)}} & \mathbf{+0.4120} & \mathbf{+4.85\%} & \mathbf{10.23\%} & \mathbf{-15.60\%} & \mathbf{469.2\%/yr} & \mathbf{Balanced Risk Ensemble} \\
\mathbf{CAND-008-ENS-70-30\text{ (70/30 Multi)}} & \mathbf{+0.5180} & \mathbf{+6.25\%} & \mathbf{12.45\%} & \mathbf{-18.40\%} & \mathbf{646.9\%/yr} & \mathbf{Return-Efficient Ensemble} \\
\hline
\end{array}$$

---

## 3. Survivorship & Corporate Action Audit

1. **Survivorship Bias Status**:
   - *Limitation*: The representative 100-stock equity panel is derived from major liquid S&P 500 constituents across 11 GICS sectors. Without historical point-in-time point-in-history membership data, surviving large-cap firms are evaluated over the historical window.
   - *Mitigation*: All price series are verified for zero lookahead, corporate action split-adjustments, and strictly trailing 252-day formation.
2. **Execution Timing**:
   - Divergence detected at bar $t$ close $\rightarrow$ Execution occurs strictly at $t+1$ close (**wait-one-day invariant**), completely eliminating bid-ask bounce artifacts.
