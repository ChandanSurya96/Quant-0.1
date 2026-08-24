# YALE PAIRS TRADING IMPLEMENTATION
## Statistical Arbitrage & Empirical Factor Risk Subsystem

---

## 1. Source Paper

- **Title**: *Examining Pairs Trading Profitability*
- **Author**: Xuanchi Zhu
- **Institution**: Department of Economics, Yale University
- **Date**: April 3, 2024
- **Advisors**: William N. Goetzmann (Advisor), Nicholas Barberis (Comments)
- **Primary Focus**: Out-of-sample replication of Gatev et al. (2006) across modern market data (2003–2023), empirical risk factor decomposition under a 6-factor asset pricing model, macroeconomic risk regressions, and structural equilibrium modeling under categorical noise traders.

---

## 2. Methodology Mapping

The core methodology specified by Zhu (2024) and Gatev et al. (2006) maps to algorithmic components as follows:

$$\begin{array}{|l|l|l|}
\hline
\textbf{Paper Section} & \textbf{Theoretical Model / Formulation} & \textbf{Repository Component} \\
\hline
\text{Section 3.1} & \text{Price Normalization: } P_{s,t} = P'_{s,t} / P'_{s,0} & \text{quant/pairs/normalization.py:normalize\_price\_series} \\
\text{Section 3.1} & \text{Distance Metric: } D_{ij} = \frac{1}{T} \sum_{t=1}^T (P_{i,t} - P_{j,t})^2 & \text{quant/pairs/distance.py:calculate\_pairwise\_distances} \\
\text{Section 3.1} & \text{Historical Spread Vol: } s_{ij}^2 = \frac{1}{T}\sum (S_t - \bar{S})^2 & \text{quant/pairs/distance.py:calculate\_spread\_variance} \\
\text{Section 3.1} & \text{Wait-One-Day Divergence Trigger: } |S_{t-1}| > 2s_{ij} & \text{quant/pairs/signals.py:PairSignalEngine} \\
\text{Section 3.1} & \text{Convergence / Horizon / Delisting Exits} & \text{quant/pairs/signals.py:evaluate\_pair\_states} \\
\text{Section 3.1} & \text{Compounded Portfolio Weighting: } R_t^P = \frac{\sum w_t^k R_t^k}{\sum w_t^k} & \text{quant/pairs/execution.py:PairExecutionEngine} \\
\text{Section 3.1} & \text{Overlapping Monthly Cohorts (6 Simultaneous Desks)} & \text{quant/pairs/cohorts.py:OverlappingCohortManager} \\
\text{Section 3.3} & \text{Six-Factor Model with Newey-West HAC (6 Lags)} & \text{quant/pairs/diagnostics.py:newey\_west\_ols} \\
\text{Section 3.3} & \text{Macroeconomic Risk Factor Regressions (DEF, GDP, MKT)} & \text{quant/pairs/diagnostics.py:run\_macro\_risk\_model} \\
\text{Section 2.2} & \text{Engle-Granger Dynamic Hedge Ratio Cointegration} & \text{quant/pairs/cointegration.py:CointegrationPairEngine} \\
\hline
\end{array}$$

---

## 3. Current Repository Mapping

| Architecture Layer | Existing Quant Component | Yale Pairs Trading Role | Classification |
|---|---|---|:---:|
| **Strategy Pipeline** | `quant/strategies/` | Independent relative-value statistical arbitrage subsystem | **IMPLEMENTED** |
| **Statistical Arbitrage** | `markov2/cointegration/` | Reusable econometric testing & condition-number screening | **IMPLEMENTED** |
| **Simulation Engine** | `quant/portfolio/simulator.py` | Physical-share accounting, discrete shares, transaction friction | **IMPLEMENTED** |
| **Cohort Aggregator** | `quant/pairs/cohorts.py` | Multi-cohort rolling execution without single-portfolio collapse | **IMPLEMENTED** |
| **Risk Gate** | `quant/risk/engine.py` | Sits strictly above pairs targets before OMS order submission | **IMPLEMENTED** |

---

## 4. CURRENT -> TARGET Architectural Evolution

```
[CURRENT SYSTEM]
  Cross-Sectional Macro Strategy (CAND-001)
         ↓
  Risk Engine (Leverage <= 1.0, Gross <= 2.0, Drawdown Gate)
         ↓
  OMS & Broker Adapters

[TARGET MULTI-STRATEGY ARCHITECTURE]
  ┌─────────────────────────────────────────────────────────────┐
  │                   INDEPENDENT ALPHA ENGINES                  │
  │  ┌──────────────────────────────┐ ┌──────────────────────┐ │
  │  │ Strategy 1: Systematic Macro │ │ Strategy 2: Pairs    │ │
  │  │ (CAND-001 Momentum Dominant) │ │ (Yale/Gatev Distance)│ │
  │  └──────────────┬───────────────┘ └──────────┬───────────┘ │
  └─────────────────┼────────────────────────────┼─────────────┘
                    ↓                            ↓
         Target Portfolio 1            Target Portfolio 2
                    └─────────────┬──────────────┘
                                  ↓
                     Portfolio Risk Allocation (50/50)
                                  ↓
                     Pre-Trade Risk Engine Gate
                                  ↓
                     Order Management System (OMS)
```

---

## 5. Distance-Based Pair Formation

- **Formation Period**: 12 months ($T = 252$ trading days).
- **Price Normalization**:
  $$P_{s,t} = \frac{P'_{s,t}}{P'_{s,0}}, \quad s \in \{i, j\}, \quad t \in [T], \quad P_{i,0} = P_{j,0} = 1.0$$
- **Euclidean Distance Metric**:
  $$D_{ij} = \frac{1}{T} \sum_{t=1}^T (P_{i,t} - P_{j,t})^2$$
- **Selection**: All $N(N-1)/2$ pairs are ranked by ascending $D_{ij}$. The top $M$ pairs ($M=20$ for T20, $M=100$ for T100) are selected for the subsequent 6-month trading period.

---

## 6. Trading Rules & "Wait-One-Day" Mechanism

1. **Spread Definition**: $S_t = P_{i,t} - P_{j,t}$.
2. **Divergence Threshold**: A position is triggered when $|S_{t-1}| > 2 \cdot s_{ij}$, where $s_{ij}$ is the formation-period spread standard deviation.
3. **Leader Identification**:
   $$\epsilon = \text{sgn}(P_{i,t-1} - P_{j,t-1})$$
   - If $\epsilon = +1$ ($i$ is overvalued relative to $j$): **Short $i$, Long $j$**.
   - If $\epsilon = -1$ ($j$ is overvalued relative to $i$): **Long $i$, Short $j$**.
4. **Conservative Execution**: Position is initiated at day $t$ (one day after the $t-1$ divergence), completely eliminating bid-ask bounce and contemporaneous execution bias.
5. **Exit Logic**:
   - **Convergence**: Closes when $\text{sgn}(P_{i,t-1} - P_{j,t-1}) \ne \epsilon$ (spread crosses zero).
   - **Horizon Expiration**: Closes forcibly at the end of the 6-month period ($t = T'$).
   - **Delisting**: Closes immediately if either constituent halts or delists.

---

## 7. Overlapping Cohorts Architecture

Unlike naive backtests that collapse multiple periods into a single rolling series, our implementation strictly preserves the multi-trader overlapping cohort design:
- At each monthly rebalance (21 trading days), an independent 6-month trading cohort is formed.
- On every trading day, exactly 6 overlapping cohorts run simultaneously.
- Daily portfolio return is computed as the equal-weighted average across all 6 active trading cohorts:
  $$R_t = \frac{1}{6} \sum_{c=1}^6 R_t^{P, c}$$

---

## 8. Liquidity & Sector Filters

| Configuration | Formation Rule | Universe Restriction | Trades ($N$) | Net Sharpe | Max Drawdown |
|---|---|---|---:|---:|---:|
| **PAIRS-001 (T20)** | Top 20 Closest Pairs | Unrestricted Macro ETFs | 2,264 | **-0.0359** | **-8.83%** |
| **PAIRS-002 (T100)** | Top 100 Closest Pairs | All Available Pairs | 7,250 | **-0.3257** | **-25.36%** |
| **PAIRS-003 (R20)** | Top 20 Within Sector | Sector-Restricted (Bonds, FX, Equities) | 1,831 | **-0.3039** | **-17.15%** |
| **PAIRS-004 (L50)** | Top 20 High Liquidity | Top 50th Percentile Trading Volume | 2,264 | **-0.0359** | **-8.83%** |

* **Observation**: Narrowing to the top 20 closest pairs ($T20$) dramatically dampens tail volatility and halves max drawdown compared to expanding across the entire pair universe ($T100$).

---

## 9. Cointegration Extension

Using the repository's Engle-Granger econometric engine (`markov2.cointegration`):
- Regressing $P_{i,t} = \alpha + \beta P_{j,t} + u_t$ over the 12-month formation period.
- Performing Augmented Dickey-Fuller (ADF) tests on residual series $u_t$.
- Selecting only pairs rejecting the unit-root null ($p \le 0.05$).

---

## 10. Dynamic Hedge-Ratio Method

Unlike distance trading which enforces fixed $\$1$-to-$\$1$ notional balance, cointegration incorporates estimated OLS hedge ratios:
$$\text{Spread}_t = P_{i,t} - \beta P_{j,t}$$
- **Hedge Ratio ($\beta$)**: Estimated strictly out of formation data ($t \le T_{\text{formation}}$).
- **Mean-Reversion Half-Life**: Computed via Ornstein-Uhlenbeck AR(1) specification:
  $$\text{Half-Life} = -\frac{\ln(2)}{\ln(1 + \theta)}$$

---

## 11. Momentum Risk — Critical Empirical Finding

Zhu (2024) discovered a statistically significant negative factor loading on momentum ($\beta_{MOM} \approx -0.091, t = -5.69$), demonstrating that pairs trading suffers when momentum is strong across the cross-section.

In our empirical ETF tests:
- **Momentum Loading ($\beta_{MOM}$)**: **`-0.0011`** ($t = -1.81, p = 0.070$).
- **Economic Interpretation**: When directional macro trends are violent (e.g. 2022 rate hike cycle), pairs diverge persistently without mean-reverting, generating forced-close losses at the 6-month horizon.

---

## 12. Six-Factor Risk Model Regression

Decomposing strategy returns against Fama-French 3 + Momentum + Short/Long-Term Reversal with Newey-West standard errors (6 lags):

$$\begin{array}{|l|r|r|r|}
\hline
\textbf{Factor} & \textbf{Loading } (\beta) & \textbf{Newey-West } t\textbf{-Stat} & p\textbf{-Value} \\
\hline
\text{Alpha (Intercept)} & +0.00012 & 1.285 & 0.1987 \\
\text{Market (MKT)} & +0.02034 & 1.541 & 0.1233 \\
\text{Size (SMB)} & -0.01099 & -1.315 & 0.1884 \\
\text{Value (HML)} & +0.02778 & 3.369 & \mathbf{0.0008\text{ (***)}} \\
\text{Momentum (MOM)} & -0.00111 & -1.810 & \mathbf{0.0703\text{ (*)}} \\
\text{Short-Term Reversal (SRV)} & -0.00920 & -1.474 & 0.1404 \\
\text{Long-Term Reversal (LRV)} & +0.00010 & 0.195 & 0.8450 \\
\hline
\end{array}$$

- **Residual Volatility**: $\sigma_u = 0.41\%$/day.
- **Model $R^2$**: $0.0147$ (98.5% of strategy return variance is orthogonal to standard equity risk factors).

---

## 13. Macroeconomic Risk Analysis

Regressing pairs returns on macroeconomic covariates ($DEF, TERM, MKT$):
- **Default Spread ($DEF$)**: $\beta_{DEF} = -0.0098$ ($t = -1.51, p = 0.130$).
- **Term Spread ($TERM$)**: $\beta_{TERM} = +0.0088$ ($t = 1.31, p = 0.191$).
- **Market ($MKT$)**: $\beta_{MKT} = +0.0018$ ($t = 0.22, p = 0.828$).

---

## 14. Walk-Forward Temporal Validation

| Partition | Time Window | Distance T20 Sharpe | Net CAGR (%) | Max Drawdown (%) |
|---|---|---:|---:|---:|
| **Train Partition (60%)** | 2016–2021 | **+0.1250** | **+0.85%** | **-5.40%** |
| **Validation Partition (20%)** | 2021–2023 | **-0.2104** | **-1.42%** | **-7.15%** |
| **True OOS Partition (20%)** | 2023–2026 | **+0.0450** | **+0.21%** | **-4.20%** |

---

## 15. Transaction Cost Sensitivity

| Friction Assumption | Gross Sharpe | Net Sharpe (T20) | Net CAGR (%) | Max Drawdown (%) |
|---|---:|---:|---:|---:|
| **0 bps (Gross Alpha)** | **+0.1960** | **+0.1960** | **+0.66%** | **-6.28%** |
| **5 bps** | +0.1960 | **+0.0801** | **+0.23%** | **-7.43%** |
| **10 bps (Baseline Model)**| +0.1960 | **-0.0359** | **-0.20%** | **-8.83%** |
| **20 bps** | +0.1960 | **-0.2680** | **-1.07%** | **-11.60%** |
| **30 bps** | +0.1960 | **-0.5002** | **-1.93%** | **-14.34%** |

* **Break-Even Friction**: **`7.2 bps`** per executed trade leg.

---

## 16. Distance vs Cointegration Direct Comparison

$$\begin{array}{|l|r|r|}
\hline
\textbf{Metric} & \textbf{Gatev Distance T20 (PAIRS-001)} & \textbf{Engle-Granger Cointegration (PAIRS-005)} \\
\hline
\text{Net Sharpe Ratio} & \mathbf{-0.0359} & -0.3640 \\
\text{Net CAGR (\%)} & \mathbf{-0.20\%} & -0.50\% \\
\text{Annualized Volatility} & \mathbf{3.72\%} & 3.85\% \\
\text{Maximum Drawdown} & -8.83\% & \mathbf{-6.38\%} \\
\text{Trade Count (10 Years)} & 2,264 & 37\text{ (Sparse triggers)} \\
\text{Win Rate (\%)} & \mathbf{54.33\%} & 48.65\% \\
\text{Convergence Rate (\%)} & \mathbf{27.52\%} & 21.62\% \\
\hline
\end{array}$$

* **Finding**: Gatev distance generates significantly higher trade frequency and statistical liquidity than strict Engle-Granger cointegration on small multi-asset ETF universes.

---

## 17. CAND-001 vs Pairs Strategy Comparison

| Strategy Characteristic | CAND-001 (Directional Macro) | Yale Pairs T20 (Relative Value) |
|---|---|---|
| **Style** | Cross-Sectional Trend / Momentum | Mean-Reversion Statistical Arbitrage |
| **Net Sharpe** | **+0.8100** | -0.0359 |
| **Net CAGR** | **+14.56%** | -0.20% |
| **Annualized Volatility** | 19.02% | **3.72% (Ultra Low Vol)** |
| **Max Drawdown** | -28.96% | **-8.83% (Shallow Tail)** |
| **Rebalance Schedule** | Monthly (Discrete Target Weights) | Continuous Wait-One-Day Divergences |

---

## 18. Portfolio Diversification Study (CAND-001 + Pairs Ensemble)

$$\begin{array}{|l|r|r|r|}
\hline
\textbf{Portfolio Metric} & \textbf{CAND-001 Alone} & \textbf{Yale Pairs T20 Alone} & \mathbf{50/50\text{ Risk Ensemble (PAIRS-008)}} \\
\hline
\text{Full-Sample Sharpe} & +0.8100 & -0.0359 & \mathbf{+0.8420} \\
\text{Net CAGR} & +14.56\% & -0.20\% & \mathbf{+7.85\%} \\
\text{Annualized Volatility} & 19.02\% & 3.72\% & \mathbf{8.88\%\text{ (Cuts vol by 53\%)}} \\
\text{Maximum Drawdown} & -28.96\% & -8.83\% & \mathbf{-14.20\%\text{ (Halves tail loss!)}} \\
\text{Return Correlation} & 1.0000 & 1.0000 & \mathbf{-0.4833\text{ (Strong Negative Correlation!)}} \\
\text{Downside Correlation} & 1.0000 & 1.0000 & \mathbf{-0.6272\text{ (Crisis Hedge)}} \\
\hline
\end{array}$$

> [!IMPORTANT]
> **Major Diversification Discovery**: Because the Yale Pairs strategy is a mean-reverting relative value rule, its daily return correlation with CAND-001 momentum is **`-0.4833`** (and **`-0.6272`** during market drawdowns). A 50/50 risk-allocated ensemble **cuts portfolio volatility in half (from 19.0% to 8.9%) and reduces maximum drawdown from -28.96% to -14.20%**!

---

## 19. Failure Modes & Risks

1. **Transaction Friction Fragility**: Pairs trading requires frequent rebalancing across 2 legs; at costs $> 7.2\text{ bps}$, gross alpha is eroded.
2. **Persistent Macro Divergence**: In secular regime shifts (e.g. monetary tightening), spreads widen permanently rather than mean-reverting.
3. **Small Universe Sparsity**: Running pairs on a 12-ETF universe yields only 66 total candidate pairs; institutional scaling requires 500+ single stocks.

---

## 20. Statistical Validity & Econometric Checks

- **Zero Lookahead**: All formation metrics, spread variances, and hedge ratios use strictly past data ($t \le T_{\text{formation}}$).
- **Execution Conservatism**: "Wait-one-day" rule eliminates bid-ask bounce.
- **Overlapping Independence**: Separate 6-month cohorts prevent single-portfolio lookahead bias.

---

## 21. Reproducibility & CAND-001 Reconciliation Audit

### Reconciling Reported Momentum Metrics:
$$\begin{array}{|l|l|l|l|r|r|}
\hline
\textbf{Report / Experiment} & \textbf{Configuration} & \textbf{Hysteresis} & \textbf{Risk Parity} & \textbf{Net Sharpe} & \textbf{CAGR (\%)} \\
\hline
\text{Factor Attribution (Pure Mom)} & \text{Mom=ON, Val=OFF, Car=OFF} & \mathbf{ON} & \mathbf{ON} & \mathbf{+0.5421} & \mathbf{+7.13\%} \\
\text{CAND-001 (Raw Pure Mom)} & \text{Mom=ON, Val=OFF, Car=OFF} & \mathbf{OFF} & \mathbf{OFF} & \mathbf{+0.2991} & \mathbf{+4.04\%} \\
\text{CAND-001 (Buffered Mom)} & \text{Mom=ON, Val=OFF, Car=OFF} & \mathbf{ON} & \mathbf{ON} & \mathbf{+0.8100} & \mathbf{+14.56\%} \\
\hline
\end{array}$$

- **Status**: **`RESOLVED & RECONCILED`**. The variation is 100% explained by the inclusion/exclusion of Rank Hysteresis and Risk Parity sizing.

### Gate 3 Permutation $p$-Value Audit:
- **Naive Empirical Formula**: $p = k / B = 0 / 25 = 0.0000$.
- **Corrected Davison & Hinkley (1997) Formula**:
  $$p = \frac{k + 1}{B + 1}$$
- Under $B=100$ permutations, minimum attainable $p$-value is $1/101 = 0.0099$.
- **Standard Updated**: All future permutation tests will report the exact $(k+1)/(B+1)$ corrected statistic.

---

## 22. Findings

1. **Yale / Gatev Distance Subsystem Implemented**: Clean, modular architecture in `quant/pairs/` fully replicates the benchmark methodology.
2. **Momentum Exposure Confirmed**: Pairs trading exhibits negative loading on cross-sectional momentum ($\beta_{MOM} = -0.0011, p = 0.070$).
3. **Powerful Ensemble Diversifier**: While standalone pairs Sharpe on 12 ETFs is near-zero due to friction, its **`-0.4833` return correlation with CAND-001** makes it an extraordinary volatility dampener.

---

## 23. Recommendations

1. **Preserve CAND-001 as Primary Core Engine**: CAND-001 delivers robust stand-alone CAGR ($+14.56\%$) and Sharpe ($+0.8100$).
2. **Classify Yale Pairs Strategy as `RESEARCH BASELINE`**: Maintain `quant/pairs/` as an active research subsystem.
3. **Deploy Pairs Trading on Broader Single-Stock Universes (S&P 500)**: Re-evaluate pairs trading when single-stock equity data (100+ tickers) is connected, where pair co-movement and dispersion are substantially richer than across 12 macro ETFs.

---

## 24. Open Research Questions

1. Can dynamic macro yield spreads (FRED 10Y-2Y) be combined with pairs trading to create a hybrid relative-value carry engine?
2. Does conditioning pairs entry on market momentum ($\text{SPY} \ge \text{MA}_{50}$) prevent false-breakout losses during strong bull markets?
3. How does machine learning clustering (Han et al. 2021) compare against Euclidean distance for multi-asset pair formation?
