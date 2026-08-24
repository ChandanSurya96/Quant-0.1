# CAND-013 RESEARCH AUDIT: ASYMMETRIC VOL TARGETING & TURNOVER HYSTERESIS
## Rigorous Falsification Audit of EXP-028 (48 Configurations vs Frozen Control)

---

## 1. Executive Summary & Falsification Verdict

$$\mathbf{CAND-013 = REJECTED\text{ }(0\text{ / }48\text{ CONFIGURATIONS PASSED HARD ELIGIBILITY CRITERIA)}}$$

### Primary Failure Reasons:
1. **Hysteresis Alpha Destruction**: Widening entry thresholds ($\ge 2.2\sigma$) starves the pair formation pipeline, while premature exit thresholds ($0.50\sigma - 1.00\sigma$) truncate convergence gains before overcoming the $10\text{ bps}$ friction barrier.
2. **Volatility Targeting Deleveraging Drag**: Dynamic rolling volatility scaling introduces drag and whipsaw rebalancing turnover during macro trend transitions.
3. **Turnover-Alpha Tradeoff**: Turnover cannot be brought below $5.0\times$/yr without causing OOS Sharpe to collapse below the required $\ge 0.50$ threshold.

---

## 2. Frozen Control vs Best Candidate Comparison

$$\begin{array}{|l|r|r|r|r|r|r|l|}
\hline
\textbf{Specification} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Volatility} & \textbf{Max DD} & \textbf{Turnover} & \textbf{OOS Sharpe} & \textbf{Status} \\
\hline
\mathbf{Frozen\text{ }Control\text{ (ENS-80/20)}} & \mathbf{+0.4648} & \mathbf{+4.88\%} & \mathbf{12.35\%} & \mathbf{-14.73\%} & \mathbf{7.37\times} & \mathbf{+0.5340} & \mathbf{IMMUTABLE\text{ }CONTROL} \\
\text{Best Candidate (E2.0\_X0.50\_V8)} & +0.2495 & +1.75\% & 8.12\% & -20.75\% & 16.60\times & +0.1892 & \mathbf{FAIL\text{ (Criteria Unmet)}} \\
\hline
\end{array}$$

- **Conclusion**: Retain **`ENS-80/20`** as the research baseline. Do NOT deploy hysteresis or volatility targeting to live architecture.
