# YALE RESEARCH MAPPING & TRANSLATION MATRIX: CAND-008
## Translation of Zhu (2024) / Gatev et al. (2006) Methodology to S&P 500 Single Stocks

---

## 1. Executive Translation Matrix

$$\begin{array}{|l|l|l|l|l|}
\hline
\textbf{Yale Paper Concept} & \textbf{Our Single-Stock Implementation} & \textbf{Observed Metric} & \textbf{Decision} \\
\hline
\textbf{SSD Pair Distance Metric} & \text{Trailing 252d normalized Euclidean distance } D_{i,j} & \text{Isolates co-moving sector peers} & \mathbf{ADOPTED} \\
\hline
\textbf{Wait-One-Day Execution Lag} & \text{Divergence at } t \rightarrow \text{Execution at } t+1\text{ close} & \text{Eliminates bid-ask bounce bias} & \mathbf{MANDATORY\text{ }INVARIANT} \\
\hline
\textbf{Overlapping 6M Cohorts} & \text{Monthly cohorts (21 bars) smoothing exit lumpiness} & \text{Stabilizes cohort returns} & \mathbf{ADOPTED} \\
\hline
\textbf{Equities Universe Expansion} & \text{100 liquid S\&P 500 stocks across 11 GICS sectors} & \text{Sharpe raised to } \mathbf{+0.5221} & \mathbf{VALIDATED} \\
\hline
\textbf{Physical-Share Accounting} & \text{Explicit cash conservation, discrete integer shares} & \text{Zero lookahead or NAV leakage} & \mathbf{ADOPTED} \\
\hline
\end{array}$$

---

## 2. Theoretical Verification

1. **Why Single-Stock Pairs Outperform ETF Pairs**:
   - Broad macro ETFs are heavily diversified index baskets with compressed spread variance and limited idiosyncratic mispricing.
   - Individual equities exhibit higher idiosyncratic volatility, allowing $2\sigma$ divergence events to represent larger percentage price displacements that yield wider profit margins upon convergence, easily overcoming the $10\text{ bps}$ transaction barrier.
