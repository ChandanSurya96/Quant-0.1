"""Gates. Each one answers "may this be presented as tradeable?" - never
"is this model valid?".

That distinction is load-bearing. A signal that fails every gate here is still a
perfectly good object of study, and researchers must keep being able to look at
it, plot it and argue with it. What the gates prevent is a weak or contaminated
result being read as a trading recommendation because nothing on the page said
otherwise.

Three independent gates:

  DATA          a single bar beyond +/-25% is far more likely to be an
                unadjusted corporate action than a market move.
  SIGNAL        if the largest available |signal| never reaches the threshold
                the strategy would trade on, there is nothing to trade.
  NULL          the real result has to sit outside the permutation null.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .matrix import signal_vector

# Status vocabulary. "NOT_VALIDATED_AS_TRADEABLE" is a statement about evidence,
# not about correctness; nothing in this module ever emits "invalid".
VALIDATED = "VALIDATED_AS_TRADEABLE"
NOT_VALIDATED = "NOT_VALIDATED_AS_TRADEABLE"
NO_SIGNAL = "NO_ADMISSIBLE_SIGNAL"
CONTAMINATED = "DATA_CONTAMINATED"
RESEARCH_ONLY = "RESEARCH_ONLY"

class DataIntegrityError(Exception):
    """Raised when an unhandled corporate action anomaly gap is detected."""
    pass


CORP_ACTION_THRESHOLD = 0.15
NULL_PERCENTILE_REQUIRED = 95.0


def detect_corporate_actions(close: pd.Series,
                             threshold: float = CORP_ACTION_THRESHOLD) -> list[dict]:
    """Flag single-bar moves large enough to be a corporate action.

    Detection only. Nothing is spliced automatically unless specified by manifest or caller.
    The caller gets the date and a suggested `--splice` argument.
    """
    r = close.pct_change()
    hits = r[np.abs(r) >= threshold]
    return [{
        "date": str(pd.Timestamp(d).date()),
        "return": float(v),
        "suggested_splice": str(pd.Timestamp(d).date()),
        "likely": "unadjusted corporate action (demerger / spin-off / split / rights issue)"
                  if v < 0 else "unadjusted corporate action or genuine gap",
    } for d, v in hits.items()]


def validate_data_integrity(close: pd.Series,
                            ticker: str | None = None,
                            threshold: float = CORP_ACTION_THRESHOLD,
                            raise_on_anomaly: bool = True) -> list[dict]:
    """Validates data integrity against rolling gap anomaly detector (default +/-15%).

    If unhandled anomalies exist and raise_on_anomaly is True, raises DataIntegrityError.
    """
    actions = detect_corporate_actions(close, threshold=threshold)
    if actions and raise_on_anomaly:
        symbol = f" for {ticker!r}" if ticker else ""
        gap_dates = [f"{a['date']} ({a['return']*100:+.2f}%)" for a in actions]
        raise DataIntegrityError(
            f"Unhandled price anomaly gap(s) >= +/-{threshold*100:.0f}% detected{symbol} "
            f"on dates: {gap_dates}. Please update markov2/config/corporate_actions.json."
        )
    return actions


def signal_admissibility(P: np.ndarray, signal_threshold: float) -> dict:
    """Can the signal ever reach the threshold the strategy trades on?

    Uses the existing `signal_threshold` rather than inventing a second knob.
    TMPV.NS peaks at |signal| = 0.073 against a 0.10 gate, so its backtest was
    never a trading result - it was the flat-position path plus noise.
    """
    sig = signal_vector(np.asarray(P, dtype=float))
    max_abs = float(np.abs(sig).max()) if sig.size else 0.0
    admissible = max_abs >= float(signal_threshold)
    return {
        "max_abs_signal": max_abs,
        "signal_threshold": float(signal_threshold),
        "admissible": bool(admissible),
        "status": VALIDATED if admissible else NO_SIGNAL,
        "detail": (f"max|signal| {max_abs:.4f} >= threshold {signal_threshold:.4f}"
                   if admissible else
                   f"max|signal| {max_abs:.4f} < threshold {signal_threshold:.4f}: the "
                   f"signal cannot reach the level the strategy acts on"),
    }


def tradeability(
    *,
    corporate_actions: list[dict],
    spliced_dates: list[str],
    admissibility: dict,
    null_summary: dict | None,
    baseline_verdict: dict | None,
    percentile_required: float = NULL_PERCENTILE_REQUIRED,
) -> dict:
    """Combine the gates into one status plus the reasons behind it.

    Every gate must pass. Any failure downgrades to NOT_VALIDATED_AS_TRADEABLE
    and the result stays fully visible as a research object.
    """
    reasons, failed = [], []

    unhandled = [c for c in corporate_actions if c["date"] not in set(spliced_dates)]
    if unhandled:
        failed.append(CONTAMINATED)
        for c in unhandled:
            reasons.append(f"unhandled {abs(c['return'])*100:.2f}% bar on {c['date']} "
                           f"- rerun with --splice {c['suggested_splice']} or confirm it is real")

    if not admissibility.get("admissible", False):
        failed.append(NO_SIGNAL)
        reasons.append(admissibility.get("detail", "signal below threshold"))

    pct = None
    if null_summary and "sharpe" in null_summary:
        pct = null_summary["sharpe"].get("percentile", float("nan"))
        p = null_summary["sharpe"].get("p_one_sided", float("nan"))
        if not np.isfinite(pct) or pct < percentile_required:
            failed.append("FAILS_NULL")
            reasons.append(f"Sharpe at the {pct:.1f}th percentile of the permutation "
                           f"null (p={p:.4f}); {percentile_required:.0f}th required")
    else:
        failed.append("NULL_NOT_RUN")
        reasons.append("permutation null was not run")

    if baseline_verdict and not baseline_verdict.get("beats", False):
        failed.append("FAILS_BASELINE")
        reasons.append(baseline_verdict.get("verdict", "did not beat the label-only baseline"))

    status = VALIDATED if not failed else NOT_VALIDATED
    return {
        "status": status,
        "failed_gates": failed,
        "reasons": reasons,
        "null_percentile": pct,
        "research_status": RESEARCH_ONLY if failed else VALIDATED,
    }
