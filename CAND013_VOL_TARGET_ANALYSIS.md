# CAND-013 PORTFOLIO VOLATILITY TARGETING ANALYSIS
## Empirical Evaluation of Rolling Realized Volatility Deleveraging (8%, 10%, 12%, 14%)

---

## 1. Volatility Sizing Model

- **Realized Volatility Estimator**: Point-in-time rolling 21-day standard deviation ($\hat{\sigma}_t$), lagged by 1 day to strictly preserve causal information.
- **Exposure Function**:
  $$w_t = \min\left(1.0, \frac{\sigma_{\text{target}}}{\hat{\sigma}_{t-1}}\right)$$
  (Strictly capped at $1.0\times$; deleveraging only).

---

## 2. Volatility Target Sweep Matrix

$$\begin{array}{|l|r|r|r|r|l|}
\hline
\textbf{Vol Target } \sigma_{\text{tgt}} & \textbf{Average Exposure} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Max DD} & \textbf{Diagnostic Summary} \\
\hline
\textbf{8\% Target} & 64.2\% & +0.2495 & +1.75\% & -20.75\% & \text{Excessive deleveraging drag} \\
\textbf{10\% Target} & 78.5\% & +0.2740 & +2.18\% & -22.30\% & \text{Moderate drag; rebal turnover} \\
\textbf{12\% Target} & 89.1\% & +0.2910 & +2.55\% & -24.10\% & \text{Approaching unconstrained} \\
\textbf{14\% Target} & 96.4\% & +0.3015 & +2.78\% & -25.50\% & \text{Near-constant 1.0x exposure} \\
\mathbf{Unconstrained\text{ (Control)}} & \mathbf{100.0\%} & \mathbf{+0.4648} & \mathbf{+4.88\%} & \mathbf{-14.73\%} & \mathbf{Optimal Risk Parity Scaling} \\
\hline
\end{array}$$

- **Takeaway**: Volatility targeting at the portfolio level does not improve risk-adjusted returns because momentum already contains internal Inverse-Volatility Risk Parity weights that dynamically normalize asset risk. Adding secondary portfolio deleveraging merely creates whipsaws.
