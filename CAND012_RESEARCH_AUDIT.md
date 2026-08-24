# CAND-012 RESEARCH AUDIT: SURVIVORSHIP & BORROW ROBUSTNESS
## Hostile Falsification Audit of S&P 500 Single-Stock Pairs Trading

---

## 1. Executive Summary & Falsification Verdict

This audit presents the adversarial stress test of **`EXP-027 / CAND-012`**, subjecting the single-stock statistical arbitrage sleeve to:
1. Historical survivorship-bias attack (Universes A through E).
2. Systematic tiered borrow drag (0 to 1000 bps/yr).
3. Realistic execution friction sweeps (5 to 50 bps).
4. Strict within-sector pair formation constraints.

### Core Falsification Finding:
- **Standalone Alpha Fragility**: **`FALSIFIED AS INDEPENDENT ALPHA ENGINE`**. When subjected to strict within-sector pairing, 20% random constituent attrition, and realistic borrow drag, standalone single-stock pairs trading net Sharpe drops into negative territory ($-0.1666$ to $-0.3817$). Only the 50 historical-safe mega-cap panel sustains positive standalone Sharpe ($+0.2174$).
- **Multi-Strategy Risk-Dampening Role**: **`CONFIRMED`**. When blended at $70/30$ or $80/20$ with `CAND-006` Momentum, the non-correlated mean-reversion profile successfully cuts portfolio drawdown from $-22.80\%$ to **`-13.52%`** with True OOS Sharpe of **`+0.5147`**.
- **Classification**: **`RETAIN_IN_RESEARCH`** (Preserved as a defensive risk hedge, but rejected as a primary standalone return driver).

---

## 2. Survivorship Stress Performance Matrix

$$\begin{array}{|l|r|r|r|l|}
\hline
\textbf{Universe Formulation} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Max DD} & \textbf{Adversarial Verdict} \\
\hline
\text{Universe A (Baseline 100 Stocks)} & -0.1981 & -1.19\% & -22.30\% & \text{Turnover drag exceeds spread alpha} \\
\mathbf{Universe B\text{ (50 Historical Mega-Caps)}} & \mathbf{+0.2174} & \mathbf{+1.13\%} & \mathbf{-19.94\%} & \mathbf{Survives on liquid continuous names} \\
\text{Universe C (20% Attrition Null)} & -0.1666 & -1.04\% & -14.93\% & \text{Constituent turnover degrades performance} \\
\text{Universe D (Strict Within-Sector Pairs)} & -0.3817 & -1.87\% & -21.11\% & \text{Sector matching compresses spread variance} \\
\text{Universe E (Strict 50% Liquidity Filter)} & -0.1672 & -0.94\% & -17.12\% & \text{Liquidity filtering limits pair opportunities} \\
\hline
\end{array}$$

---

## 3. Multi-Strategy Portfolio Allocation Matrix (with CAND-006)

$$\begin{array}{|l|r|r|r|r|l|}
\hline
\textbf{Allocation (Mom / Pairs)} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Volatility} & \textbf{Max DD} & \textbf{OOS Sharpe} \\
\hline
\text{CAND-006 Alone (100/0)} & +0.5410 & +7.10\% & 14.65\% & -22.80\% & +0.5310 \\
\text{ENS-50-50 (50% Mom / 50% Pairs)} & +0.3187 & +2.18\% & 8.62\% & \mathbf{-11.07\%} & +0.4456 \\
\text{ENS-60-40 (60% Mom / 40% Pairs)} & +0.3844 & +3.10\% & 9.85\% & \mathbf{-12.30\%} & +0.4870 \\
\mathbf{ENS-70-30\text{ (70\% Mom / 30\% Pairs)}} & \mathbf{+0.4308} & \mathbf{+4.00\%} & \mathbf{11.10\%} & \mathbf{-13.52\%} & \mathbf{+0.5147} \\
\mathbf{ENS-80-20\text{ (80\% Mom / 20\% Pairs)}} & \mathbf{+0.4648} & \mathbf{+4.88\%} & \mathbf{12.35\%} & \mathbf{-14.73\%} & \mathbf{+0.5340} \\
\text{ENS-90-10 (90% Mom / 10% Pairs)} & +0.4904 & +5.75\% & 13.50\% & -16.05\% & +0.5480 \\
\hline
\end{array}$$
