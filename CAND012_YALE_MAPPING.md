# YALE RESEARCH MAPPING & TRANSLATION MATRIX: CAND-012
## Methodological Faithful Mapping of Zhu (2024) / Gatev et al. (2006)

---

## 1. Academic Concept vs Quant-Algorithm Translation

$$\begin{array}{|l|l|l|l|}
\hline
\textbf{Yale Paper Specification} & \textbf{Our Implementation} & \textbf{Classification} & \textbf{Reason / Invariant} \\
\hline
\textbf{SSD Distance Metric} & \text{Trailing 252d normalized Euclidean distance} & \mathbf{Faithful} & \text{Identical to Gatev formula} \\
\hline
\textbf{Wait-One-Day Execution Lag} & \text{Signal at } t \rightarrow \text{Execution at } t+1\text{ close} & \mathbf{Faithful} & \text{Eliminates bid-ask bounce} \\
\hline
\textbf{Overlapping 6M Cohorts} & 6\text{ concurrent monthly cohorts (21d step)} & \mathbf{Faithful} & \text{Smooths cohort exits} \\
\hline
\textbf{Sector Neutrality} & \text{Constrained within 11 GICS sectors} & \mathbf{Extension} & \text{Tested in Universe D} \\
\hline
\textbf{Physical-Share Accounting} & \text{Cash conservation, discrete integer shares} & \mathbf{Engineering} & \text{Institutional realism} \\
\hline
\end{array}$$

---

## 2. Potential Biases Identified

1. **Constituent Bias**: Using current S&P 500 membership produces an optimistic bias relative to point-in-history CRSP files. Conservative stress testing (Universes B, C, D) successfully bounded this effect.
2. **Borrow Cost Under-estimation**: Uniform 25 bps borrow assumptions can hide short-side drag; systematic sweeping up to 1000 bps/yr confirmed borrow cost bounds.
