# RESEARCH BASELINE RECONCILIATION & CANONICAL CONTROL SPECIFICATION
## Phase 0 Resolution of Historical CAND-001 Discrepancies

---

## 1. Executive Reconciliation Summary

A critical audit was conducted to reconcile the discrepancy between the historical validation report (`CANDIDATE_001_VALIDATION.md`, reporting **Sharpe `+0.8100`**, **CAGR `+14.56%`**, **Max DD `-28.96%`**) and the subsequent adversarial audit report (`ADVERSARIAL_CAND001_AUDIT.md`, reporting **Sharpe `+0.5253`**, **CAGR `+6.87%`**, **Max DD `-23.04%`**).

Both results were independently reproduced from source code, and the exact root causes of the variance were identified and isolated.

---

## 2. Root Cause Audit & Reconciliation Table

$$\begin{array}{|l|l|l|l|l|}
\hline
\textbf{Audit Dimension} & \textbf{Early Validation (Sharpe 0.81)} & \textbf{Adversarial Audit (Sharpe 0.53)} & \textbf{Methodological Variance} & \textbf{Impact on Metrics} \\
\hline
\textbf{Short Borrow Fee} & 0.0\text{ bps/yr (Free Shorting)} & \mathbf{25.0\text{ bps/yr (Realistic Cost)}} & \text{Simulated borrow drag} & \Delta\text{CAGR } -18\text{ bps} \\
\hline
\textbf{Evaluation Slice} & 2017–2026\text{ (Start Idx } 252\text{)} & \mathbf{2019–2026\text{ (Start Idx } 756\text{)}} & 3\text{-year warm-up alignment} & \Delta\text{CAGR } -7.51\% \\
\hline
\textbf{Data Source} & \text{Historical Yahoo ETF Feed} & \text{Cached Validated Fixture} & \text{Rate-limit fallback isolation} & \text{Preserves determinism} \\
\hline
\textbf{Friction Model} & 10.0\text{ bps flat} & 10.0\text{ bps} + 25\text{ bps borrow} & \text{Physical share tracking} & \text{Strict physical accounting} \\
\hline
\textbf{Sortino Metric} & \text{Semi-deviation denominator} & \text{Annualized downside semi-vol} & \text{Formula standardization} & \text{Standardized to 252-day annual} \\
\hline
\end{array}$$

### Key Findings:
1. **The Primary Driver ($\approx 90\%$ of discrepancy)** is the **Active Evaluation Slice Window**:
   - In earlier validation, the strategy began trading at index `252` (after 1 year of price data), capturing the violent 2017–2018 macro equity bull rally.
   - When the 3-year value factor warm-up was frozen at index `756` (3 years of data, active trading beginning in 2019), the 2017–2018 period was excluded, shifting the baseline Sharpe from $+0.8100$ to $+0.5253$.
2. **Short Borrow Drag**: Accruing 25 bps/yr borrow fees on short equity and bond positions further reduced net CAGR from $+7.05\%$ down to $+6.87\%$.

---

## 3. Canonical Control Specification: `CAND-001-FROZEN-CONTROL-V2`

To ensure 100% scientific reproducibility and prevent future methodology drift, the canonical research control is permanently frozen with the following exact specifications:

$$\begin{array}{|l|l|l|}
\hline
\textbf{Configuration Field} & \textbf{Frozen Value} & \textbf{Verification Constraint} \\
\hline
\text{Control Identifier} & \mathbf{CAND-001-FROZEN-CONTROL-V2} & \text{Immutable benchmark for all future research} \\
\text{Universe} & 12\text{ Multi-Asset ETFs} & \text{SPY, EWJ, EFA, EEM, TLT, IEF, BNDX, IGOV, UUP, FXE, FXY, FXB} \\
\text{Evaluation Window} & \text{Index } \mathbf{756} \rightarrow \text{End} & 3\text{-year warm-up period strictly observed} \\
\text{Momentum Factor} & \mathbf{126\text{ trading days (6 Months)}} & \text{Total return relative-strength ranking} \\
\text{Value Factor} & \mathbf{OFF} & \text{Disabled: eliminates factor cannibalization} \\
\text{Static Carry Factor} & \mathbf{OFF} & \text{Disabled: eliminates uninformative static yields} \\
\text{Portfolio Sizing} & \mathbf{Risk Parity} & \text{Inverse 60-day trailing realized volatility} \\
\text{Rank Hysteresis Buffer} & \mathbf{Top 3 Long / Bottom 3 Short} & \text{Hold Long if rank } \le 6\text{; Short if rank } \ge 7 \\
\text{Rebalance Frequency} & \mathbf{21\text{ trading days (Monthly)}} & \text{Scheduled discrete physical-share rebalancing} \\
\text{Execution Friction} & \mathbf{10.0\text{ bps / executed leg}} & \text{Institutional baseline friction} \\
\text{Short Borrow Fee} & \mathbf{25.0\text{ bps annualized}} & \text{Daily accrued short carrying cost} \\
\text{Initial Capital} & \mathbf{\$100,000.00} & \text{Cash base} \\
\hline
\end{array}$$

---

## 4. Frozen Canonical Baseline Metrics

$$\begin{array}{|l|r|}
\hline
\textbf{Institutional Performance Metric} & \textbf{CAND-001-FROZEN-CONTROL-V2 Value} \\
\hline
\text{Net Sharpe Ratio (10 bps friction + 25 bps borrow)} & \mathbf{+0.5253} \\
\text{Net Annualized Return (CAGR)} & \mathbf{+6.87\%} \\
\text{Annualized Volatility} & \mathbf{14.71\%} \\
\text{Sortino Ratio} & \mathbf{+0.6107} \\
\text{Maximum Drawdown} & \mathbf{-23.04\%} \\
\text{Annualized Turnover} & \mathbf{893.4\%/yr\text{ (8.93}\times\text{/yr)}} \\
\text{10-Year Transaction Friction Paid} & \mathbf{\$7,405.56} \\
\text{True Out-of-Sample Sharpe (2023–2026)} & \mathbf{+0.5284} \\
\text{True Out-of-Sample CAGR (2023–2026)} & \mathbf{+6.40\%} \\
\text{Friction Break-Even Level} & \mathbf{93.4\text{ bps}} \\
\hline
\end{array}$$

---

## 5. Invariant Rule for All Future Research

> [!IMPORTANT]
> All candidate hypotheses (`CAND-010A`, `CAND-010B`, `CAND-010C`, `CAND-010D`, `CAND-010E`) must be evaluated against **`CAND-001-FROZEN-CONTROL-V2`** under the exact same universe, date slicing (`start_idx = 756`), friction (10 bps), borrow fee (25 bps), and temporal splits (Train 60%, Val 20%, True OOS 20%).
