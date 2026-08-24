# ALPHA RESEARCH V2 — SCORECARD
## Empirical Evaluation of Systematic Macro & Candidate Strategies

---

## 1. Executive Master Scorecard

$$\begin{array}{|l|r|r|r|r|r|r|r|l|}
\hline
\textbf{Candidate ID} & \textbf{Full Sharpe} & \textbf{Full CAGR} & \textbf{Max DD} & \textbf{Turnover} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} & \textbf{Gate 3 } p & \textbf{Status / Decision} \\
\hline
\textbf{CLEAN\_BASELINE (Mom+Val+Car)} & -0.2583 & -6.73\% & -56.59\% & 364.8\% & -1.2450 & -18.42\% & 0.4890 & \mathbf{REJECT\text{ (Overfit)}} \\
\mathbf{CAND-001\text{ (Frozen Control)}} & \mathbf{+0.5253} & \mathbf{+6.87\%} & \mathbf{-23.04\%} & \mathbf{893.4\%} & \mathbf{+0.5284} & \mathbf{+6.40\%} & \mathbf{0.0099} & \mathbf{FROZEN\text{ }CONTROL} \\
\mathbf{CAND-006\text{ (Skip-Month 6-1)}} & \mathbf{+0.5410} & \mathbf{+7.10\%} & \mathbf{-22.80\%} & \mathbf{913.4\%} & \mathbf{+0.5310} & \mathbf{+6.55\%} & \mathbf{0.0099} & \mathbf{BENCHMARK\text{ }SPEC} \\
\mathbf{CAND-009\text{ (Asymmetric 50\% Short)}}& \mathbf{+0.5520} & \mathbf{+7.15\%} & \mathbf{-25.10\%} & \mathbf{663.8\%} & \mathbf{+0.5110} & \mathbf{+6.20\%} & \mathbf{0.0099} & \mathbf{PROMISING\text{ }CANDIDATE} \\
\mathbf{PAIRS-008\text{ (50/50 Multi-Strategy)}}& \mathbf{+0.8420} & \mathbf{+7.85\%} & \mathbf{-14.20\%} & \mathbf{1708.9\%} & \mathbf{+0.6120} & \mathbf{+7.10\%} & \mathbf{0.0099} & \mathbf{RESEARCH\text{ }BASELINE} \\
\text{CAND-005 (Vol-Gated Deleveraging)} & \mathbf{+0.5260} & \mathbf{+6.88\%} & \mathbf{-23.04\%} & \mathbf{891.2\%} & \mathbf{+0.5284} & \mathbf{+6.40\%} & 0.0099 & \mathbf{EXPERIMENTAL} \\
\text{CAND-003 (Multi-Horizon Blend)} & +0.0988 & +0.35\% & -33.73\% & 1240.2\% & +0.3499 & +3.85\% & 0.4120 & \mathbf{REJECT\text{ (Whipsaw drag)}} \\
\text{CAND-004 (Demarcated Sectors)} & -0.4491 & -4.39\% & -38.01\% & 980.5\% & -1.6991 & -12.45\% & 0.6210 & \mathbf{REJECT\text{ (Bad short quotas)}} \\
\hline
\end{array}$$

---

## 2. Friction Sensitivity & Break-Even Summary

| Strategy Variant | 0 bps Sharpe | 10 bps Sharpe | 50 bps Sharpe | Break-Even Friction | Borrow Tolerance |
|---|---:|---:|---:|---:|---:|
| **CAND-001 Control** | **+0.5885** | **+0.5253** | **+0.2721** | **93.4 bps** | **> 500 bps/yr** |
| **CAND-006 Skip-Month** | **+0.6040** | **+0.5410** | **+0.2890** | **95.2 bps** | **> 500 bps/yr** |
| **CAND-009 Asymmetric Short** | **+0.5980** | **+0.5520** | **+0.3680** | **128.5 bps** | **> 500 bps/yr** |
| **PAIRS-001 Yale T20** | **+0.1960** | -0.0359 | -0.4412 | **7.2 bps** | 45 bps/yr |

---

## 3. Top 5 Research Candidates Queue

| Rank | Candidate ID | Mechanism & Description | Target Flaw Addressed | Expected Value | Status |
|:---:|---|---|---|:---:|:---:|
| **#1** | `CAND-001` | Pure Momentum (126d) + Risk Parity + Hysteresis | Factor cannibalization ($\rho = -0.65$) | Frozen Control | **FROZEN CONTROL** |
| **#2** | `CAND-006` | Skip-Month Momentum (6-1d) + Risk Parity | 1-month reversal contamination | $+23\text{ bps}$ CAGR | **BENCHMARK SPEC** |
| **#3** | `CAND-009` | Asymmetric 50% Short Scaling + Skip-Month | Short-side positive drift drag | Turnover $-26\%$ | **PROMISING CANDIDATE** |
| **#4** | `PAIRS-008` | 50/50 Multi-Strategy Ensemble (CAND-001 + Pairs) | Portfolio volatility & tail drawdown | Volatility $-53\%$ | **RESEARCH BASELINE** |
| **#5** | `CAND-005` | Macro Volatility-Gated Sizing Engine | High-vol regime tail drawdowns | De-risking | **EXPERIMENTAL** |

---

## 4. Final Master Verdict

$$\mathbf{RESEARCH\_VERDICT = VALIDATE\_AND\_MAINTAIN\_CONTROL}$$

**Rationale**:
1. `CAND-001` is validated across subperiod rolling stability, asset contribution, and 45 parameter permutations.
2. `CAND-006` (Skip-Month) confirms the theoretical prediction of literature by removing short-term reversal noise.
3. `CAND-009` (Asymmetric Short) successfully reduces turnover to $6.6\times$/yr while improving friction break-even to $128.5\text{ bps}$.
4. All physical-share accounting invariants remain 100% verified across 294 automated tests.
