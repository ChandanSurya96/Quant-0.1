# CAND-012 SYSTEMATIC BORROW COST ANALYSIS
## Evaluation of Short Locate Drag Across 0 to 1000 bps/Year Rates

---

## 1. Systematic Borrow Drag Sweep

$$\begin{array}{|l|r|r|r|l|}
\hline
\textbf{Annualized Borrow Rate} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Max Drawdown} & \textbf{Economic Viability} \\
\hline
\textbf{0 bps/yr (Gross Borrow)} & -0.3692 & -1.74\% & -21.05\% & \text{Theoretical Upper Bound} \\
\mathbf{25\text{ bps/yr (General Collateral)}} & \mathbf{-0.3817} & \mathbf{-1.87\%} & \mathbf{-21.11\%} & \text{Baseline Liquid Short Rate} \\
\textbf{50 bps/yr} & -0.3942 & -1.99\% & -21.18\% & \text{Mild Locate Fee} \\
\textbf{100 bps/yr} & -0.4192 & -2.24\% & -21.31\% & \text{Moderate Locate Fee} \\
\textbf{150 bps/yr} & -0.4442 & -2.49\% & -21.44\% & \text{Elevated Borrow Rate} \\
\textbf{200 bps/yr} & -0.4692 & -2.74\% & -21.57\% & \text{Hard-to-Borrow Tier 1} \\
\textbf{300 bps/yr} & -0.5192 & -3.24\% & -21.83\% & \text{Hard-to-Borrow Tier 2} \\
\textbf{500 bps/yr} & -0.6192 & -4.24\% & -22.35\% & \text{Special Rate Squeeze} \\
\textbf{1000 bps/yr} & -0.8692 & -6.74\% & -23.65\% & \text{Prohibitive Short Cost} \\
\hline
\end{array}$$

---

## 2. Hard-to-Borrow Vulnerability Audit

- In US equity statistical arbitrage, if alpha originates primarily from shorting hard-to-borrow (HTB) names before delistings or earnings misses, that alpha is uncapturable in live execution due to high borrow rates ($> 300\text{ bps/yr}$) or locate buy-ins.
- Because CAND-012 restricts pairs to large-cap S&P 500 equities, short legs fall almost entirely under **General Collateral (GC, $\le 25\text{ bps/yr}$)**, preventing unexpected locate squeezes.
