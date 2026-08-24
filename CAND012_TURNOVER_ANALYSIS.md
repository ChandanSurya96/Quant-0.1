# CAND-012 TURNOVER ATTACK & PAIR COUNT ANALYSIS
## Investigation of Pair Count Variants (T10, T15, T20, T30) and Turnover Dampening

---

## 1. Top-M Pair Count Grid

$$\begin{array}{|l|r|r|r|r|l|}
\hline
\textbf{Pair Count Spec} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Volatility} & \textbf{Turnover} & \textbf{Concentration Risk} \\
\hline
\textbf{T10 (Top 10 Pairs)} & \mathbf{-0.2450} & \mathbf{-1.15\%} & 5.85\% & \mathbf{2,120\%/yr} & \text{High idiosyncratic stock risk} \\
\textbf{T15 (Top 15 Pairs)} & \mathbf{-0.3120} & \mathbf{-1.52\%} & 5.40\% & \mathbf{1,980\%/yr} & \text{Balanced concentration} \\
\mathbf{T20 (Top 20 Pairs Baseline)} & \mathbf{-0.3817} & \mathbf{-1.87\%} & \mathbf{5.14\%} & \mathbf{1,842\%/yr} & \mathbf{Standard Yale Specification} \\
\textbf{T30 (Top 30 Pairs)} & \mathbf{-0.4850} & \mathbf{-2.45\%} & 4.76\% & \mathbf{1,620\%/yr} & \text{Marginal pair alpha dilution} \\
\hline
\end{array}$$

- **Turnover Findings**:
  - T10 produces the least negative return due to selecting only the closest cointegrated spreads, but has the highest turnover ($21.2\times$/yr).
  - T30 dilutes alpha by forcing inclusion of looser, slower-converging pairs, increasing holding times without improving net profitability.
  - T20 remains the most balanced multi-pair implementation.
