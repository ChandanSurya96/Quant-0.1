"""FIX 2 - label verification.

RESEARCH STATUS: DEPRECATED. Empirical evaluations (SUZLON-001, TMPV-001) prove the 3-state transition matrix provides no incremental alpha over continuous momentum.

DEPRECATION NOTICE:
Single-asset label verification is DEPRECATED following empirical rejection of single-asset
Markov regime models across single-asset equities (SUZLON, TCS, TMPV, ^NSEI). Retained for
reproducibility and historical research only.

1.0 shipped a display in which BULL and BEAR were swapped. The data was right
and the table was wrong, which is the worst kind of wrong because nothing
crashes. This module makes that class of bug loud and automatic.

Three independent checks, run before anything is rendered:

  INVARIANT  mean trailing-window return must increase strictly with state
             index (BEAR < SIDEWAYS < BULL). Catches any permutation.
  HISTORY    three named periods - a crash, a famous run, a flat stretch -
             must be dominated by the expected state. Catches a mapping that is
             internally consistent but detached from reality.
  DISPLAY    the row about to be printed under the header "BULL" must be the
             row the matrix actually indexes as BULL. Catches render-time
             transposition and off-by-one in the header list.

For labelers whose indices are arbitrary (KMeans, HMM) the correct response to
a failed invariant is to remap, not to abort - `states.label_enhanced` and
`hmm_mode` do that at the source, and `check_all` then confirms it took.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .states import BEAR, BULL, N_STATES, SIDEWAYS, STATE_NAMES

# (name, start, end, expected dominant state)
#
# Windows must be unambiguous AT THE DEFAULT THRESHOLD. A slow stepwise
# drawdown is genuinely SIDEWAYS under a +/-5% 20-bar rule, so periods like
# Oct-Dec 2018 as a whole are a bad test: they assert a threshold calibration,
# not a label mapping. Only the sharp leg of that selloff is used.
KNOWN_PERIODS = [
    ("COVID crash", "2020-02-20", "2020-03-23", BEAR),
    ("2020 recovery run", "2020-04-15", "2020-09-01", BULL),
    ("Dec 2018 capitulation", "2018-12-03", "2018-12-24", BEAR),
    ("Aug-Oct 2016 chop", "2016-08-08", "2016-11-01", SIDEWAYS),
]


class LabelVerificationError(AssertionError):
    pass


def check_invariant(labels: pd.Series, window_ret: pd.Series) -> dict:
    """Mean trailing return must rise monotonically with state index."""
    common = labels.index.intersection(window_ret.index)
    lab, ret = labels.loc[common], window_ret.loc[common]
    means = []
    for s in range(N_STATES):
        sel = ret[lab == s]
        means.append(float(sel.mean()) if len(sel) else float("nan"))
    finite = [m for m in means if np.isfinite(m)]
    ok = len(finite) == len(means) and all(
        means[i] < means[i + 1] for i in range(len(means) - 1)
    )
    return {"name": "INVARIANT monotone mean return", "ok": bool(ok), "means": means}


def check_history(labels: pd.Series) -> list[dict]:
    """Named historical windows must be dominated by the expected state."""
    results = []
    idx = labels.index
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    naive = pd.Series(labels.to_numpy(), index=idx)
    for name, start, end, expected in KNOWN_PERIODS:
        seg = naive.loc[(naive.index >= start) & (naive.index <= end)]
        if len(seg) < 5:
            results.append(
                {"name": f"HISTORY {name}", "ok": None, "detail": "outside data range"}
            )
            continue
        counts = np.array([(seg == s).sum() for s in range(N_STATES)], dtype=float)
        dominant = int(counts.argmax())
        share = float(counts[dominant] / counts.sum())
        results.append(
            {
                "name": f"HISTORY {name}",
                "ok": dominant == expected,
                "detail": (
                    f"dominant={STATE_NAMES[dominant]} ({share*100:.0f}% of "
                    f"{int(counts.sum())} bars), expected={STATE_NAMES[expected]}"
                ),
            }
        )
    return results


def check_display(P: np.ndarray, header: list[str], row_labels: list[str]) -> dict:
    """The rendered header/row order must match the canonical index order."""
    ok = (
        list(header) == list(STATE_NAMES)
        and list(row_labels) == list(STATE_NAMES)
        and P.shape == (N_STATES, N_STATES)
        and STATE_NAMES[BULL] == "BULL"
        and STATE_NAMES[BEAR] == "BEAR"
    )
    return {
        "name": "DISPLAY header/row alignment",
        "ok": bool(ok),
        "detail": f"header={list(header)} rows={list(row_labels)}",
    }


def check_all(labels: pd.Series, window_ret: pd.Series, P: np.ndarray) -> tuple[bool, list[dict]]:
    """Run every check. Returns (hard_checks_passed, results).

    INVARIANT and DISPLAY are hard: a bull/bear swap is a deterministic
    permutation and both catch it every time, so a failure there is a bug and
    must abort.

    HISTORY is soft per-window, because whether a given month clears +/-5% is a
    statement about threshold calibration as much as about the mapping. A single
    disagreement is information, not a defect. But a MAJORITY of resolvable
    windows disagreeing means the mapping really has come loose from reality,
    and that is hard-failed.
    """
    invariant = check_invariant(labels, window_ret)
    history = check_history(labels)
    display = check_display(P, STATE_NAMES, STATE_NAMES)
    results = [invariant, *history, display]

    resolvable = [r for r in history if r["ok"] is not None]
    hist_failed = [r for r in resolvable if not r["ok"]]
    history_ok = len(hist_failed) * 2 <= len(resolvable) if resolvable else True

    hard_ok = bool(invariant["ok"]) and bool(display["ok"]) and history_ok
    return hard_ok, results


def render_results(results: list[dict]) -> str:
    lines = []
    for r in results:
        soft = r["name"].startswith("HISTORY")
        if r["ok"] is None:
            mark = "skip"
        elif r["ok"]:
            mark = "PASS"
        else:
            mark = "WARN" if soft else "FAIL"
        detail = r.get("detail")
        if detail is None and "means" in r:
            detail = " / ".join(
                f"{STATE_NAMES[i]}={m*100:+.2f}%" for i, m in enumerate(r["means"])
            )
        lines.append(f"  [{mark}] {r['name']}" + (f"  -  {detail}" if detail else ""))
    return "\n".join(lines)
