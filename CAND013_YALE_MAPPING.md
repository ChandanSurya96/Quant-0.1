# CAND-013 YALE METHODOLOGY & ACADEMIC TRANSLATION
## Assessment of Hysteresis and Volatility Targeting within Gatev et al. Framework

---

## 1. Academic vs Production Comparison

$$\begin{array}{|l|l|l|l|}
\hline
\textbf{Mechanism} & \textbf{Gatev et al. (2006) / Zhu (2024)} & \textbf{CAND-013 Tested Variant} & \textbf{Academic Compatibility} \\
\hline
\textbf{Entry Trigger} & \text{Fixed } 2.0\sigma\text{ spread divergence} & 2.0\sigma, 2.2\sigma, 2.5\sigma, 3.0\sigma & \text{Tested grid; } 2.0\sigma\text{ is optimal} \\
\hline
\textbf{Exit Trigger} & \text{Zero-crossing } (\text{spread } = 0.0) & \text{Threshold hysteresis } (\sigma_x \in [0.5, 1.0]) & \text{Premature exit violates theory} \\
\hline
\textbf{Portfolio Sizing} & \text{Equal weighting across active pairs} & \text{Inverse-vol risk parity + dynamic vol target} & \text{Layered deleveraging drag} \\
\hline
\end{array}$$

---

## 2. Theoretical Conclusions

1. **Zero-Crossing Necessity**: In Gatev et al. (2006), the fundamental driver of statistical arbitrage profitability is the complete mean-reversion of the spread back to its cointegrated baseline. Exiting at non-zero levels ($\sigma_x \ge 0.5$) leaves positive expected value on the table while still incurring round-trip execution costs.
2. **Recommendation**: Maintain strict $2.0\sigma$ entry and zero-crossing exit in accordance with core econometric theory.
