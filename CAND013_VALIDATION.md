# CAND-013 4-GATE VALIDATION & FALSIFICATION REPORT
## Evaluation Across 48 Parameter Configurations (EXP-028)

---

## 1. 4-Gate Econometric Validation Summary

$$\begin{array}{|l|l|c|l|}
\hline
\textbf{Validation Gate} & \textbf{Requirement / Invariant} & \textbf{Result} & \textbf{Validation Details} \\
\hline
\textbf{Gate 1: Data Integrity} & \text{Strict } t+1\text{ execution, zero lookahead, conservative universe} & \mathbf{PASS} & \text{No lookahead, prior volatility used} \\
\textbf{Gate 2: Signal Admissibility} & \text{Non-zero trade generation across grid} & \mathbf{PASS} & \text{Trades generated across all } (\sigma_e, \sigma_x) \\
\textbf{Gate 3: Permutation / Null} & \text{Stationary block permutation test } (p < 0.05) & \mathbf{PASS} & \mathbf{p = 0.0052}\text{ vs block randomized null} \\
\textbf{Gate 4: Baseline Superiority}& \text{Improvement in turnover efficiency vs Frozen Control} & \mathbf{FAIL} & \mathbf{0 / 48}\text{ configurations beat Control efficiency} \\
\hline
\end{array}$$

- **Gate 4 Falsification**: Because no configuration satisfied the hard success criteria (Turnover $< 5.0\times$, OOS Sharpe $\ge 0.50$, OOS CAGR $\ge 4.5\%$, Max DD $\ge -15.5\%$), `CAND-013` is **REJECTED**.

---

## 2. Parameter Grid Results Summary Table

$$\begin{array}{|l|c|c|c|r|r|r|r|r|r|l|}
\hline
\textbf{Configuration} & \sigma_e & \sigma_x & \sigma_{\text{vol}} & \textbf{CAGR} & \textbf{Sharpe} & \textbf{OOS CAGR} & \textbf{OOS SR} & \textbf{Max DD} & \textbf{Turnover} & \textbf{Status} \\
\hline
\mathbf{CONTROL\text{ (ENS-80/20)}} & \mathbf{2.0} & \mathbf{0.00} & \mathbf{None} & \mathbf{+4.88\%} & \mathbf{+0.4648} & \mathbf{+5.70\%} & \mathbf{+0.5340} & \mathbf{-14.73\%} & \mathbf{7.37\times} & \mathbf{CONTROL} \\
\text{CFG\_E2.0\_X0.50\_V8} & 2.0 & 0.50 & 8\% & +1.75\% & +0.2495 & +1.20\% & +0.1892 & -20.75\% & 16.60\times & \mathbf{FAIL} \\
\text{CFG\_E2.0\_X0.50\_V10} & 2.0 & 0.50 & 10\% & +2.18\% & +0.2740 & +1.55\% & +0.2150 & -22.30\% & 16.85\times & \mathbf{FAIL} \\
\text{CFG\_E2.0\_X0.50\_V12} & 2.0 & 0.50 & 12\% & +2.55\% & +0.2910 & +1.85\% & +0.2380 & -24.10\% & 17.10\times & \mathbf{FAIL} \\
\text{CFG\_E2.0\_X0.50\_V14} & 2.0 & 0.50 & 14\% & +2.78\% & +0.3015 & +2.05\% & +0.2510 & -25.50\% & 17.30\times & \mathbf{FAIL} \\
\text{CFG\_E2.2\_X0.75\_V8} & 2.2 & 0.75 & 8\% & +1.42\% & +0.2110 & +0.95\% & +0.1540 & -19.80\% & 15.40\times & \mathbf{FAIL} \\
\text{CFG\_E2.5\_X1.00\_V10} & 2.5 & 1.00 & 10\% & +1.10\% & +0.1650 & +0.70\% & +0.1120 & -21.40\% & 13.20\times & \mathbf{FAIL} \\
\text{CFG\_E3.0\_X1.00\_V12} & 3.0 & 1.00 & 12\% & +0.65\% & +0.0980 & +0.35\% & +0.0540 & -22.90\% & 10.50\times & \mathbf{FAIL} \\
\hline
\end{array}$$

---

## 3. Multiple Testing & Deflated Sharpe Ratio (DSR)

- **Total Trials Evaluated ($N$)**: 48 full parameter configurations.
- **Deflated Sharpe Ratio (DSR)**: $p = 1.0000$ (confirms zero statistically significant overperformance vs control).
