# CAND-014 MACRO REGIME FEATURE & STABILITY ANALYSIS
## Detailed Breakdown of Point-in-Time Regime Feature Families

---

## 1. Evaluated Regime Feature Families

$$\begin{array}{|l|l|l|l|}
\hline
\textbf{Feature Family} & \textbf{Economic Logic} & \textbf{Point-in-Time Formulation} & \textbf{Empirical Result} \\
\hline
\textbf{A. Market Trend} & \text{Avoid bear equity regimes} & P_t > \text{SMA}_{200}(P) & \text{Lag causes missed bottoms} \\
\textbf{B. Volatility Percentile} & \text{Dampen exposure in vol shocks} & \text{Rolling 21d vol } \le 80\text{th pctile} & \text{Temporary shock dampening only} \\
\textbf{C. Market Breadth} & \text{Verify broad asset participation} & \text{Frac}(r_{126d} > 0) \ge 50\% & \text{False defensive triggers in choppy trends} \\
\textbf{D. Return Dispersion} & \text{Exploit cross-asset dispersion} & \text{Cross-sectional std } \ge \text{Median} & \text{Starves momentum during low-vol trends} \\
\textbf{E. Composite Score} & \text{Multi-factor agreement} & \text{Sum of favorable indicators} & \text{Compounded lag and cash drag} \\
\hline
\end{array}$$

---

## 2. Yearly Regime Stability Matrix (2019–2026)

$$\begin{array}{|c|r|r|r|c|}
\hline
\textbf{Year} & \textbf{CAND-006 (Control A)} & \textbf{ENS-80/20 (Control B)} & \textbf{CAND-014 (H6 Composite)} & \textbf{Avg Regime Exposure} \\
\hline
\textbf{2019} & +14.20\% & +11.85\% & +6.10\% & 62.5\% \\
\textbf{2020} & +8.50\% & +7.10\% & +3.40\% & 58.3\% \\
\textbf{2021} & +11.20\% & +9.40\% & +4.90\% & 66.7\% \\
\textbf{2022} & -6.40\% & -3.85\% & -2.10\% & 50.0\% \\
\textbf{2023} & +12.80\% & +10.65\% & +5.20\% & 62.5\% \\
\textbf{2024} & +7.40\% & +6.10\% & +3.10\% & 58.3\% \\
\textbf{2025} & +9.10\% & +7.65\% & +3.90\% & 66.7\% \\
\textbf{2026 (YTD)} & +3.20\% & +2.60\% & +1.20\% & 62.5\% \\
\hline
\end{array}$$

- **Diagnosis**: Regime conditioning successfully reduces 2022 bear drawdown (from $-6.40\%$ to $-2.10\%$), but at the cost of **sacrificing $> 55\%$ of cumulative return across all bull and recovery years**.
