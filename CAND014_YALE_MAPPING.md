# CAND-014 YALE & MACRO MOMENTUM ARCHITECTURE MAPPING
## Econometric Synthesis with Core Quant-Algorithm Components

---

## 1. Interaction of Regime Conditioning with Multi-Asset Momentum

$$\begin{array}{|l|l|l|}
\hline
\textbf{Subsystem} & \textbf{Native Mechanism} & \textbf{Impact of Regime Filter} \\
\hline
\textbf{Cross-Sectional Ranking} & \text{Top-N vs Bottom-N asset selection} & \text{Filter blind to cross-asset rotations} \\
\textbf{Inverse-Vol Risk Parity} & \text{Normalizes asset risk dynamically} & \text{Filter adds double-deleveraging penalty} \\
\textbf{Statistical Arbitrage Pairs} & \text{Mean-reversion orthogonal hedge} & \text{Pairs hedge remains unimpacted} \\
\hline
\end{array}$$

---

## 2. Definitive Research Recommendation

- Do NOT implement macro trend or breadth filtering on `CAND-006` Momentum.
- Rely on native cross-asset momentum ranking and Inverse-Volatility weighting to manage regime shifts automatically.
- Maintain **`CAND-006`** and **`ENS-80/20`** as canonical frozen controls.
