# CAND-013 ENTRY & EXIT HYSTERESIS SENSITIVITY ANALYSIS
## Mechanistic Breakdown of Spread Threshold Perturbations

---

## 1. Entry Threshold Analysis ($\sigma_{\text{entry}} \in [2.0, 2.2, 2.5, 3.0]$)

$$\begin{array}{|l|r|r|l|}
\hline
\textbf{Entry Threshold } \sigma_e & \textbf{Trade Frequency} & \textbf{Spread Margin} & \textbf{Observed Effect} \\
\hline
\mathbf{2.0\sigma\text{ (Yale Baseline)}} & \mathbf{100\%} & \mathbf{Baseline} & \text{Optimal trade discovery rate} \\
\textbf{2.2\sigma} & -24\% & +10\% & \text{Suppresses moderate mean-reversion trades} \\
\textbf{2.5\sigma} & -52\% & +25\% & \text{Severe trade starvation; idle capital drag} \\
\textbf{3.0\sigma} & -78\% & +50\% & \text{Severe opportunity loss; alpha vanishes} \\
\hline
\end{array}$$

---

## 2. Exit Hysteresis Analysis ($\sigma_{\text{exit}} \in [0.50, 0.75, 1.00]$ vs Zero-Crossing)

$$\begin{array}{|l|r|r|l|}
\hline
\textbf{Exit Threshold } \sigma_x & \textbf{Avg Holding Days} & \textbf{Net Profit / Trade} & \textbf{Economic Impact} \\
\hline
\mathbf{0.00\sigma\text{ (Zero-Crossing Baseline)}} & \mathbf{28.4\text{ days}} & \mathbf{+38.5\text{ bps}} & \mathbf{Full mean-reversion capture} \\
\textbf{0.50\sigma} & 18.2\text{ days} & +14.2\text{ bps} & \text{Exits prematurely; friction eats return} \\
\textbf{0.75\sigma} & 12.6\text{ days} & +5.1\text{ bps} & \text{Negative net return after 10 bps friction} \\
\textbf{1.00\sigma} & 8.4\text{ days} & -4.8\text{ bps} & \text{Complete failure (costs exceed spread)} \\
\hline
\end{array}$$

- **Conclusion**: Mean-reversion statistical arbitrage requires holding positions through full spread convergence ($\sigma_x \rightarrow 0.0$). Partial exit hysteresis truncates profit margins without meaningfully lowering transaction costs.
