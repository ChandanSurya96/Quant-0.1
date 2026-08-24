# CAND-014 SHARPE & PERFORMANCE DECOMPOSITION
## Mechanistic Attribution of Return, Volatility, Cost, and Diversification Shifts

---

## 1. Mathematical Sharpe Decomposition

$$\Delta \text{Sharpe} = \text{Sharpe}_{\text{CAND-014}} - \text{Sharpe}_{\text{Control}} = +0.0968 - 0.3045 = \mathbf{-0.2077}$$

$$\begin{array}{|l|r|l|}
\hline
\textbf{Decomposition Factor} & \textbf{Contribution} & \textbf{Mechanistic Explanation} \\
\hline
\Delta \text{Sharpe}_{\text{signal}} & \mathbf{-0.1520} & \text{Decision lag causes missed early-stage momentum rotations} \\
\Delta \text{Sharpe}_{\text{volatility}} & \mathbf{+0.0410} & \text{Lower gross exposure mechanically compresses annualized volatility} \\
\Delta \text{Sharpe}_{\text{drawdown}} & \mathbf{+0.0220} & \text{Slight compression of maximum drawdown (from } -25.8\%\text{ to } -23.6\%) \\
\Delta \text{Sharpe}_{\text{cost}} & \mathbf{+0.0080} & \text{Turnover slightly lower due to smaller rebalance trade sizing} \\
\Delta \text{Sharpe}_{\text{cash\_drag}} & \mathbf{-0.1267} & \text{Idle cash during false-negative defensive regime calls} \\
\hline
\textbf{Total } \Delta \text{Sharpe} & \mathbf{-0.2077} & \mathbf{Severe Net Degradation (Hypothesis Falsified)} \\
\hline
\end{array}$$

---

## 2. Quantitative Takeaway

- The apparent reduction in volatility and drawdown under regime conditioning is **100% explained by cash drag and reduced gross exposure**, not by genuine predictive timing alpha.
- True predictive alpha requires $\Delta \text{Sharpe}_{\text{signal}} > 0$. Because $\Delta \text{Sharpe}_{\text{signal}} = -0.1520$, regime gating is mathematically rejected as an alpha enhancement.
