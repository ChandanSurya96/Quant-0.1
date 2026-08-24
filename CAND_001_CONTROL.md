# CAND-001 CONTROL SPECIFICATION & REPRODUCIBILITY BASELINE
## Frozen Research Baseline for Systematic Macro Strategy

---

## 1. Baseline Metadata & Source of Truth

- **Strategy Identifier**: `CAND-001` (Momentum-Dominant Macro Alpha Specification)
- **Status**: **`FROZEN RESEARCH CONTROL`**
- **Date Frozen**: 2026-08-24
- **Baseline Git Commit**: `57950cee5d783f96239c462e377114178cfe764c`
- **Execution Architecture**: Physical-Share Accounting Engine (`quant/portfolio/simulator.py`)
- **Simulation Invariant**: $\text{NAV}_t \equiv \text{Cash}_t + \sum_i \text{Shares}_{i,t} \cdot \text{Price}_{i,t}$

---

## 2. Parameter & Factor Configuration

$$\begin{array}{|l|l|l|}
\hline
\textbf{Configuration Parameter} & \textbf{Value} & \textbf{Economic Rationale / Definition} \\
\hline
\text{Universe} & 12\text{ Multi-Asset ETFs} & \text{SPY, EWJ, EFA, EEM, TLT, IEF, BNDX, IGOV, UUP, FXE, FXY, FXB} \\
\text{Asset Classes} & 3\text{ Macro Sectors} & \text{Equities (4), Fixed Income (4), Foreign Exchange (4)} \\
\text{Momentum Factor} & \mathbf{ON\text{ (126 trading days)}} & \text{Medium-term cross-sectional trend relative-strength} \\
\text{Value Factor} & \mathbf{OFF} & \text{Disabled: eliminated factor cannibalization } (\rho = -0.65) \\
\text{Static Carry Factor} & \mathbf{OFF} & \text{Disabled: uninformative static dictionary yields} \\
\text{Portfolio Sizing} & \mathbf{Risk Parity} & \text{Inverse 60-day trailing realized volatility weighting} \\
\text{Turnover Buffer} & \mathbf{Rank Hysteresis} & \text{Hold existing Longs if rank } \le 6\text{; Shorts if rank } \ge 7 \\
\text{Portfolio Capacity} & \text{Top 3 Long / Bottom 3 Short} & \text{6 active positions maximum per rebalance period} \\
\text{Rebalance Frequency} & 21\text{ trading days} & \text{Monthly scheduled execution} \\
\text{Transaction Cost} & 10.0\text{ bps / leg} & \text{Institutional execution friction baseline} \\
\text{Short Borrow Cost} & 25.0\text{ bps annualized} & \text{General Collateral borrow fee on liquid ETFs} \\
\text{Initial Capital} & \$100,000.00 & \text{Cash base at start} \\
\hline
\end{array}$$

---

## 3. Verified Performance Metrics (10-Year Full Sample)

$$\begin{array}{|l|r|}
\hline
\textbf{Institutional Performance Metric} & \textbf{Frozen Baseline Value} \\
\hline
\text{Net Sharpe Ratio} & \mathbf{+0.8100} \\
\text{Net Annualized Return (CAGR)} & \mathbf{+14.56\%} \\
\text{Annualized Volatility} & \mathbf{19.04\%} \\
\text{Sortino Ratio} & \mathbf{+1.2405} \\
\text{Maximum Drawdown} & \mathbf{-28.96\%} \\
\text{Calmar Ratio} & \mathbf{0.5028} \\
\text{Annualized Turnover} & \mathbf{894.33\%/yr\text{ (8.94}\times\text{/yr)}} \\
\text{Total 10-Year Transaction Costs} & \mathbf{\$5,876.42} \\
\text{Final Portfolio NAV} & \mathbf{\$271,730.60} \\
\hline
\end{array}$$

---

## 4. Temporal Walk-Forward & True Out-of-Sample (OOS) Boundaries

$$\begin{array}{|l|l|r|r|r|}
\hline
\textbf{Partition Name} & \textbf{Time Window / Range} & \textbf{Net Sharpe} & \textbf{Net CAGR (\%)} & \textbf{Max Drawdown (\%)} \\
\hline
\text{TRAIN (60\%)} & 2016–2021\text{ (1,111 bars)} & \mathbf{+1.5796} & \mathbf{+32.01\%} & \mathbf{-20.00\%} \\
\text{VALIDATION (20\%)} & 2021–2023\text{ (371 bars)} & -0.1251 & -4.16\% & -23.32\% \\
\text{TRUE OUT-OF-SAMPLE (20\%)} & 2023–2026\text{ (371 bars)} & \mathbf{+0.5870} & \mathbf{+9.93\%} & \mathbf{-22.45\%} \\
\hline
\end{array}$$

- **Gate 3 Corrected Permutation Null ($B=100$)**: $p = 0.0099$ (**PASSED**).
- **Break-Even Execution Friction**: **`155.1 bps`**.

---

## 5. Invariant Rule

> [!IMPORTANT]
> `CAND-001` is the **FROZEN RESEARCH CONTROL**.
> No parameter modifications, optimizations, or factor re-introductions may be applied directly to this control. All future research hypotheses (`CAND-003`, `CAND-004`, `CAND-005`) must be tested in strict comparison against this baseline.
