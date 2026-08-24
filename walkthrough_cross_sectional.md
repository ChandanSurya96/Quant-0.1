# Cross-Sectional Validation Study — Markov 2.0

### Large-Scale Empirical Test of the 3-State Discrete Markov Regime Framework across 50 Liquid NSE Equities

---

## Executive Summary & Final Verdict

| Metric / Hypothesis Test | Cross-Sectional Finding | Requirement / Benchmark | Status |
| :--- | :--- | :--- | :--- |
| **All-Gate Pass Rate** | **0 / 50 (0.0%)** | All 4 gates passed simultaneously | **REJECTED** |
| **Hypothesis $H_0$ Test** | **$t = -6.2154$ ($p < 10^{-7}$)** | Mean Alpha $\le 0$ | **$H_0$ ACCEPTED** |
| **Mean Sharpe vs Baseline** | **-0.4453** (95% CI: [-0.585, -0.312]) | Must beat `LABEL_ONLY` | **Systematic Degradation** |
| **Transition Memory (9/9 CIs)** | **50 / 50 (100.0%)** of Universe | Cells must depart from Base Rate | **Zero Memory** |
| **Permutation Null Pass Rate** | **2 / 50 (4.0%)** ($\ge 95\text{th}$ percentile) | Type I expectation: 5.0% | **Pure Random Noise** |
| **Log Loss / Calibration** | **Worse on 90.0% of stocks** | $\Delta \text{LogLoss} > 0$ | **Calibration Failure** |

### Mandatory Final Hard Verdict
# **NO EVIDENCE OF EDGE**
*(Null Hypothesis $H_0$ Supported and Cannot Be Rejected)*

> Across a 50-stock liquid universe spanning 10 sectors and 10 years of trading history, the current 20-bar discrete Markov regime framework demonstrates **zero statistically significant predictive alpha**. Adding the discrete transition matrix systematically **destroys risk-adjusted returns** relative to a simple 1-parameter trailing-return momentum baseline ($t = -6.2154$, $p = 8.5 \times 10^{-8}$). The failure is not idiosyncratic to SUZLON or TATAMOTORS; it is a **universal structural property** of single-asset discrete Markov state modeling.

---

## 1. Asset Universe & Methodology

### Universe Construction (50 Liquid NSE Equities)
The universe was constructed deterministically across 10 major industry sectors and market capitalization tiers:

- **Information Technology (5)**: `TCS.NS`, `INFY.NS`, `WIPRO.NS`, `HCLTECH.NS`, `TECHM.NS`
- **Financial Services (8)**: `HDFCBANK.NS`, `ICICIBANK.NS`, `SBIN.NS`, `KOTAKBANK.NS`, `AXISBANK.NS`, `BAJFINANCE.NS`, `BAJAJFINSV.NS`, `INDUSINDBK.NS`
- **Energy & Oil/Gas (5)**: `RELIANCE.NS`, `ONGC.NS`, `BPCL.NS`, `IOC.NS`, `COALINDIA.NS`
- **Utilities & Power (2)**: `NTPC.NS`, `POWERGRID.NS`
- **Automotive (6)**: `MARUTI.NS`, `M&M.NS`, `BAJAJ-AUTO.NS`, `HEROMOTOCO.NS`, `EICHERMOT.NS`, `TMPV.NS` (Tata Motors Passenger Vehicles / TATAMOTORS.NS)
- **Metals & Materials (7)**: `TATASTEEL.NS`, `JSWSTEEL.NS`, `HINDALCO.NS`, `VEDL.NS`, `JINDALSTEL.NS`, `ULTRACEMCO.NS`, `GRASIM.NS`
- **Consumer Staples & FMCG (6)**: `HINDUNILVR.NS`, `ITC.NS`, `NESTLEIND.NS`, `BRITANNIA.NS`, `DABUR.NS`, `MARICO.NS`
- **Consumer Discretionary (1)**: `TITAN.NS`
- **Healthcare & Pharmaceuticals (5)**: `SUNPHARMA.NS`, `DRREDDY.NS`, `CIPLA.NS`, `DIVISLAB.NS`, `APOLLOHOSP.NS`
- **Industrials, Capital Goods & Ports (5)**: `LT.NS`, `ADANIENT.NS`, `ADANIPORTS.NS`, `BEL.NS`, `SUZLON.NS`

### Frozen Framework Configuration
As mandated, zero parameters were optimized or tuned:
- Window: $W = 20$ bars
- Regime Threshold: $\tau = \pm 5\%$
- Signal Threshold: $\theta = 0.10$
- Minimum Training Window: $756$ bars (expanding walk-forward)
- Transaction Cost: $10\text{ bps}$ per unit of position turnover
- States: 3 discrete states (`BEAR` = 0, `SIDEWAYS` = 1, `BULL` = 2)
- Matrix Estimator: Corrected non-overlapping `stride-20` phase-sampled estimator
- Null Benchmarks: 1,000 circular rotations (Primary) and 1,000 i.i.d. shuffles (Secondary)
- Control Baseline: Matrix-free `LABEL_ONLY` trailing-return rule

---

## 2. Transition Memory & The 9/9 Phenomenon

- **Fraction with 9/9 Cells Covering Base Rates**: **50 / 50 (100.0%)**
- **Average Overlapping Diagonal Persistence (Biased)**: **84.17%**
- **Average Stride-20 Diagonal Persistence (Honest)**: **33.49%**
- **Average Persistence Collapse**: **-50.68 percentage points**

Definitive Finding: Across all 50 stocks, **100% of transition probability cells** have 95% Wilson Score confidence intervals that cover the unconditional base rate. The transition matrix contains **zero conditional predictive memory** on single-asset equity return series.

---

## 3. Hypothesis Testing & Statistical Significance

- **Sample Mean Difference**: **-0.4453**
- **Sample Median Difference**: **-0.4257**
- **Bootstrap 95% Confidence Interval for Mean Difference**: **[-0.5854, -0.3124]**
- **One-Sample t-statistic**: **$t = -6.2154$ ($p = 8.5 \times 10^{-8}$)**
- **Proportion of Stocks where Markov Beats Baseline**: **10 / 50 (20.0%)** (Binomial test $p < 10^{-4}$ against null of 50%)

### Permutation Null Distribution Analysis
- **Observed Mean Percentile**: **41.73th percentile**
- **Observed Median Percentile**: **35.80th percentile**
- **Stocks Achieving $\ge 95.0\text{th}$ Percentile**: **2 / 50 (4.0%)**
- **Stocks Achieving $\ge 99.0\text{th}$ Percentile**: **0 / 50 (0.0%)**

---

## 4. Probability Calibration & Predictive Diagnostics

- **Log Loss**: Markov transition probability forecasts are **worse than static unconditional base rates on 90.0% of stocks** (Mean $\Delta \text{LogLoss} = -0.01467$).
- **Brier Score**: Markov forecasts are **worse than static base rates on 88.0% of stocks** (Mean $\Delta \text{Brier} = -0.00592$).
- **Directional Hit Rate**: Mean directional accuracy across active signal bars is **50.93%** (equivalent to random coin tosses).

---

## 5. Sector Breakdown

| Sector | Tickers ($N$) | Avg Markov Net Sharpe | Avg Baseline Net Sharpe | Avg Diff (Markov - Base) | Avg Null Pct | Gate Pass Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Consumer Discretionary** | 7 | +0.340 | +0.883 | **-0.544** | 37.7% | 0.0% |
| **Consumer Staples** | 6 | +0.203 | +0.251 | **-0.048** | 53.2% | 0.0% |
| **Energy** | 5 | -0.043 | +0.659 | **-0.702** | 28.6% | 0.0% |
| **Financials** | 8 | +0.413 | +0.569 | **-0.156** | 63.2% | 0.0% |
| **Healthcare** | 5 | +0.032 | +0.661 | **-0.628** | 14.7% | 0.0% |
| **Industrials** | 5 | +0.310 | +1.114 | **-0.805** | 26.3% | 0.0% |
| **Information Technology** | 5 | +0.360 | +0.791 | **-0.431** | 59.5% | 0.0% |
| **Materials** | 7 | +0.544 | +1.079 | **-0.535** | 34.4% | 0.0% |
| **Utilities** | 2 | +0.540 | +0.712 | **-0.172** | 55.6% | 0.0% |

---

## 6. Answers to Explicit Research Questions

1. **How many of 50 stocks pass all mandatory gates?**  
   **0 out of 50 (0.0%)**.
2. **What percentage fail the permutation null?**  
   **96.0% fail** (48/50 fail the 95th percentile requirement).
3. **What percentage fail the baseline control?**  
   **80.0% fail** (40/50 fail to beat the matrix-free baseline).
4. **How often does Markov beat the matrix-free baseline?**  
   **Only 20.0% of the time** (10/50), significantly below the 50% coin-toss null ($p < 10^{-4}$).
5. **Does the Markov transition matrix show genuine transition memory across the cross-section?**  
   **No**. 100.0% of stocks (50/50) have 9 out of 9 transition cells whose 95% Wilson Score confidence intervals cover unconditional base rates.
6. **Does Markov improve Log Loss/Brier Score versus unconditional prediction?**  
   **No**. Markov probability forecasts degrade Log Loss on 90.0% of stocks and degrade Brier Score on 88.0% of stocks.
7. **Is there evidence of systematic Markov alpha?**  
   **No**. Cross-sectional Markov alpha is strictly negative ($\mu = -0.4453, t = -6.2154$).
8. **Are successful stocks concentrated in particular sectors or market-cap groups?**  
   **No**. Average Markov alpha is negative across all 9 sectors.
9. **Does the cross-sectional evidence support or reject $H_0$?**  
   **$H_0$ is strongly SUPPORTED and CANNOT BE REJECTED**.
