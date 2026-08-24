# DYNAMIC CARRY RESEARCH REPORT (CAND-010A – CAND-010E)
## Econometric Evaluation of Point-in-Time Yield Curve & Interest Rate Differential Carry

---

## 1. Executive Summary & Research Mandate

This study investigates whether replacing the deprecated static carry dictionary with point-in-time dynamic macro information improves the systematic macro strategy.

### Tested Candidate Specifications:
- **`CAND-010A`**: Dynamic Carry Alone (Yield Curve Term Spreads + Currency Rate Differentials + Equity Dividend Yields).
- **`CAND-010B`**: 50/50 Momentum + Dynamic Carry Composite.
- **`CAND-010C`**: Skip-Month Momentum (6-1) + Dynamic Carry (70/30 Blend).
- **`CAND-010D`**: Asymmetric 50% Short (CAND-009) + Dynamic Carry Blend.
- **`CAND-010E`**: Dynamic Carry as a Macro Regime Overlay Filter.

---

## 2. Empirical Results Table

$$\begin{array}{|l|r|r|r|r|r|l|}
\hline
\textbf{Strategy Specification} & \textbf{Full Sharpe} & \textbf{Full CAGR} & \textbf{Max DD} & \textbf{Turnover} & \textbf{OOS Sharpe} & \textbf{Gate 4 Decision} \\
\hline
\mathbf{CAND-001-FROZEN-CONTROL-V2} & \mathbf{+0.5253} & \mathbf{+6.87\%} & \mathbf{-23.04\%} & \mathbf{893.4\%} & \mathbf{+0.5284} & \mathbf{CANONICAL\text{ }CONTROL} \\
\text{CAND-010A (Dynamic Carry Alone)} & -0.2651 & -6.83\% & -61.00\% & 645.2\% & -0.6900 & \mathbf{REJECT\text{ (Negative Alpha)}} \\
\text{CAND-010B (50/50 Mom + Carry)} & -0.6336 & -13.69\% & -73.66\% & 1120.4\% & -0.8808 & \mathbf{REJECT\text{ (Severe Degradation)}} \\
\text{CAND-010C (70/30 Skip-Mom + Carry)}& -1.0601 & -20.66\% & -83.51\% & 1245.8\% & -1.1157 & \mathbf{REJECT\text{ (Severe Degradation)}} \\
\text{CAND-010D (Asym Short + Carry)} & -0.5539 & -9.30\% & -55.76\% & 812.0\% & -0.8430 & \mathbf{REJECT\text{ (Negative Alpha)}} \\
\text{CAND-010E (Carry Regime Filter)} & -0.5994 & -13.14\% & -67.07\% & 940.5\% & -0.4088 & \mathbf{REJECT\text{ (Filter Lag Drag)}} \\
\hline
\end{array}$$

---

## 3. Econometric Diagnosis & Root Cause Analysis

### Why Dynamic Carry Fails in Multi-Asset Cross-Sectional Ranking:
1. **Cross-Sector Carry Incommensurability**:
   - High dividend yield equities (e.g. Emerging Markets `EEM`) or high nominal yield sovereign debt (`TLT` during rate hike shocks) systematically receive high carry scores.
   - During macroeconomic shifts (such as the 2022 global tightening cycle), these high-carry assets experienced severe capital loss. Cross-sectional ranking forced the strategy into losing assets simply because their trailing yields appeared elevated.
2. **Carry / Momentum Anti-Correlation**:
   - Assets with the highest trailing yields are frequently those experiencing severe price declines (falling price inflates dividend/yield ratios). Blending Carry with Momentum dilutes the pure trend-following signal.
3. **Turnover Explosion**:
   - Combining two distinct signals with different autocorrelation structures increased monthly turnover from $8.9\times$/yr to over $12.5\times$/yr, generating substantial friction drag without adding gross return.

---

## 4. Final Scientific Verdict

$$\mathbf{DYNAMIC\_CARRY\_VERDICT = REJECT}$$

**Formal Conclusion**:
- Dynamic cross-sectional carry is formally **`REJECTED`** as a direct ranking factor for the 12-ETF multi-asset panel.
- In accordance with the Anti-Overfitting Rules, we do not force a broken hypothesis into production.
- The validated strategy architecture is confirmed to be **`MOMENTUM-ONLY + RISK PARITY + RANK HYSTERESIS`** (`CAND-001-FROZEN-CONTROL-V2`, with `CAND-006` and `CAND-009` as active benchmark evolutions).
