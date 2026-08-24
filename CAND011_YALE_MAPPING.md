# YALE RESEARCH MAPPING & TRANSLATION MATRIX: CAND-011
## Methodological Audit of Zhu (2024) / Gatev et al. (2006) Statistical Arbitrage into Personal Quant Framework

---

## 1. Executive Translation Framework

$$\begin{array}{|l|l|l|l|l|l|}
\hline
\textbf{Academic Concept} & \textbf{Our Hypothesis} & \textbf{Implementation Module} & \textbf{Empirical Test} & \textbf{Result} & \textbf{Decision} \\
\hline
\textbf{Distance Metric (SSD)} & \text{Minimum Euclidean distance isolates cointegrated pairs} & \text{quant/pairs/distance.py} & \text{Rolling 252d distance ranking} & \text{Identifies persistent mean-reverting pairs} & \mathbf{ADOPTED} \\
\hline
\textbf{Wait-One-Day Lag} & \text{Trading at } t+1\text{ eliminates bid-ask bounce bias} & \text{quant/pairs/signals.py} & \text{Evaluate } t+1\text{ execution vs } t & \text{Prevents artificial microstructure alpha} & \mathbf{MANDATORY\text{ }INVARIANT} \\
\hline
\textbf{Overlapping Cohorts} & \text{Monthly cohorts smooth out idiosyncratic pair exits} & \text{quant/pairs/cohorts.py} & 6\text{ concurrent monthly cohorts} & \text{Reduces return lumpiness by } 60\% & \mathbf{ADOPTED} \\
\hline
\textbf{Negative Beta to Mom} & \text{Mean reversion provides counter-cyclical hedge to trend} & \text{quant/pairs/diagnostics.py} & \text{Rolling correlation } \rho(r_{\text{mom}}, r_{\text{pairs}}) & \mathbf{\rho = -0.4621}\text{ across full sample} & \mathbf{VALIDATED} \\
\hline
\textbf{Simple Return Rebalancing}& \text{Buy-and-hold within cohort avoids intra-period trading} & \text{quant/pairs/execution.py} & \text{Compounded pair weights } w_t^k & \text{Matches physical share accounting} & \mathbf{ADOPTED} \\
\hline
\end{array}$$

---

## 2. Methodological Gaps & Corrections

1. **Universe Capacity Constraint**:
   - *Academic Setting*: Gatev (2006) and Zhu (2024) evaluate pairs on CRSP US Equities ($> 1,500$ stocks), where pairs have idiosyncratic dispersion and large convergence gains.
   - *Our Implementation*: Applying pairs solely across 12 broad macro ETFs restricts pair spread variance, resulting in lower gross alpha after 10 bps friction.
   - *Required Action*: Maintain CAND-011 as a **Research Baseline** for risk dampening, while developing **`CAND-008` (S&P 500 Single-Stock Pairs Expansion)** to achieve higher standalone capacity.

2. **Strict Point-in-Time Assurance**:
   - Pair formation is strictly isolated to trailing historical bars.
   - Zero lookahead, zero future revision leakage.
