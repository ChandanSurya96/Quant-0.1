# ALPHA RESEARCH V2 — SCORECARD

---

## 1. Executive Summary Scorecard

| Strategy Variant / Candidate | CAGR (%) | Net Sharpe | Sortino | Max DD (%) | Calmar | Volatility (%) | Ann. Turnover (%) | Costs (bps) | OOS Sharpe | OOS CAGR (%) | Robustness Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| **Baseline (Mom + Val + Carry + Hyst + RP)** | -7.63% | -0.297 | -0.640 | -60.56% | 0.126 | 20.01% | 357.35% | 10.0 | -1.245 | -18.42% | **REJECT (In-Sample Overfit)** |
| **Ablation 1: No Momentum (Val + Carry only)** | +4.13% | +0.306 | +0.365 | -45.74% | 0.090 | 19.31% | 351.51% | 10.0 | -0.182 | -2.15% | **PROMISING (Momentum Drag Removed)** |
| **Ablation 2: No Value (Mom + Carry only)** | -3.60% | -0.095 | -0.308 | -38.77% | 0.093 | 19.21% | 462.27% | 10.0 | -0.622 | -8.10% | **REJECT (Negative Alpha)** |
| **Ablation 3: No Carry (Mom + Val only)** | -7.88% | -0.327 | -0.692 | -55.37% | 0.142 | 19.39% | 788.13% | 10.0 | -1.410 | -21.05% | **REJECT (High Turnover Drag)** |
| **Ablation 4: No Hysteresis (Raw Monthly)** | -11.21% | -0.511 | -0.947 | -68.84% | 0.163 | 19.52% | 1093.52% | 10.0 | -1.825 | -28.90% | **REJECT (Excessive Churn)** |
| **Ablation 5: Equal Weight (No Risk Parity)** | -7.95% | -0.315 | -0.668 | -60.72% | 0.131 | 19.95% | 235.85% | 10.0 | -1.189 | -17.80% | **REJECT (Sub-optimal Risk Profile)** |
| **Standalone: Pure Momentum Alone** | -7.10% | -0.288 | -0.610 | -61.76% | 0.115 | 19.18% | 932.14% | 10.0 | -1.350 | -19.80% | **REJECT (Severe Cross-Asset Bleed)** |
| **Standalone: Pure Value Alone** | +0.49% | +0.122 | +0.041 | -43.38% | 0.011 | 19.44% | 447.93% | 10.0 | +0.085 | +0.90% | **STABLE (Positive Unconditional Edge)** |
| **Standalone: Pure Carry Alone** | -2.60% | -0.039 | -0.225 | -47.11% | 0.055 | 19.40% | 146.46% | 10.0 | -0.310 | -4.20% | **REJECT (Static Tilt Artifact)** |

---

## 2. Friction & Break-Even Analysis

| Execution Friction Assumption | Net CAGR (%) | Net Sharpe Ratio | Maximum Drawdown (%) | Annualized Turnover (%) | Status |
|---|---:|---:|---:|---:|:---:|
| **0 bps (Gross Return)** | -7.30% | -0.279 | -59.88% | 357.35% | Negative Gross Edge |
| **5 bps (Institutional Execution)** | -7.47% | -0.288 | -60.22% | 357.35% | Negative |
| **10 bps (Baseline Model)** | -7.63% | -0.297 | -60.56% | 357.35% | Negative |
| **20 bps (Conservative Slippage)** | -7.96% | -0.315 | -61.23% | 357.35% | Negative |
| **30 bps (Adverse Execution)** | -8.29% | -0.332 | -61.89% | 357.35% | Negative |
| **50 bps (Severe Friction)** | -8.95% | -0.368 | -63.17% | 357.35% | Negative |

* **Break-Even Cost**: **`-156.18 bps`** (The gross strategy has a negative return of -7.30%/yr; costs merely increase the drag).

---

## 3. Parameter Sensitivity Grid (Momentum $\times$ Value Windows)

| Mom Window | Val Window | Train Sharpe (60%) | Validation Sharpe (20%) | True OOS Sharpe (20%) | Full Sharpe | Full CAGR (%) | Full MaxDD (%) | Plateau Status |
|:---:|:---:|---:|---:|---:|---:|---:|---:|:---:|
| 63d (3M) | 252d (1Y) | +0.367 | -0.108 | -0.922 | -0.133 | -4.37% | -50.56% | Fragile |
| 63d (3M) | 504d (2Y) | +0.321 | -0.372 | -1.168 | -0.309 | -7.85% | -55.42% | Degraded |
| 63d (3M) | 756d (3Y) | +0.353 | -0.208 | -1.304 | -0.272 | -7.20% | -53.51% | Degraded |
| 63d (3M) | 1008d (4Y) | +0.454 | -0.014 | -2.038 | -0.473 | -9.97% | -65.42% | Severe OOS Collapse |
| 126d (6M) | 252d (1Y) | +0.741 | -0.413 | -0.826 | -0.035 | -2.50% | -49.74% | In-Sample Peak |
| 126d (6M) | 504d (2Y) | +0.578 | -0.731 | -0.622 | -0.143 | -4.73% | -52.14% | Degraded |
| **126d (6M)** | **756d (3Y)** | **+0.481** | **-0.541** | **-1.245** | **-0.297** | **-7.63%** | **-60.56%** | **Baseline Choice (Overfit)** |
| 126d (6M) | 1008d (4Y) | +0.698 | -0.374 | -0.618 | -0.025 | -2.18% | -47.26% | Unstable |
| 252d (12M) | 252d (1Y) | +0.720 | -0.159 | -0.396 | +0.151 | +1.07% | -40.69% | Positive Full |
| 252d (12M) | 504d (2Y) | +1.025 | -0.546 | -0.585 | +0.119 | +0.44% | -49.37% | In-Sample Peak |
| 252d (12M) | 756d (3Y) | +0.529 | -0.463 | -0.559 | -0.066 | -3.15% | -45.61% | Degraded |
| 252d (12M) | 1008d (4Y) | +0.689 | -0.827 | -0.134 | -0.026 | -2.11% | -42.79% | Degraded |
| 504d (24M) | 252d (1Y) | +0.432 | -0.091 | -1.066 | -0.132 | -4.18% | -49.65% | Degraded |
| 504d (24M) | 504d (2Y) | +0.642 | -0.068 | -0.672 | +0.075 | -0.39% | -40.69% | Neutral |
| 504d (24M) | 756d (3Y) | +1.073 | +0.066 | -1.204 | +0.124 | +0.55% | -50.82% | In-Sample Peak |
| 504d (24M) | 1008d (4Y) | +1.240 | -0.018 | -0.618 | +0.280 | +3.42% | -41.68% | In-Sample Spike |

* **Key Takeaway**: In 16 out of 16 parameter pairs, Train Sharpe was positive (+0.32 to +1.24), while True OOS Sharpe was strictly negative (-0.13 to -2.04). This proves systemic in-sample overfitting across all lookback horizons.

---

## 4. Top 5 Research Candidates Scorecard

| Rank | Research Candidate | Primary Mechanism | Target Flaw Addressed | Expected $\Delta$Sharpe | Falsification Criterion |
|:---:|---|---|---|:---:|---|
| **#1** | **Within-Asset-Class Ranking** | Rank 1 Long / 1 Short per asset class (Equities, Bonds, FX) | Eliminates structural anti-equity bias across mixed asset classes | $+0.60$ to $+0.85$ | OOS Sharpe $\le 0.0$ across 3-year walk-forward |
| **#2** | **Dynamic Macro Carry (FRED Yields)** | Replace static dict with rolling 10Y-2Y yield spreads & div yields | Removes hardcoded 2024 yield assumptions | $+0.25$ to $+0.40$ | Turnover $> 8.0\times$ without Sharpe gain |
| **#3** | **Trend Regime Conditioning** | Invert or silence momentum when SPY $\ge \text{MA}_{50}$ | Neutralizes severe negative alpha in Risk-On equity regimes | $+0.40$ to $+0.60$ | Underperformance in historical Risk-Off regimes |
| **#4** | **Multi-Horizon Vol-Targeted Trend** | 3-Horizon blend (21d, 63d, 126d) normalized by $\sigma_{20d}$ | Reduces whipsaw on individual single-lookback breakouts | $+0.20$ to $+0.35$ | Correlation $> 0.90$ with single-window momentum |
| **#5** | **Macro State-Gated Allocation** | Regime-based gating between Macro Short and Equity Beta | Eliminates bleed during 10-year equity secular bull markets | $+0.50$ to $+0.75$ | Regime detection lag causing tail losses |

---

## 5. Final Research Verdict

$$\mathbf{RESEARCH\_VERDICT = MODIFY}$$

**Rationale**: The baseline Systematic Macro strategy as currently formulated is broken due to (1) cross-asset normalization distortion, (2) static dictionary carry artifacts, and (3) severe anti-trend drag during risk-on regimes. However, rank hysteresis and value z-scoring provide genuine structural benefits. Research should proceed to test Candidate #1 (Within-Asset-Class Cross-Sectional Ranking) under strict walk-forward isolation.
