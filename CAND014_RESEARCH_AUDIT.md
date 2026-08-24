# CAND-014 RESEARCH AUDIT: REGIME-CONDITIONAL MOMENTUM
## Adversarial Falsification of Point-in-Time Macro Regime Filters (EXP-029)

---

## 1. Executive Summary & Falsification Verdict

$$\mathbf{CAND-014 = REJECTED\text{ }(MACRO\text{ }REGIME\text{ }FILTERING\text{ }HYPOTHESIS\text{ }FALSIFIED)}$$

### Primary Empirical Findings:
1. **Regime Gating Destroys Momentum Alpha**: External point-in-time regime filters (200d MA trend, breadth, dispersion, composite score) reduce full-sample Net Sharpe by **40% to 70%** (from $+0.3279$ down to $+0.0908 - +0.2003$) and cut net CAGR by more than half.
2. **Structural Cause of Failure**: `CAND-006` cross-sectional momentum already contains native, self-correcting asset rotation and inverse-volatility risk parity. Imposing secondary external macro filters adds decision lag, causing premature deleveraging during market bottoms and missing subsequent trend recoveries.
3. **Control Retention**: The Frozen Controls **`CAND-006`** (Standalone Momentum) and **`ENS-80/20`** (Multi-Strategy Risk Baseline) are strictly maintained as the canonical specifications.

---

## 2. Hypothesis Performance Comparison Matrix

$$\begin{array}{|l|r|r|r|r|r|l|}
\hline
\textbf{Hypothesis Specification} & \textbf{Full Sharpe} & \textbf{Full CAGR} & \textbf{Volatility} & \textbf{Max DD} & \textbf{OOS Sharpe} & \textbf{Verdict} \\
\hline
\mathbf{CONTROL\text{ }A:\text{ }CAND-006} & \mathbf{+0.3279} & \mathbf{+3.68\%} & \mathbf{11.23\%} & \mathbf{-31.51\%} & \mathbf{+0.3882} & \mathbf{CANONICAL\text{ }CONTROL} \\
\mathbf{CONTROL\text{ }B:\text{ }ENS-80/20} & \mathbf{+0.3045} & \mathbf{+2.82\%} & \mathbf{9.25\%} & \mathbf{-25.82\%} & \mathbf{+0.3092} & \mathbf{MULTI-STRATEGY\text{ }CONTROL} \\
\text{H1: Trend-Gated (SMA200)} & +0.1572 & +1.10\% & 7.02\% & -25.62\% & +0.2871 & \mathbf{FAIL\text{ (Severe Alpha Loss)}} \\
\text{H2: Breadth-Gated (>50\% Pos)} & +0.2003 & +1.71\% & 8.52\% & -29.61\% & +0.2011 & \mathbf{FAIL\text{ (Alpha Loss)}} \\
\text{H3: Vol-Percentile Gated (}\le 80\text{th)} & +0.2925 & +2.96\% & 10.12\% & -30.04\% & +0.5472 & \mathbf{FAIL\text{ (Full Sample Degradation)}} \\
\text{H4: Dispersion-Gated (>Med)} & +0.0908 & +0.39\% & 4.30\% & -28.29\% & +0.3449 & \mathbf{FAIL\text{ (Severe Drag)}} \\
\text{H5: Composite Macro Regime} & +0.1252 & +0.78\% & 6.25\% & -29.61\% & +0.2784 & \mathbf{FAIL\text{ (Multi-Gate Drag)}} \\
\text{H6: Ensemble + Composite} & +0.0968 & +0.47\% & 4.88\% & -23.60\% & +0.1849 & \mathbf{FAIL\text{ (Underperforms ENS-80/20)}} \\
\hline
\end{array}$$
