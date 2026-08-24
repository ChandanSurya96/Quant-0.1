# CAND-014 TURNOVER & REBALANCE TIMING ANALYSIS
## Assessment of 21-Day Decision Cadence and Implementation Friction

---

## 1. Annualized Turnover Across Hypotheses

$$\begin{array}{|l|r|r|l|}
\hline
\textbf{Specification} & \textbf{Annualized Turnover} & \textbf{Change vs Control} & \textbf{Turnover Mechanism} \\
\hline
\mathbf{CONTROL\text{ }A:\text{ }CAND-006} & \mathbf{9.13\times} & \mathbf{Baseline} & \text{Standard 21d momentum rebalance} \\
\mathbf{CONTROL\text{ }B:\text{ }ENS-80/20} & \mathbf{7.37\times} & \mathbf{Baseline} & \text{80\% Momentum + 20\% Pairs} \\
\text{H1: Trend-Gated} & 6.45\times & -29.3\% & \text{Downscaled trade sizing during downtrends} \\
\text{H2: Breadth-Gated} & 7.10\times & -22.2\% & \text{Downscaled trade sizing} \\
\text{H3: Vol-Percentile Gated} & 8.20\times & -10.2\% & \text{Shock deleveraging} \\
\text{H4: Dispersion-Gated} & 5.12\times & -43.9\% & \text{Compressed exposure sizing} \\
\text{H5: Composite Regime} & 5.85\times & -35.9\% & \text{Multi-tier scaling} \\
\text{H6: Ensemble + Composite} & 5.48\times & -25.6\% & \text{Blended ensemble scaling} \\
\hline
\end{array}$$

- **Takeaway**: By synchronizing regime updates to the native 21-day rebalance cycle, turnover was successfully controlled without daily whipsaws; however, lower turnover was achieved purely via cash drag rather than execution efficiency.
