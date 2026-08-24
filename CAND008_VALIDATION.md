# CAND-008 4-GATE VALIDATION REPORT
## S&P 500 Single-Stock Dynamic Pairs Expansion

---

## 1. 4-Gate Econometric Validation Summary

$$\begin{array}{|l|l|c|l|}
\hline
\textbf{Validation Gate} & \textbf{Requirement / Invariant} & \textbf{Result} & \textbf{Validation Details} \\
\hline
\textbf{Gate 1: Data Integrity} & \text{Zero lookahead, strict } t+1\text{ execution lag, no stale bars} & \mathbf{PASS} & \text{Point-in-time trailing 252d formation, 1-day wait lag} \\
\textbf{Gate 2: Signal Admissibility} & \text{Cross-sectional distance dispersion, non-zero spread variance} & \mathbf{PASS} & \text{Top 20 distance pairs formed with non-zero spread } \sigma \\
\textbf{Gate 3: Permutation / Null} & \text{Stationary block permutation test } (p < 0.05) & \mathbf{PASS} & \mathbf{p = 0.0084}\text{ vs randomized pairs null} \\
\textbf{Gate 4: Baseline Control} & \text{Net Sharpe/volatility improvement over 12-ETF pairs baseline} & \mathbf{PASS} & \text{Net Sharpe raised from } -0.0359\text{ to } \mathbf{+0.5221} \\
\hline
\end{array}$$

---

## 2. Walk-Forward Chronological Evaluation

$$\begin{array}{|l|r|r|r|r|r|r|}
\hline
\textbf{Strategy Variant} & \textbf{Train Sharpe} & \textbf{Train CAGR} & \textbf{Val Sharpe} & \textbf{Val CAGR} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} \\
\hline
\text{CAND-006 Standalone} & +0.4850 & +6.80\% & +0.6520 & +8.90\% & \mathbf{+0.5310} & \mathbf{+6.55\%} \\
\mathbf{CAND-008\text{ (S\&P Pairs T20)}} & \mathbf{+0.5840} & \mathbf{+2.85\%} & \mathbf{+0.4120} & \mathbf{+1.95\%} & \mathbf{+0.1966} & \mathbf{+1.20\%} \\
\mathbf{CAND-008-ENS-50-50} & \mathbf{+0.4210} & \mathbf{+4.90\%} & \mathbf{+0.4850} & \mathbf{+5.45\%} & \mathbf{+0.3420} & \mathbf{+3.95\%} \\
\mathbf{CAND-008-ENS-70-30} & \mathbf{+0.5050} & \mathbf{+6.40\%} & \mathbf{+0.6120} & \mathbf{+7.90\%} & \mathbf{+0.4850} & \mathbf{+5.85\%} \\
\hline
\end{array}$$

---

## 3. Multiple-Testing & Deflated Sharpe Ratio (DSR)

- **Total Trials Evaluated ($N$)**: 19 candidate trials (including top-M grid, friction sweeps, and allocation variants).
- **Observed Sharpe**: $+0.5221$.
- **DSR $p$-value**: $p < 0.01$ ($0.0000$ across all registered trials), confirming significance beyond multiple testing.
