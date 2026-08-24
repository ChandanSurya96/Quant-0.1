# YALE RESEARCH NOTES: EXAMINING PAIRS TRADING PROFITABILITY
## Academic Literature Review & Methodological Relevance for Quant-Algorithm

---

## 1. Source Reference

- **Title**: *Examining Pairs Trading Profitability*
- **Author**: Xuanchi Zhu
- **Institution**: Department of Economics, Yale University
- **Date**: April 3, 2024
- **Primary Advising**: William N. Goetzmann (Advisor), Nicholas Barberis (Comments)
- **Scope**: Replicating Gatev et al. (2006) across modern US equity data (2003–2023), evaluating 6-factor risk models, macroeconomic sensitivities, liquidity filters, and noisy rational expectations equilibrium under categorical investors.

---

## 2. Executive Summary of Paper Methodology

1. **Formation Period**: 12 months ($T=252$ trading days), price series normalized to $P_{s,0} = 1.0$.
2. **Pair Ranking**: Euclidean sum of squared differences distance $D_{ij} = \frac{1}{T} \sum (P_{i,t} - P_{j,t})^2$.
3. **Trading Rules**:
   - $2\sigma$ historical spread standard deviation divergence trigger ($|P_{i,t-1} - P_{j,t-1}| > 2s_{ij}$).
   - **Wait-one-day conservative execution** (positions open at $t$, one day post divergence signal at $t-1$).
   - Exit when spread crosses 0 (convergence), or at end of 6-month trading period ($T'=126$ days), or upon delisting.
4. **Portfolio Weighting & Overlapping Cohorts**:
   - Buy-and-hold compounded pair weighting within single cohorts: $w_t^k = \prod (1 + R_\tau^k)$.
   - 6 simultaneous overlapping monthly cohorts running concurrently and equal-weighted daily.

---

## 3. Systematic Classification of Paper Findings

$$\begin{array}{|l|l|l|}
\hline
\textbf{Paper Finding / Theme} & \textbf{Empirical Evidence in Paper} & \textbf{Relevance Classification for Quant} \\
\hline
\textbf{Negative Momentum Beta} & \beta_{\text{MOM}} \approx -0.091\text{ (}t = -5.69\text{)} & \mathbf{DIRECTLY\text{ }RELEVANT} \\
\textbf{Overlapping Cohort Design} & \text{Prevents single-portfolio lookahead bias} & \mathbf{DIRECTLY\text{ }RELEVANT} \\
\textbf{Wait-One-Day Execution} & \text{Removes bid-ask bounce contamination} & \mathbf{DIRECTLY\text{ }RELEVANT} \\
\textbf{Macro Factor Exposure} & \text{Default Spread } (DEF)\text{ and Term Spread } (TERM) & \mathbf{POTENTIALLY\text{ }RELEVANT} \\
\textbf{Short-Term Reversal Loading} & \beta_{\text{SRV}} > 0\text{ (captures microstructure bounce)} & \mathbf{POTENTIALLY\text{ }RELEVANT} \\
\textbf{Liquidity Degradation} & \text{Alpha drops significantly after 2008} & \mathbf{POTENTIALLY\text{ }RELEVANT} \\
\textbf{Categorical Noise Trader Model} & \text{Theoretical micro-foundations for co-movement} & \mathbf{NOT\text{ }RELEVANT\text{ (Theory Only)}} \\
\textbf{CRSP Single-Stock Panel} & \text{13,386 US equities with CRSP share codes} & \mathbf{REQUIRES\text{ }NEW\text{ }EXPERIMENT} \\
\hline
\end{array}$$

---

## 4. In-Depth Analysis of Critical Insights

### 1. The Momentum Loading Mechanism ($\beta_{\text{MOM}} < 0$)
- **Finding**: Zhu (2024) demonstrates that statistical arbitrage pairs trading exhibits a strong negative factor loading on momentum ($\beta_{\text{MOM}} \approx -0.091$).
- **Economic Mechanism**: During strong cross-sectional trend regimes (e.g. violent tech rallies or rate hike cycles), divergent pairs continue to drift apart rather than mean-reverting. Pairs traders incur losses as positions reach the 6-month forced liquidation horizon without converging.
- **Quant Application**: This negative loading confirms why Pairs Trading is an exceptional portfolio diversifier against trend-following momentum (`CAND-001`), producing a cross-strategy return correlation of **`-0.5194`**.

### 2. Transaction Cost Sensitivity
- **Finding**: While gross pairs trading alpha appears high ($> 8\%$/yr gross), transaction friction and short borrow costs rapidly erode net returns.
- **Quant Application**: High turnover ($25\times - 30\times$/yr) requires strict break-even friction modeling. On our 12-ETF universe, break-even friction is $7.2\text{ bps}$; on 100 single stocks, it is $28.2\text{ bps}$.

### 3. Asymmetric Macroeconomic Sensitivities
- **Finding**: In recessions and credit stress regimes (widening $DEF$ spreads), pair co-movement breaks down and forced liquidation rates rise.
- **Quant Application**: Points directly toward research hypothesis `CAND-005` (Macro Volatility & Credit Gating) to dynamically de-risk during systemic dislocations.
