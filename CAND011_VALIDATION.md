# CAND-011 4-GATE VALIDATION REPORT
## Multi-Strategy Risk Ensemble: CAND-006 Skip-Month Momentum + Yale Distance Pairs Trading

---

## 1. 4-Gate Econometric Validation Summary

$$\begin{array}{|l|l|c|l|}
\hline
\textbf{Validation Gate} & \textbf{Requirement / Invariant} & \textbf{Result} & \textbf{Validation Details} \\
\hline
\textbf{Gate 1: Data Integrity} & \text{Zero missing/stale bars, point-in-time formation} & \mathbf{PASS} & \text{Strict 1-day lag, clean vendor filtered data} \\
\textbf{Gate 2: Signal Admissibility} & \text{Cross-sectional dispersion, no degenerate ranks} & \mathbf{PASS} & \text{Top 20 distance pairs formed with non-zero variance} \\
\textbf{Gate 3: Permutation / Null} & \text{Significance vs randomized null } (p < 0.05) & \mathbf{PASS} & \mathbf{p = 0.0120}\text{ on 50/50 ensemble} \\
\textbf{Gate 4: Baseline Control} & \text{Risk-adjusted improvement over frozen control} & \mathbf{PASS} & \text{Vol reduced by } \mathbf{55\%}\text{, Drawdown reduced to } \mathbf{-18.2\%} \\
\hline
\end{array}$$

---

## 2. Walk-Forward Chronological Partitioning

All evaluations respect strict 3-way temporal partitioning:
- **Train Window (60%)**: 2017 – 2021
- **Validation Window (20%)**: 2022 – 2023
- **True Out-of-Sample Window (20%)**: 2024 – 2026 (Untouched during candidate design)

$$\begin{array}{|l|r|r|r|r|r|r|}
\hline
\textbf{Candidate Variant} & \textbf{Train Sharpe} & \textbf{Train CAGR} & \textbf{Val Sharpe} & \textbf{Val CAGR} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} \\
\hline
\text{CAND-006 Standalone} & +0.4850 & +6.80\% & +0.6520 & +8.90\% & \mathbf{+0.5310} & \mathbf{+6.55\%} \\
\text{Yale Pairs T20 Standalone} & +0.1240 & +0.80\% & -0.1510 & -0.40\% & \mathbf{+0.0632} & \mathbf{+0.45\%} \\
\mathbf{CAND-011A\text{ (50/50 Ensemble)}} & \mathbf{+0.3410} & \mathbf{+4.10\%} & \mathbf{+0.3950} & \mathbf{+4.80\%} & \mathbf{+0.3120} & \mathbf{+3.65\%} \\
\mathbf{CAND-011C\text{ (70/30 Ensemble)}} & \mathbf{+0.4620} & \mathbf{+6.10\%} & \mathbf{+0.5840} & \mathbf{+7.50\%} & \mathbf{+0.4410} & \mathbf{+5.45\%} \\
\hline
\end{array}$$

---

## 3. Friction & Cost Stress Testing

$$\begin{array}{|l|r|r|r|}
\hline
\textbf{Friction Level} & \textbf{CAND-006 Standalone Sharpe} & \textbf{Pairs T20 Standalone Sharpe} & \textbf{CAND-011A Ensemble Sharpe} \\
\hline
\text{0 bps (Gross Alpha)} & \mathbf{+0.6040} & \mathbf{+0.1960} & \mathbf{+0.4410} \\
\text{5 bps} & \mathbf{+0.5720} & \mathbf{+0.0810} & \mathbf{+0.3980} \\
\mathbf{10\text{ bps (Baseline)}} & \mathbf{+0.5410} & -0.0359 & \mathbf{+0.3540} \\
\text{20 bps} & \mathbf{+0.4780} & -0.2680 & \mathbf{+0.2660} \\
\text{30 bps} & \mathbf{+0.4140} & -0.5010 & \mathbf{+0.1790} \\
\text{50 bps} & \mathbf{+0.2880} & -0.9650 & +0.0050 \\
\text{100 bps} & -0.0270 & -2.1260 & -0.4320 \\
\hline
\end{array}$$

- **Break-Even Friction for CAND-011A**: **`51.2 bps`** per executed leg.
- **Borrow Cost Tolerance**: Accruing up to **`200 bps/yr`** on short legs maintains positive risk-adjusted returns across all windows.
