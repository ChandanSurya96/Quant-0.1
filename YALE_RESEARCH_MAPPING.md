# YALE RESEARCH MAPPING & TRANSLATION MATRIX
## Systematic Translation of Literature Concepts to Quant Architecture

---

## 1. Source Reference

- **Paper Title**: *Examining Pairs Trading Profitability*
- **Author**: Xuanchi Zhu (Department of Economics, Yale University, April 2024)
- **Foundational Benchmark**: Gatev, Goetzmann, and Rouwenhorst (2006)

---

## 2. Master Concept Mapping Table

$$\begin{array}{|l|l|l|l|l|l|}
\hline
\textbf{Yale Literature Concept} & \textbf{Current Quant Implementation} & \textbf{Identified Gap} & \textbf{Proposed Experiment} & \textbf{Empirical Result} & \textbf{Final Decision} \\
\hline
\textbf{Negative Momentum Beta} & \text{Cross-Sectional Momentum in} & \text{Trend momentum was} & \text{PAIRS-008: 50/50 Risk} & \text{Return Correlation } \mathbf{-0.5194}; & \mathbf{ADOPT\text{ }AS} \\
(\beta_{\text{MOM}} \approx -0.091) & \text{CAND-001; Pairs module} & \text{unhedged against mean-} & \text{Ensemble between} & \text{Vol cut from } 19.0\% \rightarrow \mathbf{8.3\%}; & \mathbf{DIVERSIFICATION} \\
\text{Zhu (2024), Sec 3.3} & \text{in quant/pairs/} & \text{reversion drawdowns} & \text{CAND-001 and Pairs} & \text{Max DD: } -29\% \rightarrow \mathbf{-14.2\%} & \mathbf{BASELINE} \\
\hline
\textbf{Overlapping Cohorts} & \text{6 simultaneous cohorts in} & \text{Single-portfolio rolling} & \text{PAIRS-001: Overlapping} & \text{Smooth equity curve;} & \mathbf{IMPLEMENTED} \\
\text{Gatev (2006), Sec 2} & \text{quant/pairs/cohorts.py} & \text{backtest lookahead} & \text{cohort simulation} & \text{Gross Sharpe } +0.1960 & \mathbf{IN\text{ }quant/pairs/} \\
\hline
\textbf{Wait-One-Day Rule} & \text{Positions open at } t \text{ for} & \text{Contemporaneous} & \text{Test 0-day vs 1-day} & \text{Eliminates bounce bias;} & \mathbf{MANDATORY\text{ }IN} \\
\text{Zhu (2024), Sec 3.1} & \text{signals at } t-1 & \text{execution bias} & \text{execution latency} & \text{Realistic execution} & \mathbf{ALL\text{ }STRATEGIES} \\
\hline
\textbf{Skip-Month Momentum} & \text{Single-window 126d} & \text{Short-term 1-month} & \text{EXP-019: Skip-Month} & \text{Evaluates } (t-252 \rightarrow t-21) & \mathbf{TO\text{ }BE} \\
(12-1\text{ Momentum}) & \text{momentum in CAND-001} & \text{reversal contamination} & \text{Momentum (12-1d)} & \text{vs (12-0d)} & \mathbf{TESTED\text{ (P1)}} \\
\hline
\textbf{Risk-Adjusted Momentum} & \text{Raw percentage return} & \text{High-vol assets dominate} & \text{EXP-020: } M_i / \sigma_i & \text{Risk-normalized ranking} & \mathbf{TO\text{ }BE} \\
(M_i / \sigma_i\text{ Vol-Scaled}) & \text{cross-sectional ranking} & \text{cross-sectional scores} & \text{signal ranking} & \text{vs raw momentum} & \mathbf{TESTED\text{ (P1)}} \\
\hline
\textbf{Default Spread Stress} & \text{Static 100\% capital} & \text{No dynamic deleveraging} & \text{CAND-005: Volatility /} & \text{Preserves CAGR } +6.88\% & \mathbf{EXPERIMENTAL} \\
(DEF\text{ macro factor}) & \text{deployment} & \text{during macro stress} & \text{Macro Gated Sizing} & \text{while dampening tail risk} & \mathbf{RESEARCH} \\
\hline
\textbf{Single-Stock Dispersion} & \text{12-ETF macro panel in} & \text{Small pair universe} & \text{CAND-002: S\&P 100} & \text{Break-even friction 28 bps;} & \mathbf{REJECT\text{ }STANDALONE;} \\
(N \ge 100\text{ equities}) & \text{production spec} & \text{(66 candidate pairs)} & \text{Pairs Expansion (4,950 pairs)} & \text{OOS Sharpe } -0.27 & \mathbf{RETAIN\text{ }BASELINE} \\
\hline
\end{array}$$

---

## 3. Methodological Implications for Systematic Macro Strategy

1. **Short-Term Reversal Isolation**: Academic literature (Jegadeesh & Titman 1993, Fama & French 2012, Zhu 2024) establishes that the 1-month trailing return ($t-21$ to $t$) exhibits negative autocorrelation (mean-reversion / bid-ask bounce), whereas medium-term returns ($t-252$ to $t-21$) exhibit strong positive autocorrelation (momentum). CAND-001's raw 126d momentum includes the immediate 1-month return; testing a skip-month $(t-126 \rightarrow t-21)$ formulation is the highest-priority alpha experiment.
2. **Vol-Standardized Signal Ranking**: Rather than ranking assets by unscaled trailing returns $\frac{P_t - P_{t-L}}{P_{t-L}}$, scaling by realized volatility $\frac{R_{t,L}}{\sigma_{t,60}}$ ensures that low-vol fixed income and currencies compete fairly against volatile equities in the cross-sectional ranking.
