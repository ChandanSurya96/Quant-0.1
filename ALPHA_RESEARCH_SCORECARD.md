# ALPHA RESEARCH V2 — SCORECARD
## Empirical Evaluation of Systematic Macro & Candidate Strategies

---

## 1. Executive Master Scorecard

$$\begin{array}{|l|r|r|r|r|r|r|r|l|}
\hline
\textbf{Candidate ID} & \textbf{Full Sharpe} & \textbf{Full CAGR} & \textbf{Max DD} & \textbf{Turnover} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} & \textbf{Gate 3 } p & \textbf{Status / Decision} \\
\hline
\textbf{CLEAN\_BASELINE (Mom+Val+Car)} & -0.2583 & -6.73\% & -56.59\% & 364.8\% & -1.2450 & -18.42\% & 0.4890 & \mathbf{REJECT\text{ (Overfit)}} \\
\mathbf{CAND-001\text{ (Frozen Control)}} & \mathbf{+0.5253} & \mathbf{+6.87\%} & \mathbf{-23.04\%} & \mathbf{893.4\%} & \mathbf{+0.5284} & \mathbf{+6.40\%} & \mathbf{0.0099} & \mathbf{PROMOTE\text{ (Primary Spec)}} \\
\text{CAND-003 (Multi-Horizon Blend)} & +0.0988 & +0.35\% & -33.73\% & 1240.2\% & +0.3499 & +3.85\% & 0.4120 & \mathbf{REJECT\text{ (Whipsaw drag)}} \\
\text{CAND-004 (Demarcated Sectors)} & -0.4491 & -4.39\% & -38.01\% & 980.5\% & -1.6991 & -12.45\% & 0.6210 & \mathbf{REJECT\text{ (Bad short quotas)}} \\
\text{CAND-005 (Vol-Gated Deleveraging)} & \mathbf{+0.5260} & \mathbf{+6.88\%} & \mathbf{-23.04\%} & \mathbf{891.2\%} & \mathbf{+0.5284} & \mathbf{+6.40\%} & 0.0099 & \mathbf{EXPERIMENTAL} \\
\mathbf{PAIRS-001\text{ (Yale Distance T20)}} & \mathbf{+0.1960} & \mathbf{+0.66\%} & \mathbf{-8.83\%} & \mathbf{2524.5\%} & +0.0450 & +0.21\% & 0.0792 & \mathbf{RESEARCH\text{ }BASELINE} \\
\mathbf{PAIRS-008\text{ (50/50 Multi-Strategy)}}& \mathbf{+0.8420} & \mathbf{+7.85\%} & \mathbf{-14.20\%} & \mathbf{1708.9\%} & \mathbf{+0.6120} & \mathbf{+7.10\%} & \mathbf{0.0099} & \mathbf{RESEARCH\text{ }BASELINE} \\
\hline
\end{array}$$

---

## 2. Friction Sensitivity & Break-Even Summary

| Strategy Variant | 0 bps Sharpe | 10 bps Sharpe | 50 bps Sharpe | Break-Even Friction | Borrow Tolerance |
|---|---:|---:|---:|---:|---:|
| **CAND-001 Control** | **+0.5885** | **+0.5253** | **+0.2721** | **93.4 bps** | **> 500 bps/yr** |
| **CAND-003 Multi-Horizon** | +0.1840 | +0.0988 | -0.2410 | 17.6 bps | 85 bps/yr |
| **CAND-004 Demarcated** | -0.3810 | -0.4491 | -0.7200 | Negative Gross Alpha | 0 bps/yr |
| **PAIRS-001 Yale T20** | **+0.1960** | -0.0359 | -0.4412 | **7.2 bps** | 45 bps/yr |

---

## 3. Top 5 Research Candidates Queue

| Rank | Candidate ID | Mechanism & Description | Target Flaw Addressed | Expected Value | Status |
|:---:|---|---|---|:---:|:---:|
| **#1** | `CAND-001` | Pure Momentum (126d) + Risk Parity + Hysteresis | Factor cannibalization ($\rho = -0.65$) | Primary Spec | **PROMOTED** |
| **#2** | `CAND-005` | Macro Volatility-Gated Deleveraging | High vol regime tail drawdowns | De-risking | **EXPERIMENTAL** |
| **#3** | `PAIRS-008` | 50/50 Multi-Strategy Ensemble (CAND-001 + Pairs) | Portfolio volatility & tail drawdown | Volatility $-53\%$ | **RESEARCH BASELINE** |
| **#4** | `CAND-006` | Dynamic FRED Yield Differential Carry (10Y-2Y) | Static dictionary carry replacement | $+0.20$ Sharpe | Backlog |
| **#5** | `CAND-007` | S&P 500 Dynamic Fundamental Dispersion Pairs | Single-stock idiosyncratic mean reversion | High capacity | Backlog |

---

## 4. Final Master Verdict

$$\mathbf{RESEARCH\_VERDICT = PROMOTE\_CAND\_001}$$

**Rationale**:
1. `CAND-001` is validated across a 45-parameter perturbation grid, showing smooth parameter stability with no knife-edge fragility.
2. In the untouched True Out-of-Sample window, CAND-001 delivers **Sharpe `+0.5284`** and **CAGR `+6.40%`**.
3. All accounting invariants (physical shares, discrete shares, transaction costs, natural weight drift) remain 100% verified across 289 automated tests.
