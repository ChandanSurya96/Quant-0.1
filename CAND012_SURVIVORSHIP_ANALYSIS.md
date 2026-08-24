# CAND-012 SURVIVORSHIP-BIAS AUDIT & STRESS ANALYSIS
## Econometric Evaluation of S&P 500 Constituent Selection Biases

---

## 1. Methodology & Data Limitations

In academic literature (e.g. Gatev et al. 2006), pair formation is executed on CRSP historical files containing exact point-in-history entry, exit, and delisting dates. 

In this repository:
- Exact historical constituent entry/exit dates are not included in vendor daily bar feeds.
- To prevent artificial alpha claims, we executed **5 distinct hostile universe perturbations**:
  1. **Universe A**: Baseline 100-stock liquid S&P 500 panel.
  2. **Universe B**: 50 long-standing mega-caps continuous since 2010 (historical-safe survivorship benchmark).
  3. **Universe C**: Dynamic 20% random constituent attrition per cohort (simulating delisting/merger churn).
  4. **Universe D**: Strict within-sector pair formations.
  5. **Universe E**: Trailing 50th-percentile dollar volume filter.

---

## 2. Empirical Findings

$$\begin{array}{|l|r|r|r|l|}
\hline
\textbf{Universe Specification} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Max DD} & \textbf{Survival Status} \\
\hline
\text{Universe A (100 Baseline)} & -0.1981 & -1.19\% & -22.30\% & \text{Underperforms 10 bps friction} \\
\mathbf{Universe B\text{ (50 Historical Mega-Caps)}} & \mathbf{+0.2174} & \mathbf{+1.13\%} & \mathbf{-19.94\%} & \mathbf{Survives friction & borrow drag} \\
\text{Universe C (20% Attrition Null)} & -0.1666 & -1.04\% & -14.93\% & \text{Degraded by constituent churn} \\
\text{Universe D (Within-Sector)} & -0.3817 & -1.87\% & -21.11\% & \text{Reduced spread dispersion} \\
\text{Universe E (50% Liquidity Filter)} & -0.1672 & -0.94\% & -17.12\% & \text{Fewer viable mean-reverting pairs} \\
\hline
\end{array}$$

- **Takeaway**: Statistical arbitrage in single stocks is highly sensitive to universe composition. Only liquid, continuous blue-chip mega-caps (Universe B) sustain positive net alpha through realistic execution friction.
