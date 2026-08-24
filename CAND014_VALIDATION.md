# CAND-014 4-GATE VALIDATION & SUCCESS CRITERIA REPORT
## Quantitative Evaluation of Regime Conditioning Hypotheses (EXP-029)

---

## 1. 4-Gate Econometric Validation Summary

$$\begin{array}{|l|l|c|l|}
\hline
\textbf{Validation Gate} & \textbf{Requirement / Invariant} & \textbf{Result} & \textbf{Validation Details} \\
\hline
\textbf{Gate 1: Data Integrity} & \text{Strict } t+1\text{ execution, zero lookahead, point-in-time features} & \mathbf{PASS} & \text{All regime metrics lagged to } t-1 \\
\textbf{Gate 2: Signal Admissibility} & \text{Well-defined non-zero regime multipliers} & \mathbf{PASS} & \text{Multipliers bounded in } [0.50, 1.00] \\
\textbf{Gate 3: Permutation / Null} & \text{Block permutation test } (p < 0.05) & \mathbf{PASS} & \mathbf{p = 0.0048}\text{ vs randomized null} \\
\textbf{Gate 4: Baseline Superiority}& \text{Improvement in OOS Sharpe } (\ge 0.65)\text{ & full Sharpe} & \mathbf{FAIL} & \mathbf{0 / 6}\text{ hypotheses beat Frozen Controls} \\
\hline
\end{array}$$

- **Gate 4 Resolution**: Because regime conditioning universally degrades risk-adjusted returns relative to the unconstrained baseline, `CAND-014` is **FALSIFIED AND REJECTED**.

---

## 2. 10 Hard Success Criteria Audit

$$\begin{array}{|l|c|l|}
\hline
\textbf{Success Criterion} & \textbf{Status} & \textbf{Audit Findings} \\
\hline
\text{1. True OOS Sharpe } \ge +0.65 & \mathbf{FAIL} & \text{Best composite OOS Sharpe is only } +0.1849 - +0.2784 \\
\text{2. True OOS CAGR } \ge \text{Control} & \mathbf{FAIL} & \text{OOS CAGR drops from } +4.65\%\text{ down to } +1.34\% - +2.71\% \\
\text{3. Max Drawdown no worse} & \mathbf{PASS} & \text{Drawdowns slightly compressed via cash drag} \\
\text{4. Survives 10 bps friction} & \mathbf{PASS} & \text{Net returns remain positive but suboptimal} \\
\text{5. No turnover explosion} & \mathbf{PASS} & \text{Turnover held steady via 21d rebalancing} \\
\text{6. DSR Significance } (p \ge 0.95) & \mathbf{FAIL} & \text{DSR } p = 0.0316\text{ (fails multiple-testing gate)} \\
\text{7. Subperiod Stability} & \mathbf{FAIL} & \text{Regime filters miss major post-2020 trend expansions} \\
\text{8. Null Tests Reject Random Labels} & \mathbf{PASS} & \text{Randomized regime label null } p = 0.0035 \\
\text{9. Zero Lookahead Invariant} & \mathbf{PASS} & \text{Confirmed by temporal audit} \\
\text{10. Not Mere Exposure Reduction} & \mathbf{FAIL} & \text{Any return change is entirely due to cash drag} \\
\hline
\end{array}$$
