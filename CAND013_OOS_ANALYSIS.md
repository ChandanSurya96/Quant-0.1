# CAND-013 OUT-OF-SAMPLE (OOS) TEMPORAL ANALYSIS
## Walk-Forward Partitioning Across Train (60%), Val (20%), and True OOS (20%)

---

## 1. Walk-Forward Results Matrix

$$\begin{array}{|l|r|r|r|r|r|r|}
\hline
\textbf{Specification} & \textbf{Train Sharpe} & \textbf{Train CAGR} & \textbf{Val Sharpe} & \textbf{Val CAGR} & \textbf{OOS Sharpe} & \textbf{OOS CAGR} \\
\hline
\mathbf{Frozen\text{ }Control\text{ (ENS-80/20)}} & \mathbf{+0.4320} & \mathbf{+4.55\%} & \mathbf{+0.5210} & \mathbf{+5.75\%} & \mathbf{+0.5340} & \mathbf{+5.70\%} \\
\text{Candidate (E2.0\_X0.50\_V8)} & +0.2210 & +1.50\% & +0.2640 & +1.95\% & \mathbf{+0.1892} & \mathbf{+1.20\%} \\
\text{Candidate (E2.2\_X0.75\_V10)} & +0.1850 & +1.15\% & +0.2180 & +1.55\% & \mathbf{+0.1540} & \mathbf{+0.95\%} \\
\text{Candidate (E2.5\_X1.00\_V12)} & +0.1420 & +0.85\% & +0.1710 & +1.10\% & \mathbf{+0.1120} & \mathbf{+0.70\%} \\
\hline
\end{array}$$

- **OOS Verdict**: `CAND-013` fails the hard criteria of True OOS Sharpe $\ge 0.50$ and True OOS CAGR $\ge 4.5\%$. The Frozen Control significantly outperforms all tested parameter variants in out-of-sample data.
