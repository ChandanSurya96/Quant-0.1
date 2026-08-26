# MASTER ADVERSARIAL ALPHA RESEARCH AUDIT
## Canonical Evaluation on Real Market Data (10-Year Aligned Multi-Asset Panel)

**Date**: 2026-08-26  
**Auditor**: Senior Quant Researcher & Adversarial Audit Engine  
**Execution Environment**: `RESEARCH` (Cached Real Market Data from `YFinanceProvider` + CBOE 3M Treasury Bill Index `^IRX`)  
**Universe (12 Macro ETFs)**: `SPY`, `TLT`, `IEF`, `BNDX`, `IGOV`, `UUP`, `FXE`, `FXY`, `FXB`, `EWJ`, `EFA`, `EEM`  
**Evaluation Range**: 2016-08-26 to 2026-08-25 (2,512 aligned daily bars; 1,756 active execution bars post 756-bar warmup)  
**Mandate & Leverage**: Option (b) Gross 1.0x NAV (Long Sleeve = +0.50, Short Sleeve = -0.50; Max Single Position = 0.25)  
**Execution Frictions**: 10.0 bps cost proxy + 5.0 bps baseline half-spread slippage + 25.0 bps/year short borrow fee + discrete integer shares + retail short cash interest policy (`short_proceeds_credit_pct = 0.0`)  

---

### Executive Verdict & Statistical Reality

> [!WARNING]
> **ALPHA AUDIT VERDICT: REJECTED (CANNOT CLAIM STANDALONE ALPHA)**  
> Derived automatically by the audit engine from statistical evidence:
> - **Observed Excess Sharpe (over RF)**: `+0.2232` (SE = `0.3799`, $t = +0.59$)
> - **95% Confidence Interval**: `[-0.5215, +0.9679]` (spans zero)
> - **Deflated Sharpe Ratio (DSR)**: **`0.4926`** ($p = 0.5074$, failing the $p < 0.05$ threshold across 29 historical candidate trials)
> - **True Out-of-Sample (2024–2026) Excess Sharpe**: `+0.1217` (CAGR: `+4.71%`, Volatility: `7.07%`, Max DD: `-6.45%`)
>
> Sized at **Gross 1.0x NAV**, the strategy produces **3.4% expected excess return over cash on 7.3% annualized volatility**, with a maximum historical drawdown of **-12.22%**. While economically viable as a low-correlation macro diversifier, it possesses **no statistically confirmed alpha** beyond random chance under multiple testing controls.

---

### 1. Provenance, Data Sourcing & Methodology Notes

| Parameter | Specification | Verification & Methodology Notes |
| :--- | :--- | :--- |
| **Data Provider** | `YFinanceProvider` (Yahoo v8 Chart API) | Real total-return prices (`adjclose`) with dividend reinvestment; verified on TLT (2021-2023 total return $-32.50\%$ vs price $-37.23\%$). 0 synthetic bars. |
| **Risk-Free Rate Source** | CBOE 3M Treasury Bill Index (`^IRX`) | Converted to decimal annual rate and aligned daily. Note: `^IRX` reflects annualized bank discount yield; bond-equivalent yield $Y_{\text{BEY}} \approx \frac{d}{1 - d \times 0.25}$ represents a minor known basis difference (~5–10 bps at 5% rate). |
| **Gross Sizing Mandate** | Option (b) Gross 1.0x NAV | +0.50 Long / -0.50 Short with iterative proportional redistribution for weights $> 0.25$. |
| **Holding Drift Modeling** | Endogenous Physical Share Tracking | Natural price-driven weight drift active between 21-day rebalance dates. |
| **Execution Sizing** | Discrete Integer Shares | `floor(w * NAV / P)` lot rounding with residual cash tracking. |
| **Short Cash Interest** | Retail Collateral Policy (`credit_pct=0.0`) | 0% interest credited on encumbered short-sale proceeds; interest credited only on unencumbered cash. |

---

### 2. Candidate Model Performance & Factor Ablation Summary

| Strategy / Specification | Gross Sharpe | Excess Sharpe | Sharpe SE | t-stat | 95% Confidence Interval | CAGR | Ann. Vol | Max DD | Turnover / yr |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`CAND-001` Canonical (Mom + Hyst + RP)** | **+0.6035** | **+0.2232** | **0.3799** | **+0.59** | **[-0.5215, +0.9679]** | **+4.20%** | **7.26%** | **-12.22%** | **427.8%** |
| `CLEAN_BASELINE` (Mom + Val + Car) | +0.0907 | -0.4345 | 0.3773 | -1.15 | [-1.1744, +0.3054] | +0.34% | 5.25% | -12.70% | 186.6% |
| `MOMENTUM_ALONE` (No Hyst, No RP) | +0.2569 | -0.0921 | 0.3785 | -0.24 | [-0.8340, +0.6498] | +1.73% | 7.91% | -16.35% | 727.8% |
| `NO_HYSTERESIS` Ablation | +0.1975 | -0.1594 | 0.3781 | -0.42 | [-0.9004, +0.5816] | +1.24% | 7.73% | -16.30% | 821.1% |
| `NO_RISK_PARITY` Ablation | +0.5862 | +0.2132 | 0.3796 | +0.56 | [-0.5309, +0.9573] | +4.15% | 7.40% | -11.76% | 364.8% |

---

### 3. Walk-Forward Partitioning (`CAND-001`)

*Emitted directly from the 2,512-bar aligned data panel (756-bar warmup + 1,756 active execution bars):*

| Partition | Date Range | Bar Count | Excess Sharpe | CAGR | Ann. Volatility | Max Drawdown |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **TRAIN (60%)** | 2019-08-29 to 2022-08-22 | 751 bars | +0.4305 | +3.67% | 7.85% | -9.84% |
| **VALIDATION (20%)** | 2022-08-23 to 2024-08-21 | 502 bars | -0.0384 | +4.49% | 6.50% | -8.12% |
| **TRUE OOS (20%)** | 2024-08-22 to 2026-08-25 | 503 bars | +0.1217 | +4.71% | 7.07% | -6.45% |

---

### 4. Friction Sensitivity Matrix

*All evaluations at base trading cost = 10.0 bps and short borrow fee = 25.0 bps/year:*

| Half-Spread Slippage (bps) | Gross Sharpe | Excess Sharpe | Net CAGR | Max Drawdown | Total Friction Paid |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **0.0 bps** | +0.6328 | +0.2525 | +4.42% | -11.89% | \$2,987 |
| **2.5 bps** | +0.6191 | +0.2388 | +4.32% | -12.06% | \$3,734 |
| **5.0 bps (Baseline)** | **+0.6035** | **+0.2232** | **+4.20%** | **-12.22%** | **\$4,481** |
| **10.0 bps** | +0.5743 | +0.1940 | +3.98% | -12.56% | \$5,975 |
| **20.0 bps** | +0.5142 | +0.1339 | +3.53% | -13.21% | \$8,962 |
| **30.0 bps** | +0.4540 | +0.0736 | +3.08% | -13.87% | \$11,949 |
| **50.0 bps** | +0.3347 | -0.0454 | +2.18% | -15.31% | \$17,924 |

*Break-Even Half-Spread Capacity*: **~42.0 bps** before excess return over risk-free rate turns negative.

---

### 5. Existing Test Modifications & Audit Justifications (Rule 9)

In accordance with Rule 9, the following modifications to existing unit and integration tests were executed and audited:

1. **[`tests/accounting/test_accounting.py`](file:///C:/Quant/Quant-Algorithm/tests/accounting/test_accounting.py)**:
   - *Change*: Changed Day 2 sell share assertion from floating range approximation to exact discrete integer equality `assert shares_day2 == 49.0`.
   - *Justification*: Under `discrete_shares=True` with Day 1 NAV = \$99,960, target weight 0.20, and price \$400, target shares are $\lfloor 0.20 \times 99,960 / 400 \rfloor = 49$. An exact equality test prevents regression to fractional shares.
2. **[`tests/runner/test_30day_validation.py`](file:///C:/Quant/Quant-Algorithm/tests/runner/test_30day_validation.py)**:
   - *Change*: Updated order count assertion to differentiate initial portfolio construction vs monthly rotation: Day 1 requires exactly `orders_count == 6` (3 long + 3 short); Day 22 requires exactly `orders_count == 7` (6 target allocations + 1 order closing rotated-out position `UUP`); intra-month drift days require exactly `orders_count == 0`.
   - *Justification*: On Day 22, ranking rotation dropped `UUP` from the portfolio. OMS generates an order to close `UUP` plus 6 target allocation orders. Exact count testing prevents silent order omission or spurious trade generation.
3. **[`tests/drift/test_drift.py`](file:///C:/Quant/Quant-Algorithm/tests/drift/test_drift.py)**:
   - *Change*: Updated expected trade delta from continuous $333.333$ to discrete integer `int(100_000 * 0.50 / 150) == 333.0`.
   - *Justification*: Reflects production-grade discrete integer lot sizing.
4. **[`tests/runner/test_autonomous_runner.py`](file:///C:/Quant/Quant-Algorithm/tests/runner/test_autonomous_runner.py)**:
   - *Change*: In `test_autonomous_short_borrow_unavailable_rejected`, mapped all assets in the universe to `ShortAvailability.UNAVAILABLE`.
   - *Justification*: With gross-1.0 dollar-neutral sizing generating 3 shorts dynamically, ensuring every universe asset is flagged as borrow-unavailable verifies that the runner's fail-closed borrow pre-check blocks order generation.
5. **[`tests/unit/test_strategy_parity.py`](file:///C:/Quant/Quant-Algorithm/tests/unit/test_strategy_parity.py)**:
   - *Change*: Strategy parity test explicitly passes legacy 2.0x Mom+Val+Car parameters (`target_sleeve_gross=1.0`, `max_single_position_weight=1.0`, `use_value=True`, `use_carry=True`).
   - *Justification*: Confirms that signal generation in `quant.strategies.macro` produces bit-for-bit identical raw factors and ranked weights to `markov2.macro` under equivalent parameterizations.
