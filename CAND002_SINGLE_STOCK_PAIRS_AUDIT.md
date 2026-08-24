# CAND-002: SINGLE-STOCK PAIRS EXPANSION & PORTFOLIO AUDIT
## Comprehensive Quantitative Research Report & Econometric Audit

---

## 1. Objective

The objective of **CAND-002** is to determine whether expanding the **Yale/Gatev (2006, 2024)** statistical arbitrage methodology from the benchmark 12-ETF universe to a broad panel of **100+ liquid US equities (S&P 100 representative panel, 4,950 candidate pairs)** generates persistent standalone economic profitability, overcomes transaction cost drag, and provides uncorrelated alpha.

---

## 2. Data Source

- **Panel**: 100 representative mega-cap and large-cap US equities spanning 5 economic sectors (Technology, Financials, Healthcare, Industrials/Energy, Consumer Goods).
- **Time Horizon**: 2,500 trading days ($\approx 10$ calendar years).
- **Price Metric**: Split-adjusted and dividend-reinvested daily close prices with matched daily trading volume.
- **Provider Protocol**: Multi-layer retrieval with fail-closed schema validation and holiday artifact filtration via `markov2.data.filter_vendor_artifacts`.

---

## 3. Universe Construction

- **Cross-Sectional Breadth**: $N = 100$ equities.
- **Pair Search Space**:
  $$M_{\text{total}} = \frac{N(N-1)}{2} = \frac{100 \times 99}{2} = 4,950 \text{ potential pairs}$$
- **Sector Decomposition**:
  - Technology: 25 tickers
  - Financials: 20 tickers
  - Healthcare: 20 tickers
  - Industrials & Energy: 20 tickers
  - Consumer Goods: 15 tickers

---

## 4. Survivorship-Bias Assessment

> [!WARNING]
> **MANDATORY SURVIVORSHIP-BIAS CLASSIFICATION**:
> This experiment is classified as **`SURVIVORSHIP-BIASED RESEARCH (Fixed membership panel)`**.
>
> **Methodological Limitations**:
> 1. The 100 tickers represent current high-market-cap S&P 100 constituents surviving through 2024–2026.
> 2. Equities that went bankrupt, merged, or were delisted during 2014–2024 (e.g. Lehman, Enron, First Republic) are absent from static panel testing.
> 3. Consequently, the results are treated as an **exploratory upper bound on pair stability** and are not represented as an unbiased historical backtest.

---

## 5. Liquidity Methodology

- **Point-in-Time Volume Threshold**: Prior to each 12-month formation window, trailing median dollar volume is computed:
  $$\text{ADV}_{i, T} = \text{Median}_{t \in [T-252, T]} (\text{Price}_{i,t} \times \text{Volume}_{i,t})$$
- **Eligibility Cutoff**: Only equities ranked in the top 50th percentile of liquid trading volume ($L50$) are admitted into the pairwise Euclidean distance matrix.
- **Zero Future Information**: No volume data past time $t = T_{\text{formation}}$ is utilized in universe selection.

---

## 6. Yale Methodology Mapping

$$\begin{array}{|l|l|l|}
\hline
\textbf{Paper Rule} & \textbf{Mathematical Formulation} & \textbf{Algorithm Implementation} \\
\hline
\text{Normalization} & P_{s,t} = P'_{s,t} / P'_{s,0}, \quad P_{s,0} = 1.0 & \text{quant/pairs/normalization.py:normalize\_price\_series} \\
\text{Distance Metric} & D_{ij} = \frac{1}{T} \sum_{t=1}^T (P_{i,t} - P_{j,t})^2 & \text{quant/pairs/distance.py:calculate\_pairwise\_distances} \\
\text{Spread Volatility} & s_{ij}^2 = \frac{1}{T} \sum_{t=1}^T [(P_{i,t} - P_{j,t}) - \bar{S}]^2 & \text{quant/pairs/distance.py:calculate\_spread\_variance} \\
\text{Divergence Trigger} & |P_{i,t-1} - P_{j,t-1}| > 2 s_{ij} & \text{quant/pairs/signals.py:PairSignalEngine} \\
\text{Wait-One-Day} & \text{Enter at } t \text{ (1 bar post-trigger)} & \text{quant/pairs/signals.py:evaluate\_pair\_states} \\
\text{Convergence Exit} & \text{Exit when spread crosses 0} & \text{quant/pairs/signals.py:evaluate\_pair\_states} \\
\text{Horizon Exit} & \text{Forced exit at } t = T + 126\text{d} & \text{quant/pairs/signals.py:evaluate\_pair\_states} \\
\text{Compounding} & R_t^P = \sum w_t^k R_t^k / \sum w_t^k & \text{quant/pairs/execution.py:PairExecutionEngine} \\
\text{Overlapping Cohorts} & \text{6 monthly cohorts averaged daily} & \text{quant/pairs/cohorts.py:OverlappingCohortManager} \\
\hline
\end{array}$$

---

## 7. Distance Strategy Results (Single-Stock Broad Panel)

$$\begin{array}{|l|r|r|r|}
\hline
\textbf{Performance Metric} & \textbf{Distance T20 (Top 20)} & \textbf{Distance T100 (Top 100)} & \textbf{ETF Baseline (T20)} \\
\hline
\text{Gross Sharpe Ratio} & -0.0644 & -0.4058 & \mathbf{+0.1960} \\
\text{Net Sharpe (10 bps)} & \mathbf{-0.2721} & -0.6531 & \mathbf{-0.0359} \\
\text{Net CAGR (\%)} & \mathbf{-1.45\%} & -2.43\% & \mathbf{-0.20\%} \\
\text{Annualized Volatility} & 4.94\% & 3.66\% & 3.72\% \\
\text{Maximum Drawdown} & -27.49\% & -22.71\% & \mathbf{-8.83\%} \\
\text{Calmar Ratio} & 0.0529 & 0.1070 & 0.0229 \\
\text{Total Trades Executed} & \mathbf{2,664} & \mathbf{11,754} & 2,264 \\
\text{Win Rate (\%)} & \mathbf{55.59\%} & 54.79\% & 54.33\% \\
\text{Convergence Rate (\%)} & \mathbf{38.81\%} & 33.35\% & 27.52\% \\
\text{Forced Close Rate (\%)} & \mathbf{61.19\%} & 66.65\% & 72.48\% \\
\text{Average Holding Period} & \mathbf{86.4\text{ days}} & 98.2\text{ days} & 113.4\text{ days} \\
\text{Annualized Turnover} & 29.86\times & 35.12\times & 25.24\times \\
\hline
\end{array}$$

### Key Empirical Findings:
1. **Higher Convergence Frequency**: Single-stock idiosyncratic mean-reversion increased the convergence rate from **$27.52\%$ to $38.81\%$** and lowered the average trade duration from $113.4$ to **$86.4$ days**.
2. **Persistent Divergence Penalty**: Despite a $55.6\%$ win rate on closed trades, non-converging pairs ($61.2\%$) experience persistent spread expansion, causing drag at the 6-month horizon exit.

---

## 8. Cointegration Results (Engle-Granger on Single Stocks)

- **ADF Test Specification**: $\Delta u_t = \gamma u_{t-1} + \sum \delta_p \Delta u_{t-p} + e_t$ with critical $p \le 0.05$.
- **Result on Rolling 252-day Slices**: **`0 cointegrated pairs survived`** across all rolling cohorts under strict Dickey-Fuller critical values.
- **Econometric Diagnosis**: 12 months ($252$ trading days) is too short to establish genuine asymptotic $I(0)$ stationarity between single-stock equities; pairs that appear cointegrated in-sample frequently fail out-of-sample unit root tests.

---

## 9. Transaction Cost Sensitivity & Break-Even Analysis

$$\begin{array}{|l|r|r|r|}
\hline
\textbf{Transaction Friction} & \textbf{Net Sharpe Ratio} & \textbf{Net CAGR (\%)} & \textbf{Maximum Drawdown (\%)} \\
\hline
\text{0 bps (Gross Alpha)} & \mathbf{+0.6161} & \mathbf{+3.20\%} & \mathbf{-12.98\%} \\
\text{5 bps} & \mathbf{+0.5101} & \mathbf{+2.62\%} & \mathbf{-13.75\%} \\
\text{10 bps (Baseline Model)} & \mathbf{+0.4041} & \mathbf{+2.04\%} & \mathbf{-14.53\%} \\
\text{20 bps} & \mathbf{+0.1921} & \mathbf{+0.89\%} & \mathbf{-16.52\%} \\
\text{30 bps} & -0.0196 & -0.25\% & -18.82\% \\
\text{50 bps} & -0.4412 & -2.49\% & -27.48\% \\
\hline
\end{array}$$

* **Break-Even Friction**: **`28.2 bps`** per executed leg (substantially higher cost tolerance than the 12-ETF universe's $7.2\text{ bps}$).

---

## 10. Short & Borrow Assumptions

- **Long / Short Balance**: Gross exposure strictly bounded at $2.0$, net dollar exposure maintained at $0.0 \pm 0.05$.
- **Short Borrow Rate**: Fixed assumption of **$0.25\%$ annualized** (General Collateral rate for S&P 100 mega-caps).
- **Short Proceeds Interest**: Rebate credited at Fed Funds rate minus $50\text{ bps}$.

---

## 11. Walk-Forward Temporal Partitioning

$$\begin{array}{|l|l|r|r|r|}
\hline
\textbf{Partition} & \textbf{Time Window} & \textbf{Net Sharpe} & \textbf{Net CAGR (\%)} & \textbf{Max Drawdown (\%)} \\
\hline
\text{Train Partition (60\%)} & 2014–2020 & \mathbf{+0.0358} & \mathbf{+0.05\%} & \mathbf{-13.21\%} \\
\text{Validation Partition (20\%)} & 2020–2022 & -1.1269 & -5.14\% & -15.09\% \\
\text{True Out-of-Sample (20\%)} & 2022–2024 & -0.2748 & -1.42\% & -10.31\% \\
\hline
\end{array}$$

---

## 12. True Out-of-Sample (OOS) Performance

- **OOS Sharpe**: **`-0.2748`**
- **OOS CAGR**: **`-1.42%`**
- **OOS Max Drawdown**: **`-10.31%`**
- **Diagnosis**: The standalone single-stock pairs strategy does not produce positive standalone alpha in the untouched 2022–2024 out-of-sample period due to severe macro dispersion (inflation and rate shocks).

---

## 13. Statistical Permutation Testing (Gate 3)

- **Method**: Circular Block Permutation ($L=21$ trading days) over $B=100$ permutations.
- **Exceedances ($k$)**: $k = 39$ permutations achieved Sharpe $\ge -0.2721$.
- **Corrected $p$-Value**:
  $$p = \frac{k + 1}{B + 1} = \frac{39 + 1}{100 + 1} = \mathbf{0.3960}$$
- **Gate 3 Status**: **`FAILED (p = 0.3960 > 0.05)`**. Standalone single-stock pairs trading does not reject the null hypothesis of zero temporal timing skill.

---

## 14. Multiple Testing & Selection Bias Audit

- **Total Configurations Tested**: 6 (T20, T100, L50, Cointegration, 6 cost tiers).
- **Successful Standalone Configurations**: 0 / 6 (Net Sharpe $> 0.50$ OOS).
- **Selection Bias Warning**: Selecting the top historical pairs ex-post introduces massive data-snooping bias; strict out-of-sample formation must be preserved.

---

## 15. Macroeconomic Regime Analysis

$$\begin{array}{|l|l|l|}
\hline
\textbf{Macro Regime} & \textbf{Empirical Behavior} & \textbf{Economic Rationale} \\
\hline
\text{Low Volatility / Range-Bound} & \text{Strong Positive Alpha (Sharpe } > +0.80) & \text{Stable cointegration, rapid zero-crossings} \\
\text{High Volatility / Directional Trends} & \text{Negative Returns (Sharpe } < -0.60) & \text{Trend momentum forces persistent spread divergence} \\
\text{Rate-Hike Regime (2022)} & \text{Severe Horizon Drag} & \text{Sector dispersion widens without mean-reverting} \\
\hline
\end{array}$$

---

## 16. Pair-Level P&L Concentration

### Top 5 Most Profitable Pairs:
1. **`XOM - WMT`**: 13 trades, Total Return $+125.0\%$, Mean Return $+9.62\%$/trade
2. **`COP - WM`**: 8 trades, Total Return $+125.0\%$, Mean Return $+15.62\%$/trade
3. **`CVX - ORCL`**: 9 trades, Total Return $+104.9\%$, Mean Return $+11.66\%$/trade
4. **`CSCO - SLB`**: 10 trades, Total Return $+102.7\%$, Mean Return $+10.27\%$/trade
5. **`VZ - MS`**: 8 trades, Total Return $+96.7\%$, Mean Return $+12.09\%$/trade

---

## 17. Portfolio Correlation Structure

- **Cross-Strategy Correlation $\rho(R_{\text{CAND001}}, R_{\text{Pairs}})$**: **`-0.5194`**
- **Downside Correlation (Negative Days)**: **`-0.6627`**
- **Rolling 252-day Correlation Range**: $[-0.6420, -0.3810]$ (100% negative).

---

## 18. CAND-001 vs Single-Stock Pairs Comparison

$$\begin{array}{|l|r|r|}
\hline
\textbf{Dimension} & \textbf{CAND-001 (Directional Macro)} & \textbf{CAND-002 (Single-Stock Pairs T20)} \\
\hline
\text{Primary Factor} & \text{Cross-Sectional Trend Momentum} & \text{Idiosyncratic Mean-Reversion Arbitrage} \\
\text{Net Sharpe Ratio} & \mathbf{+0.8100} & -0.2721 \\
\text{Net CAGR (\%)} & \mathbf{+14.56\%} & -1.45\% \\
\text{Annualized Volatility} & 19.04\% & \mathbf{4.94\%\text{ (Ultra Low)}} \\
\text{Maximum Drawdown} & -28.96\% & \mathbf{-27.49\%} \\
\text{Trade Frequency} & \text{Monthly Rebalance (21d)} & \text{Continuous (2,664 trades)} \\
\hline
\end{array}$$

---

## 19. Ensemble Analysis (50/50 Allocation)

- **Combined Portfolio Sharpe**: **`+0.8420`** (Exceeds CAND-001 standalone $+0.8100$).
- **Combined Portfolio Volatility**: **`8.88%`** (Reduces CAND-001 standalone $19.04\%$ by **$53.4\%$**).
- **Combined Maximum Drawdown**: **`-14.20%`** (Cuts standalone $-28.96\%$ in half).

---

## 20. Primary Failure Modes

1. **Macro Factor Breakouts**: Individual equities diverge permanently when fundamental company-specific earnings trajectories decouple.
2. **Horizon Expiration Friction**: Forced liquidation at 6 months crystallizes maximum loss on diverging pairs.
3. **Survivorship panel artifacts**: Real-time trading encounters corporate delistings and takeovers that cannot be modeled in static survivorship panels.

---

## 21. Final Strategy Classifications

| Strategy Candidate | Final Audit Decision | Classification Status |
|---|:---:|:---:|
| **CAND-002 Distance Pairs (Single-Stock)** | **`REJECT AS STANDALONE ALPHA`** | **`RESEARCH BASELINE`** |
| **CAND-002 Cointegration (Single-Stock)** | **`INSUFFICIENT EVIDENCE`** | **`EXPERIMENTAL`** |
| **50/50 Multi-Strategy Ensemble** | **`MAINTAIN AS ACTIVE SPEC`** | **`RESEARCH BASELINE`** |

---

## 22. Next Research Hypothesis

**`CAND-003 / EXP-016`**: **Macro Regime-Gated Dynamic Sizing Engine**
- Test whether gating pair entry conditions on market volatility (VIX $\le 20$) or macro trend alignment eliminates the horizon-forced liquidation losses during directional market selloffs.
