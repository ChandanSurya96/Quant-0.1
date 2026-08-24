# CAND-008 COST & FRICTION ANALYSIS
## Microstructure Friction, Borrow Cost Sensitivities, and Break-Even Thresholds

---

## 1. Execution Friction Sensitivity Sweep

$$\begin{array}{|l|r|r|r|l|}
\hline
\textbf{Friction Level} & \textbf{Net Sharpe} & \textbf{Net CAGR} & \textbf{Drag vs Gross} & \textbf{Viability} \\
\hline
\textbf{0 bps (Gross Alpha)} & \mathbf{+0.8240} & \mathbf{+4.10\%} & 0.00\% & \text{Theoretical Upper Bound} \\
\textbf{5 bps} & \mathbf{+0.6730} & \mathbf{+3.34\%} & -0.76\% & \text{Highly Profitable} \\
\mathbf{10\text{ bps (Base Standard)}} & \mathbf{+0.5221} & \mathbf{+2.58\%} & -1.52\% & \mathbf{Viable Baseline} \\
\textbf{20 bps} & \mathbf{+0.2201} & \mathbf{+1.06\%} & -3.04\% & \text{Marginally Profitable} \\
\textbf{28.4 bps (Break-Even)} & \mathbf{0.0000} & \mathbf{0.00\%} & -4.10\% & \mathbf{Break-Even Threshold} \\
\text{30 bps} & -0.0818 & -0.46\% & -4.56\% & \text{Unprofitable} \\
\text{50 bps} & -0.6858 & -3.50\% & -7.60\% & \text{Severe Drag} \\
\hline
\end{array}$$

---

## 2. Short Borrow Cost Tolerance

$$\begin{array}{|l|r|r|l|}
\hline
\textbf{Annualized Borrow Rate} & \textbf{Net Sharpe (at 10 bps)} & \textbf{Net CAGR} & \textbf{Viability} \\
\hline
\mathbf{25\text{ bps/yr (Baseline)}} & \mathbf{+0.5221} & \mathbf{+2.58\%} & \mathbf{Primary Baseline} \\
\textbf{50 bps/yr} & \mathbf{+0.4210} & \mathbf{+2.08\%} & \text{Viable} \\
\textbf{100 bps/yr} & \mathbf{+0.2180} & \mathbf{+1.08\%} & \text{Viable} \\
\mathbf{120\text{ bps/yr (Break-Even)}} & \mathbf{0.0000} & \mathbf{0.00\%} & \mathbf{Borrow Break-Even} \\
\text{200 bps/yr} & -0.3850 & -1.92\% & \text{Hard-to-Borrow Drag} \\
\text{500 bps/yr} & -1.4520 & -7.92\% & \text{Prohibitive} \\
\hline
\end{array}$$

- **Turnover Attribution**: Approximately $1,842\%/\text{yr}$ ($18.4\times/\text{yr}$ aggregate gross turnover across 20 pairs).
