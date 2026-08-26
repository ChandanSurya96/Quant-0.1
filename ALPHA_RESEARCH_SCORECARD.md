# QUANTITATIVE ALPHA RESEARCH SCORECARD
## Canonical Post-Remediation Real Market Data Audit (EXP-030-AUDIT)

**Audited Strategy**: `CAND-001` Systematic Macro Momentum (Gross 1.0x NAV, 50% Long / 50% Short)  
**Data Provider**: `YFinanceProvider` (10-Year Real Market Prices + CBOE 3M Treasury Rates)  
**Execution Frictions**: 10 bps turnover cost + 5.0 bps baseline slippage + 25 bps/year borrow fee + discrete integer shares  

---

### Core Performance Scorecard

| Performance Metric | Candidate Value | Benchmark / Target | Audit Status |
| :--- | :---: | :---: | :---: |
| **Gross Sharpe Ratio** | `+0.6035` | $> +0.50$ | PASS |
| **Excess Sharpe Ratio (over RF)** | `+0.2232` | $> +0.50$ | **FAIL (Weak Edge)** |
| **Sharpe Standard Error (Lo & Mertens)** | `0.3799` | $< 0.25$ | High Uncertainty |
| **t-Statistic on Excess Sharpe** | `+0.59` | $> +2.00$ | **FAIL (Not Significant)** |
| **95% Confidence Interval (Excess Sharpe)**| `[-0.5215, +0.9679]` | Lower CI $> 0.0$ | **FAIL (Spans Zero)** |
| **Deflated Sharpe Ratio (DSR)** | `0.4926` | $> 0.95$ ($p < 0.05$) | **FAIL (Consistent with Noise)** |
| **True Out-of-Sample Sharpe (2024–2026)** | `+0.1217` | $> +0.30$ | Marginal Positive |
| **Net CAGR** | `+4.20%` | $> +6.00%$ | PASS (at 1.0x Gross) |
| **Annualized Volatility** | `7.26%` | $< 12.00%$ | PASS |
| **Maximum Drawdown** | `-12.22%` | $< -15.00%$ | PASS |
| **Annualized Turnover** | `427.8%` | $< 600.0%$ | PASS |
| **Break-Even Half-Spread Slippage** | `~42 bps` | $> 15 bps$ | PASS |

---

### Adversarial Factor Ablation Scorecard

| Model Specification | Net Excess Sharpe | Net CAGR | Max Drawdown | Annualized Turnover | Conclusion |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **CAND-001 (Momentum + Hysteresis + RP)** | **+0.2232** | **+4.20%** | **-12.22%** | **427.8%** | **Canonical Macro Baseline** |
| `CLEAN_BASELINE` (Mom + Val + Car) | -0.4345 | +0.34% | -12.70% | 186.6% | Destroyed by Value/Carry drag |
| `MOMENTUM_ALONE` (No Hysteresis, No RP) | -0.0921 | +1.73% | -16.35% | 727.8% | Unmitigated turnover and tail risk |
| `NO_HYSTERESIS` Ablation | -0.1594 | +1.24% | -16.30% | 821.1% | High turnover erodes return |
| `NO_RISK_PARITY` Ablation | +0.2132 | +4.15% | -11.76% | 364.8% | Equal weight slightly lower Sharpe |

---

### Final Research Verdict

- **Standalone Production Alpha Status**: **REJECTED (UNCONFIRMED)**. The empirical edge ($t = 0.59$) is not statistically distinguishable from zero across 29 historical backtest trials.
- **Portfolio Diversifier Status**: **CONDITIONAL HOLD**. Because the strategy runs at low volatility (7.26%) and max drawdown (-12.22%) with roughly ~3.4% expected excess return over cash, it serves as a viable, non-correlated macro diversifier when combined with equities/fixed income, but should not be levered up prior to live out-of-sample evidence accumulation.
