# ALPHA RESEARCH V2 — SCORECARD
## Empirical Evaluation of Systematic Macro & Candidate Strategies (Remediated Baseline)

---

## 1. Executive Master Scorecard

$$\begin{array}{|l|r|r|r|r|r|r|r|l|}
\hline
\textbf{Candidate ID} & \textbf{Gross SR} & \textbf{Excess SR} & \textbf{Net CAGR} & \textbf{Max DD} & \textbf{Turnover} & \textbf{OOS SR} & \textbf{DSR } p & \textbf{Status / Decision} \\
\hline
\mathbf{CAND-001\text{ (Remediated Control)}} & \mathbf{+0.6022} & \mathbf{+0.6022} & \mathbf{+7.38\%} & \mathbf{-25.53\%} & \mathbf{885.0\%} & \mathbf{+1.0032} & \mathbf{1.0000} & \mathbf{CANONICAL\text{ }CONTROL} \\
\mathbf{ENS-80-20\text{ (Multi-Strategy)}} & \mathbf{+0.5789} & \mathbf{+0.3567} & \mathbf{+6.14\%} & \mathbf{-14.73\%} & \mathbf{736.7\%} & \mathbf{+0.9286} & \mathbf{1.0000} & \mathbf{MULTI-STRATEGY\text{ }BASELINE} \\
\mathbf{CAND-006\text{ (Skip-Month 6-1)}} & \mathbf{+0.5410} & \mathbf{+0.5410} & \mathbf{+7.10\%} & \mathbf{-22.80\%} & \mathbf{913.4\%} & \mathbf{+0.5310} & \mathbf{0.0099} & \mathbf{BENCHMARK\text{ }SPEC} \\
\mathbf{CAND-009\text{ (Asymmetric 50\% Short)}}& \mathbf{+0.5520} & \mathbf{+0.5520} & \mathbf{+7.15\%} & \mathbf{-25.10\%} & \mathbf{663.8\%} & \mathbf{+0.5110} & \mathbf{0.0099} & \mathbf{PROMISING\text{ }CANDIDATE} \\
\mathbf{CAND-008\text{ (S\&P 500 Pairs T20)}} & \mathbf{+0.5221} & \mathbf{+0.5221} & \mathbf{+2.58\%} & \mathbf{-8.37\%} & \mathbf{1842.0\%} & \mathbf{+0.1966} & \mathbf{0.0084} & \mathbf{RESEARCH\text{ }BASELINE} \\
\mathbf{CAND-012\text{ (Robust Pairs Hedge)}} & -0.3817 & -0.3817 & -1.87\% & \mathbf{-21.11\%} & \mathbf{1842.0\%} & -0.1980 & \mathbf{0.0068} & \mathbf{RISK\text{ }HEDGE\text{ }ONLY} \\
\text{CAND-013 (Hysteresis+Vol Target)} & +0.2495 & +0.2495 & +1.75\% & -20.75\% & 1660.0\% & +0.1892 & 0.0052 & \mathbf{REJECT\text{ (0/48 Passed)}} \\
\text{CAND-014 (Regime-Gated Momentum)} & +0.0968 & +0.0968 & +0.47\% & -23.60\% & 548.0\% & +0.1849 & 0.0316 & \mathbf{REJECT\text{ (Cash Drag)}} \\
\text{CLEAN\_BASELINE (Mom+Val+Car)} & +0.1244 & +0.1244 & +0.77\% & -26.47\% & 525.8\% & +0.0540 & 0.4890 & \mathbf{REJECT\text{ (Factor Dilution)}} \\
\text{CAND-005 (Vol-Gated Deleveraging)} & \mathbf{+0.5260} & \mathbf{+0.5260} & \mathbf{+6.88\%} & \mathbf{-23.04\%} & \mathbf{891.2\%} & \mathbf{+0.5284} & 0.0099 & \mathbf{EXPERIMENTAL} \\
\text{CAND-010 (Dynamic Macro Carry)} & -0.6336 & -0.6336 & -13.69\% & -73.66\% & 1120.4\% & -0.8808 & 0.5210 & \mathbf{REJECT\text{ (Yield Trap)}} \\
\text{CAND-003 (Multi-Horizon Blend)} & +0.0988 & +0.0988 & +0.35\% & -33.73\% & 1240.2\% & +0.3499 & 0.4120 & \mathbf{REJECT\text{ (Whipsaw drag)}} \\
\text{CAND-004 (Demarcated Sectors)} & -0.4491 & -0.4491 & -4.39\% & -38.01\% & 980.5\% & -1.6991 & 0.6210 & \mathbf{REJECT\text{ (Bad short quotas)}} \\
\hline
\end{array}$$

---

## 2. Statistical Uncertainty & Confidence Intervals

| Strategy Candidate | Gross Sharpe | Excess Sharpe | Sharpe SE | $t$-statistic | 95% Confidence Interval |
|---|---:|---:|---:|---:|:---:|
| **CAND-001 Canonical** | **+0.6022** | **+0.6022** | **0.3808** | **1.5817** | `[-0.1440, +1.3485]` |
| **ENS-80-20 Multi-Strategy**| **+0.5789** | **+0.3567** | **0.3805** | **0.9375** | `[-0.3891, +1.1025]` |
| **CAND-006 Skip-Month** | **+0.5410** | **+0.5410** | **0.3807** | **1.4210** | `[-0.2052, +1.2872]` |
| **CAND-009 Asymmetric Short**| **+0.5520** | **+0.5520** | **0.3806** | **1.4503** | `[-0.1940, +1.2980]` |

---

## 3. Friction Sensitivity & Break-Even Matrix

| Slippage Assumption | CAND-001 Sharpe | CAND-001 CAGR | ENS-80/20 Sharpe | Break-Even Slippage |
|---|---:|---:|---:|---:|
| **0.0 bps (Friction-Free)** | **+0.6645** | **+8.20%** | **+0.6410** | **26.8 bps** |
| **2.5 bps (Approved Baseline)** | **+0.6022** | **+7.38%** | **+0.5789** | **26.8 bps** |
| **5.0 bps (Conservative)** | **+0.5401** | **+6.56%** | **+0.5180** | **26.8 bps** |
| **10.0 bps (High Friction)** | **+0.4158** | **+4.95%** | **+0.3950** | **26.8 bps** |
| **20.0 bps (Severe Friction)** | **+0.1685** | **+1.79%** | **+0.1510** | **26.8 bps** |
| **30.0 bps (Negative Alpha)** | **-0.0760** | **-1.28%** | **-0.0920** | **26.8 bps** |

---

## 4. Master Strategy Recommendation

$$\mathbf{VERDICT = KEEP\text{ }(CAND-001\text{ }/\text{ }ENS-80/20\text{ }MAINTAINED\text{ }AS\text{ }CANONICAL\text{ }BASELINES)}$$
