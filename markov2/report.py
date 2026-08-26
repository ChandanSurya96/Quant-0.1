"""Report rendering, split into the four things a reader has to judge separately.

    DATA      can the input be trusted?
    REGIME    does the matrix say anything the state mix did not already say?
    STRATEGY  did it beat buy-and-hold AND the matrix-free control?
    NULL      could an uninformative label sequence have done as well?

Previously these were interleaved, so a clean label-verification PASS sat a few
lines above a backtest built on a contaminated series and the eye carried the
PASS downward. Separating them makes each claim stand on its own evidence.
"""

from __future__ import annotations

import numpy as np

from .gates import VALIDATED
from .states import N_STATES, STATE_NAMES

RULE = "=" * 78
SUB = "-" * 78


def header(title: str) -> str:
    return f"\n{RULE}\n {title}\n{RULE}"


def _pf(v: float) -> str:
    return "inf" if not np.isfinite(v) else f"{v:.2f}"


# ------------------------------------------------------------------ 1. DATA
def render_data(ticker: str, close, bars: int, corp: list[dict], spliced: list[dict],
                eval_start, eval_end, eval_bars: int, missing: int) -> str:
    L = [header("1. DATA VALIDATION")]
    L.append(f"  ticker              {ticker}")
    L.append(f"  bars                {bars}   {close.index.min().date()} -> {close.index.max().date()}")
    L.append(f"  evaluation period   {eval_start} -> {eval_end}  ({eval_bars} bars)")
    L.append(f"  missing closes      {missing}")

    if spliced:
        L.append("\n  splice status       APPLIED")
        for a in spliced:
            if a.get("ok"):
                L.append(f"    {a['date']}  raw bar {a['raw_move_pct']:+.2f}% neutralised "
                         f"(pre-event prices x{a['ratio']:.4f})")
            else:
                L.append(f"    {a['date']}  NOT APPLIED - {a['why']}")
        L.append("    Pre-event history is in post-event units and describes the FORMER entity.")
    else:
        L.append("\n  splice status       none applied")

    if not corp:
        L.append("\n  suspicious bars     none (no single bar beyond +/-25%)")
    else:
        handled = {a["date"] for a in spliced if a.get("ok")}
        L.append(f"\n  suspicious bars     {len(corp)} DETECTED")
        for c in corp:
            mark = "HANDLED  " if c["date"] in handled else "UNHANDLED"
            L.append(f"    [{mark}] {c['date']}  {c['return']*100:+.2f}%  - {c['likely']}")
            if c["date"] not in handled:
                L.append(f"                 rerun with --splice {c['suggested_splice']}, "
                         f"or confirm the move is genuine")
        L.append("    Not auto-spliced: a large move can be real, and back-adjusting a")
        L.append("    genuine one corrupts the series as badly as leaving an artefact in.")
    return "\n".join(L)


# ---------------------------------------------------------------- 2. REGIME
def render_regime(dist, cells: list[dict], counts, stride: int, stride_mode: str,
                  admissibility: dict, signal_vec, decay: list[dict]) -> str:
    L = [header("2. REGIME VALIDATION")]
    L.append("  state distribution  " + "   ".join(
        f"{STATE_NAMES[s]} {dist[s]*100:.2f}%" for s in range(N_STATES)))

    L.append(f"\n  Corrected transition matrix (stride={stride}, mode={stride_mode})")
    L.append("  Every cell carries its own interval. n_eff deflates the raw count by")
    L.append(f"  {stride} because the (t, t+{stride}) pairs overlap each other.\n")
    L.append(f"    {'transition':<22s}{'count':>11s}{'p':>9s}{'n_eff':>8s}"
             f"{'base':>8s}{'lift':>9s}{'95% CI':>18s}   verdict")
    for c in cells:
        name = f"{c['from']} -> {c['to']}"
        cnt = f"{int(c['count'])}/{int(c['row_total'])}"
        ci = f"[{c['ci_lo']*100:.1f}%, {c['ci_hi']*100:.1f}%]"
        flag = "<< CI CONTAINS BASE RATE" if c["contains_base"] else "   distinguishable"
        L.append(f"    {name:<22s}{cnt:>11s}{c['p']*100:8.2f}%{c['n_eff']:8.1f}"
                 f"{c['base_rate']*100:7.2f}%{c['lift_pp']:+8.2f}pp{ci:>18s}   {flag}")

    thin = sorted({c["from"] for c in cells if c["thin"]})
    n_contains = sum(1 for c in cells if c["contains_base"])
    L.append(f"\n  {n_contains} of {len(cells)} cells have a 95% CI containing the unconditional")
    L.append("  base rate: those cells are not distinguishable from the state mix alone.")
    if thin:
        L.append(f"  THIN ROWS (n_eff < 30, percentages far less precise than they look): "
                 f"{', '.join(thin)}")

    L.append("\n  Signal magnitude  (P(BULL next) - P(BEAR next))")
    for s in range(N_STATES):
        L.append(f"    {STATE_NAMES[s]:>10s} {signal_vec[s]:+.4f}")
    a = admissibility
    L.append(f"\n    max|signal|       {a['max_abs_signal']:.4f}")
    L.append(f"    signal_threshold  {a['signal_threshold']:.4f}")
    if a["admissible"]:
        L.append(f"    ADMISSIBLE - {a['detail']}")
    else:
        L.append(f"    *** {a['status']} ***")
        L.append(f"    {a['detail']}.")
        L.append(f"    A strategy gated at +/-{a['signal_threshold']:.2f} can never act on this")
        L.append("    matrix; any backtest below is the flat-position path plus noise.")

    if decay:
        L.append(f"\n  Forecast decay        {'horizon':>8s} {'max|signal|':>13s} {'TV to pi':>11s}")
        for row in decay:
            L.append(f"    {'':<18s}{row['horizon']:>8d} {row['max_signal']:>13.4f} "
                     f"{row['tv_distance_to_stationary']:>11.4f}")
    return "\n".join(L)


# -------------------------------------------------------------- 3. STRATEGY
def render_strategy(rows: list[dict], cost_bps: float, baseline_verdict: dict) -> str:
    L = [header("3. STRATEGY VALIDATION")]
    L.append(f"  Costs charged at {cost_bps:.1f} bps per unit of |position change|.")
    L.append("  Gross is the pre-cost path (the module's original convention).\n")
    L.append(f"    {'strategy':<44s}{'grossSh':>8s}{'netSh':>8s}{'CAGR':>9s}"
             f"{'maxDD':>9s}{'PF':>6s}{'exp':>7s}{'turn/yr':>9s}")
    for r in rows:
        L.append(f"    {r['name']:<44s}{r['gross_sharpe']:8.3f}{r['net_sharpe']:8.3f}"
                 f"{r['cagr']*100:8.2f}%{r['max_drawdown']*100:8.2f}%"
                 f"{_pf(r['profit_factor']):>6s}{r['exposure']*100:6.1f}%"
                 f"{r['turnover_annualised']:9.2f}")
    L.append("\n  MANDATORY CONTROL")
    L.append(f"    Markov {baseline_verdict['markov']:.4f}  vs  label-only baseline "
             f"{baseline_verdict['baseline']:.4f}   (delta {baseline_verdict['delta']:+.4f})")
    L.append(f"    {baseline_verdict['verdict']}")
    return "\n".join(L)


# ------------------------------------------------------------------ 4. NULL
def render_null(summary: dict, n_perm: int, method: str, trade: dict) -> str:
    L = [header("4. NULL VALIDATION")]
    if method == "rotate":
        blurb = ("circular rotation - preserves counts, run lengths, autocorrelation "
                 "and stride geometry; breaks only label/return alignment")
    else:
        blurb = "i.i.d. shuffle - SECONDARY null, anti-conservative, not a gate"
    L.append(f"  permutations        {n_perm}")
    L.append(f"  method              {method} ({blurb})")
    if not summary:
        L.append("\n  null not run")
    else:
        L.append(f"\n    {'metric':<16s}{'real':>10s}{'null mean':>11s}{'median':>10s}"
                 f"{'5th':>10s}{'95th':>10s}{'pctile':>9s}{'p(1-sided)':>12s}")
        for key, s in summary.items():
            L.append(f"    {key:<16s}{s['real']:10.3f}{s['mean']:11.3f}{s['median']:10.3f}"
                     f"{s['q05']:10.3f}{s['q95']:10.3f}{s['percentile']:8.1f}%{s['p_one_sided']:12.4f}")

    L.append(f"\n  {SUB}")
    L.append(f"  TRADEABILITY STATUS   {trade['status']}")
    L.append(f"  {SUB}")
    if trade["status"] == VALIDATED:
        L.append("    All gates passed.")
    else:
        L.append(f"    failed gates: {', '.join(trade['failed_gates'])}")
        for r in trade["reasons"]:
            L.append(f"      - {r}")
        L.append("")
        L.append("    NOT_VALIDATED_AS_TRADEABLE is a statement about EVIDENCE, not about")
        L.append("    correctness. The model is not broken and the diagnostics above remain")
        L.append("    valid research output - inspect them freely. What this status withholds")
        L.append("    is the claim that the result is fit to trade.")
    return "\n".join(L)
