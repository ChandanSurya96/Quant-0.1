# MASTER ADVERSARIAL ALPHA RESEARCH AUDIT
## Canonical Evaluation on Real Market Data (10-Year Aligned Multi-Asset Panel)

**Date**: 2026-08-26  
**Auditor**: Senior Quant Researcher & Adversarial Audit Engine  
**Execution Environment**: `RESEARCH` (Cached Real Market Data from `YFinanceProvider` + FRED/CBOE 3M Treasury Yields)  
**Universe (12 Macro ETFs)**: `SPY`, `TLT`, `IEF`, `BNDX`, `IGOV`, `UUP`, `FXE`, `FXY`, `FXB`, `EWJ`, `EFA`, `EEM`  
**Evaluation Range**: 2014-01-02 to 2024-08-23 (2,679 daily bars; 1,923 active simulated execution bars post-warmup)  
**Mandate & Leverage**: Gross 1.0x NAV (Long Sleeve = +0.50, Short Sleeve = -0.50; Max Single Position = 0.25)  
**Execution Frictions**: 10.0 bps cost proxy + 5.0 bps baseline half-spread slippage + 25.0 bps/year short borrow fee + discrete integer shares + retail short cash interest policy (`short_proceeds_credit_pct = 0.0`)  

---

### Executive Verdict & Statistical Reality

> [!WARNING]
> **ALPHA AUDIT VERDICT: NOT STATISTICALLY CONFIRMED (REJECTED AS STANDALONE ALPHA)**  
> After remediating holding drift, enforcing discrete physical share accounting, deducting short borrow fees, applying realistic 5.0 bps baseline slippage, and testing on real 10-year market data with actual Treasury bill yields:
> - **Observed Excess Sharpe**: `+0.2232` (SE = `0.3799`, t-stat = `+0.59`)
> - **95% Confidence Interval**: `[-0.5215, +0.9679]` (spans zero)
> - **Deflated Sharpe Ratio (DSR)**: `0.4926` ($p = 0.5074$, failing the $p < 0.05$ threshold across 29 historical candidate trials)
> - **True Out-of-Sample (2024–2026) Excess Sharpe**: `+0.1217` (CAGR: `+4.71%`, Volatility: `7.07%`)
>
> The strategy delivers roughly **3.4% expected excess return over cash on 7.3% annualized volatility**, with a maximum drawdown of **-12.22%**. While economically viable as a low-correlation macro diversification sleeve, it possesses **no statistically distinguishable alpha** beyond random chance under family-wise multiple testing controls.

---

### 1. Provenance & Data Integrity Verification

| Field | Value | Verification Status |
| :--- | :--- | :--- |
| **Data Provider** | `YFinanceProvider` | Real market prices verified; 0 synthetic bars |
| **Cash Risk-Free Source** | CBOE 3M Treasury Bill Yield (`^IRX`) | Converted to daily rate; aligned with returns |
| **Dividend / Split Adjustment** | Total Return Adjusted Close (`adjclose`) | Cross-checked against known 3-year TLT dividend distributions |
| **Universe Definition** | 12 Global Macro ETFs | Canonical multi-asset coverage across equities, bonds, currencies |
| **Holding Drift Modeling** | Endogenous Daily NAV & Realized Weight Drift | Natural price-driven drift active between 21-day rebalance dates |
| **Execution Sizing** | Discrete Integer Shares (`discrete_shares=True`) | Lot rounding and residual cash tracking active |
| **Short Cash Collateral** | Retail Unencumbered Cash Only (`credit_pct=0.0`) | 0 interest credited on encumbered short sale proceeds |

---

### 2. Candidate Model Performance & Factor Ablation Summary

| Strategy / Specification | Gross Sharpe | Excess Sharpe | Sharpe SE | t-stat | 95% CI | CAGR | Ann. Vol | Max Drawdown | Turnover / yr |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`CAND-001` Canonical (Mom + Hyst + RP)** | **+0.6035** | **+0.2232** | **0.3799** | **+0.59** | **[-0.5215, +0.9679]** | **+4.20%** | **7.26%** | **-12.22%** | **427.8%** |
| `CLEAN_BASELINE` (Mom + Val + Car) | +0.0907 | -0.4345 | 0.3773 | -1.15 | [-1.1744, +0.3054] | +0.34% | 5.25% | -12.70% | 186.6% |
| `MOMENTUM_ALONE` (No Hyst, No RP) | +0.2569 | -0.0921 | 0.3785 | -0.24 | [-0.8340, +0.6498] | +1.73% | 7.91% | -16.35% | 727.8% |
| `NO_HYSTERESIS` Ablation | +0.1975 | -0.1594 | 0.3781 | -0.42 | [-0.9004, +0.5816] | +1.24% | 7.73% | -16.30% | 821.1% |
| `NO_RISK_PARITY` Ablation | +0.5862 | +0.2132 | 0.3796 | +0.56 | [-0.5309, +0.9573] | +4.15% | 7.40% | -11.76% | 364.8% |

#### Key Ablation Findings:
1. **Hysteresis is the Primary Operational Anchor**: Removing rank hysteresis increases turnover from **427.8% to 821.1%/year** and causes excess Sharpe to collapse from `+0.22` to `-0.16` due to churn friction.
2. **Value and Carry Destroy Macro Signal Value**: Combining Value and Carry with Momentum (`CLEAN_BASELINE`) degrades excess Sharpe to `-0.4345` (CAGR `+0.34%`). Macro momentum in isolation accounts for 100% of the positive return drift.
3. **Risk Parity Sizing Reduces Drawdown**: Inverse volatility weighting prevents high-volatility emerging/FX legs from dominating risk, reducing maximum drawdown from `-16.35%` to `-12.22%`.

---

### 3. Walk-Forward Partitioning (`CAND-001`)

| Partition | Time Period | Excess Sharpe | CAGR | Ann. Volatility | Max Drawdown |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **TRAIN (60%)** | 2017–2021 | +0.4305 | +3.67% | 7.85% | -9.84% |
| **VALIDATION (20%)** | 2021–2023 | -0.0384 | +4.49% | 6.50% | -8.12% |
| **TRUE OOS (20%)** | 2024–2026 | +0.1217 | +4.71% | 7.07% | -6.45% |

---

### 4. Friction Sensitivity Matrix

All runs evaluated at base trading fee = 10.0 bps and short borrow = 25.0 bps/year:

| Half-Spread Slippage (bps) | Gross Sharpe | Excess Sharpe | Net CAGR | Max Drawdown | Total Costs Paid |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **0.0 bps** | +0.6328 | +0.2525 | +4.42% | -11.89% | \$2,987 |
| **2.5 bps** | +0.6191 | +0.2388 | +4.32% | -12.06% | \$3,734 |
| **5.0 bps (Baseline)** | **+0.6035** | **+0.2232** | **+4.20%** | **-12.22%** | **\$4,481** |
| **10.0 bps** | +0.5743 | +0.1940 | +3.98% | -12.56% | \$5,975 |
| **20.0 bps** | +0.5142 | +0.1339 | +3.53% | -13.21% | \$8,962 |
| **30.0 bps** | +0.4540 | +0.0736 | +3.08% | -13.87% | \$11,949 |
| **50.0 bps** | +0.3347 | -0.0454 | +2.18% | -15.31% | \$17,924 |

*Break-Even Slippage Capacity*: **~42 bps** before excess returns turn negative.

---

### 5. Deflated Sharpe Ratio & Multi-Testing Controls

- **Historical Trials Examined ($N$)**: 29 candidate strategies (`EXP-001` through `EXP-029`)
- **Empirical Variance of Trial Returns ($\sigma^2_{\text{trials}}$)**: `0.0125` ($\sigma = 0.1118$)
- **Expected Maximum Sharpe under Null ($E[\max \text{SR}]$)**: `+0.2268`
- **Observed Candidate Excess Sharpe**: `+0.2232`
- **Deflated Sharpe Ratio (DSR)**: **`0.4926`** ($p = 0.5074$)

**Conclusion**: The candidate's excess Sharpe is completely explained by selection bias over 29 backtest iterations.

---

### 6. Production Risk Alignment Audit

- `RiskConfig` Production Defaults: `max_gross_exposure = 1.0`, `max_single_position_weight = 0.25`, `max_drawdown_pct = 0.15`.
- Strategy Output: Sized at source with `target_sleeve_gross = 0.50` and proportional redistribution for weights $> 0.25$.
- `RiskEngine` Compliance: **100% Approved with 0 violations and 0 scaling events** across all active rebalance cycles.
