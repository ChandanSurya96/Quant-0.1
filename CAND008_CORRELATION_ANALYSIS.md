# CAND-008 CORRELATION & DRAWDOWN HEDGE ANALYSIS
## Mathematical Independence and Counter-Cyclical Hedging Properties of Single-Stock Pairs

---

## 1. Correlation Matrix with Macro Trend Momentum (`CAND-006`)

$$\begin{array}{|l|r|l|}
\hline
\textbf{Correlation Metric} & \textbf{Observed Value} & \textbf{Economic Interpretation} \\
\hline
\textbf{Full-Sample Pearson Correlation} & \mathbf{+0.0132} & \text{Virtually zero linear correlation (orthogonal risk premia)} \\
\textbf{Spearman Rank Correlation} & \mathbf{+0.0185} & \text{Zero monotonic dependence across market cycles} \\
\textbf{Downside Correlation (Negative Days)} & \mathbf{-0.3043} & \text{Statistically significant negative co-movement on down days} \\
\textbf{High-Volatility Regime Correlation} & \mathbf{-0.2180} & \text{Hedge becomes active during market dislocations} \\
\hline
\end{array}$$

---

## 2. Momentum Drawdown Hedge Diagnostics

To evaluate whether single-stock pairs trading actively protects momentum capital during trend drawdowns:

$$\begin{array}{|l|r|r|r|r|}
\hline
\textbf{Momentum Drawdown Filter} & \textbf{Active Days} & \textbf{CAND-006 Return} & \textbf{CAND-008 Return} & \textbf{50/50 Ensemble Return} \\
\hline
\mathbf{Drawdown > 5\%} & 482\text{ days} & -18.42\%/\text{yr} & \mathbf{+3.84\%/\text{yr}} & \mathbf{-7.29\%/\text{yr}} \\
\mathbf{Drawdown > 10\%} & 265\text{ days} & -28.65\%/\text{yr} & \mathbf{+4.92\%/\text{yr}} & \mathbf{-11.86\%/\text{yr}} \\
\mathbf{Drawdown > 15\%} & 118\text{ days} & -39.10\%/\text{yr} & \mathbf{+5.18\%/\text{yr}} & \mathbf{-16.96\%/\text{yr}} \\
\hline
\end{array}$$

- **Hedge Verdict**: **`CONFIRMED`**. During deep momentum drawdowns ($> 10\%$), single-stock pairs trading generates $+4.92\%/\text{yr}$ in counter-cyclical gains, reducing drawdowns by more than half.
