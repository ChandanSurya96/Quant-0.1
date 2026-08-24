# ALPHA RESEARCH V2 — SCORECARD
## Empirical Evaluation of Systematic Macro & Candidate Strategies

---

## 1. Executive Master Scorecard

$$\begin{array}{|l|r|r|r|r|r|r|r|l|}
\hline
\textbf{Candidate ID} & \textbf{Full Sharpe} & \textbf{Full CAGR} & \textbf{Max DD} & \textbf{Turnover} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} & \textbf{Gate 3 } p & \textbf{Status / Decision} \\
\hline
\textbf{CLEAN\_BASELINE (Mom+Val+Car)} & -0.2583 & -6.73\% & -56.59\% & 364.8\% & -1.2450 & -18.42\% & 0.4890 & \mathbf{REJECT\text{ (Overfit)}} \\
\mathbf{CAND-001\text{ (Frozen Control)}} & \mathbf{+0.5253} & \mathbf{+6.87\%} & \mathbf{-23.04\%} & \mathbf{893.4\%} & \mathbf{+0.5284} & \mathbf{+6.40\%} & \mathbf{0.0099} & \mathbf{CANONICAL\text{ }CONTROL} \\
\mathbf{CAND-006\text{ (Skip-Month 6-1)}} & \mathbf{+0.5410} & \mathbf{+7.10\%} & \mathbf{-22.80\%} & \mathbf{913.4\%} & \mathbf{+0.5310} & \mathbf{+6.55\%} & \mathbf{0.0099} & \mathbf{BENCHMARK\text{ }SPEC} \\
\mathbf{CAND-009\text{ (Asymmetric 50\% Short)}}& \mathbf{+0.5520} & \mathbf{+7.15\%} & \mathbf{-25.10\%} & \mathbf{663.8\%} & \mathbf{+0.5110} & \mathbf{+6.20\%} & \mathbf{0.0099} & \mathbf{PROMISING\text{ }CANDIDATE} \\
\mathbf{CAND-008\text{ (S\&P 500 Pairs T20)}} & \mathbf{+0.5221} & \mathbf{+2.58\%} & \mathbf{-8.37\%} & \mathbf{1842.0\%} & \mathbf{+0.1966} & \mathbf{+1.20\%} & \mathbf{0.0084} & \mathbf{RESEARCH\text{ }BASELINE} \\
\mathbf{CAND-012\text{ (Robust Pairs Hedge)}} & -0.3817 & -1.87\% & \mathbf{-21.11\%} & \mathbf{1842.0\%} & -0.1980 & -0.95\% & \mathbf{0.0068} & \mathbf{RISK\text{ }HEDGE\text{ }ONLY} \\
\mathbf{ENS-70-30\text{ (Robust Multi-Strategy)}} & \mathbf{+0.4308} & \mathbf{+4.00\%} & \mathbf{-13.52\%} & \mathbf{646.9\%} & \mathbf{+0.5147} & \mathbf{+5.10\%} & \mathbf{0.0068} & \mathbf{RESEARCH\text{ }BASELINE} \\
\mathbf{ENS-80-20\text{ (Return-Tilted Multi)}}& \mathbf{+0.4648} & \mathbf{+4.88\%} & \mathbf{-14.73\%} & \mathbf{736.7\%} & \mathbf{+0.5340} & \mathbf{+5.70\%} & \mathbf{0.0068} & \mathbf{RESEARCH\text{ }BASELINE} \\
\text{CAND-013 (Hysteresis+Vol Target)} & +0.2495 & +1.75\% & -20.75\% & 1660.0\% & +0.1892 & +1.20\% & 0.0052 & \mathbf{REJECT\text{ (0/48 Passed)}} \\
\text{CAND-014 (Regime-Gated Momentum)} & +0.0968 & +0.47\% & -23.60\% & 548.0\% & +0.1849 & +1.34\% & 0.0316 & \mathbf{REJECT\text{ (Cash Drag)}} \\
\text{CAND-005 (Vol-Gated Deleveraging)} & \mathbf{+0.5260} & \mathbf{+6.88\%} & \mathbf{-23.04\%} & \mathbf{891.2\%} & \mathbf{+0.5284} & \mathbf{+6.40\%} & 0.0099 & \mathbf{EXPERIMENTAL} \\
\text{CAND-010 (Dynamic Macro Carry)} & -0.6336 & -13.69\% & -73.66\% & 1120.4\% & -0.8808 & -18.20\% & 0.5210 & \mathbf{REJECT\text{ (Yield Trap)}} \\
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
| **CAND-008 S&P Pairs T20** | **+0.8240** | **+0.5221** | -0.6858 | **28.4 bps** | **120 bps/yr** |
| **CAND-012 Robust Pairs (Univ D)** | -0.2292 | -0.3817 | -1.6017 | < 0 bps | < 0 bps |
| **ENS-70-30 Robust Ensemble** | **+0.5120** | **+0.4308** | **+0.1050** | **58.2 bps** | **250 bps/yr** |
| **ENS-80-20 Robust Ensemble** | **+0.5480** | **+0.4648** | **+0.1840** | **74.5 bps** | **380 bps/yr** |

---

## 3. Top Research Candidates Queue

| Rank | Candidate ID | Mechanism & Description | Target Flaw Addressed | Expected Value | Status |
|:---:|---|---|---|:---:|:---:|
| **#1** | `CAND-001` | Pure Momentum (126d) + Risk Parity + Hysteresis | Factor cannibalization ($\rho = -0.65$) | Canonical Control | **CANONICAL CONTROL** |
| **#2** | `CAND-006` | Skip-Month Momentum (6-1d) + Risk Parity | 1-month reversal contamination | $+23\text{ bps}$ CAGR | **BENCHMARK SPEC** |
| **#3** | `CAND-009` | Asymmetric 50% Short Scaling + Skip-Month | Short-side positive drift drag | Turnover $-26\%$ | **PROMISING CANDIDATE** |
| **#4** | `ENS-80-20` | 80/20 Multi-Strategy Risk Ensemble (CAND-006 + Robust Pairs) | Portfolio volatility & drawdown reduction | MaxDD $-14.7\%$, OOS $+0.53$ | **RESEARCH BASELINE** |
| **#5** | `CAND-008` | S&P 500 Single-Stock Dynamic Pairs Expansion | Microstructure capacity & high dispersion | Sharpe $+0.52$, MaxDD $-8.4\%$ | **RESEARCH BASELINE** |

---

## 4. Final Master Verdict

$$\mathbf{RESEARCH\_VERDICT = MAINTAIN\_CONTROL\_AND\_INTEGRATE\_RISK\_HEDGES}$$

**Rationale**:
1. `CAND-006` remains the primary standalone trend engine ($+0.5410$ Sharpe, $+7.10\%$ CAGR).
2. Hostile survivorship and borrow tests prove that statistical arbitrage fails as a standalone profit driver, but succeeds as an orthogonal risk hedge (`ENS-80-20` cuts drawdown to $-14.73\%$ while sustaining $+4.88\%$ CAGR and $+0.5340$ OOS Sharpe).
3. All accounting invariants and 301+ automated tests remain 100% green.
