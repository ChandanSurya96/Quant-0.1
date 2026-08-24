# CAND-014 OUT-OF-SAMPLE (OOS) TEMPORAL ANALYSIS
## Walk-Forward Partitioning Across Train (60%), Val (20%), and True OOS (20%)

---

## 1. Walk-Forward Results Matrix

$$\begin{array}{|l|r|r|r|r|r|r|}
\hline
\textbf{Specification} & \textbf{Train Sharpe} & \textbf{Train CAGR} & \textbf{Val Sharpe} & \textbf{Val CAGR} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} \\
\hline
\mathbf{CONTROL\text{ }A:\text{ }CAND-006} & \mathbf{+0.4850} & \mathbf{+6.80\%} & \mathbf{+0.6520} & \mathbf{+8.90\%} & \mathbf{+0.3882} & \mathbf{+4.65\%} \\
\mathbf{CONTROL\text{ }B:\text{ }ENS-80/20} & \mathbf{+0.4320} & \mathbf{+4.55\%} & \mathbf{+0.5210} & \mathbf{+5.75\%} & \mathbf{+0.3092} & \mathbf{+2.91\%} \\
\text{H1: Trend-Gated} & +0.2105 & +1.85\% & +0.3120 & +2.80\% & +0.2871 & +2.70\% \\
\text{H2: Breadth-Gated} & +0.2450 & +2.30\% & +0.2840 & +2.50\% & +0.2011 & +1.76\% \\
\text{H3: Vol-Percentile Gated} & +0.3105 & +3.20\% & +0.3450 & +3.60\% & \mathbf{+0.5472} & \mathbf{+6.57\%} \\
\text{H4: Dispersion-Gated} & +0.1240 & +0.65\% & +0.1820 & +1.10\% & +0.3449 & +3.20\% \\
\text{H5: Composite Regime} & +0.1650 & +1.20\% & +0.2240 & +1.65\% & +0.2784 & +2.71\% \\
\text{H6: Ensemble + Composite} & +0.1120 & +0.55\% & +0.1450 & +0.85\% & +0.1849 & +1.34\% \\
\hline
\end{array}$$

- **OOS Verdict**:
  - `H6_ENSEMBLE_COMPOSITE` True OOS Sharpe collapsed to **`+0.1849`** (vs $+0.3092$ for Control B).
  - Even though `H3_VOL_REGIME` showed isolated strength in OOS ($+0.5472$), its full-sample Sharpe ($+0.2925$) fails to beat the unconstrained control ($+0.3279$).
