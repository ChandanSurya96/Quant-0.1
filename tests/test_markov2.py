"""Regression tests for Markov 2.0.

The point of this file is that the corrected estimator keeps producing the
numbers the validation study verified, and that none of the new honesty
machinery quietly changes them. Fixtures are pinned OHLCV CSVs so the suite is
deterministic and runs offline - a test that depends on Yahoo is not a
regression test.

Reference values below were produced by the pre-change implementation and
re-verified independently during the validation study.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from markov2.backtest import (
    apply_costs,
    turnover,
    walk_forward,
    walk_forward_signals,
)
from markov2.baseline import (
    markov_adds_value,
    run_label_only,
    trailing_return_positions,
)
from markov2.data import splice
from markov2.gates import (
    NOT_VALIDATED,
    VALIDATED,
    detect_corporate_actions,
    signal_admissibility,
    tradeability,
)
from markov2.matrix import build, counts_overlapping, counts_stride, counts_to_matrix
from markov2.nulls import circular_rotation, iid_shuffle, permutation_null
from markov2.states import BEAR, BULL, SIDEWAYS, label_threshold, state_distribution
from markov2.stats import cell_stats, effective_n, percentile_and_p, wilson

FIXTURES = Path(__file__).parent / "fixtures"
RTOL = 1e-9
MIN_TRAIN = 756


def load_fixture(ticker: str) -> pd.DataFrame:
    df = pd.read_csv(FIXTURES / f"{ticker}.csv", index_col=0, parse_dates=True)
    return df.dropna(subset=["Close"])


@pytest.fixture(scope="module")
def tcs():
    df = load_fixture("TCS.NS")
    close = df["Close"]
    return df, close, label_threshold(close, 20, 0.05)


@pytest.fixture(scope="module")
def tmpv_spliced():
    df = load_fixture("TMPV.NS")
    df2, applied = splice(df, ["2025-10-14"])
    close = df2["Close"]
    return df2, close, label_threshold(close, 20, 0.05), applied


# ------------------------------------------------------- 1. stride-20 estimation
def test_stride_counts_only_pair_non_overlapping_windows():
    lab = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0], dtype=int)
    c = counts_stride(lab, stride=3, mode="phase")
    # phase mode pairs (t, t+3) for every t; with this period-3 series every pair
    # is state -> same state, so all mass must sit on the diagonal.
    assert np.allclose(c, np.diag(np.diag(c)))
    assert c.sum() == len(lab) - 3


def test_stride_single_mode_thins_the_chain():
    lab = np.arange(30) % 3
    c = counts_stride(lab, stride=3, mode="single")
    assert c.sum() == len(lab[::3]) - 1


def test_stride_matrix_reproduces_verified_tcs_values(tcs):
    _, _, labels = tcs
    b = build(labels, stride=20, stride_mode="phase")
    c = b["counts_stride"]
    # Verified during the validation study.
    assert int(c[BULL, SIDEWAYS]) == 416
    assert int(c[BULL].sum()) == 656
    assert int(c[BEAR, SIDEWAYS]) == 210
    assert int(c[BEAR].sum()) == 431
    assert int(c[SIDEWAYS, SIDEWAYS]) == 707
    assert int(c[SIDEWAYS].sum()) == 1344
    assert b["P_stride"][BULL, SIDEWAYS] == pytest.approx(0.6341463414634146, rel=RTOL)
    assert np.diag(b["P_stride"]) == pytest.approx([0.14153, 0.52604, 0.17988], abs=1e-5)
    # the legacy matrix must remain available and remain biased
    assert np.diag(b["P_overlapping"]) == pytest.approx([0.80974, 0.86542, 0.85312], abs=1e-5)


def test_unobserved_row_is_flagged_not_invented():
    c = np.zeros((3, 3))
    c[0, 1] = 5
    P, unobserved = counts_to_matrix(c)
    assert unobserved == [1, 2]
    assert np.allclose(P[1], 1 / 3)


# ------------------------------------------------------------- 2. n_eff
def test_effective_n_deflates_phase_mode_by_stride():
    assert effective_n(656, 20, "phase") == pytest.approx(32.8)
    assert effective_n(656, 20, "single") == 656.0
    with pytest.raises(ValueError):
        effective_n(10, 20, "nonsense")


def test_n_eff_matches_validated_tcs_rows(tcs):
    _, _, labels = tcs
    c = build(labels, stride=20, stride_mode="phase")["counts_stride"]
    assert effective_n(c[BULL].sum(), 20) == pytest.approx(32.8, abs=0.05)
    assert effective_n(c[BEAR].sum(), 20) == pytest.approx(21.55, abs=0.05)
    assert effective_n(c[SIDEWAYS].sum(), 20) == pytest.approx(67.2, abs=0.05)


# --------------------------------------------------------------- 3. Wilson CI
def test_wilson_reproduces_the_validated_bull_sideways_interval():
    lo, hi = wilson(0.6341463414634146 * 32.8, 32.8)
    assert lo == pytest.approx(0.463, abs=0.002)
    assert hi == pytest.approx(0.777, abs=0.002)


def test_wilson_stays_inside_unit_interval_at_extremes():
    for k, n in ((0, 5), (5, 5), (0.5, 1)):
        lo, hi = wilson(k, n)
        assert 0.0 <= lo <= hi <= 1.0


def test_wilson_interval_narrows_as_n_grows():
    widths = [wilson(0.5 * n, n)[1] - wilson(0.5 * n, n)[0] for n in (10, 100, 1000)]
    assert widths[0] > widths[1] > widths[2]


def test_cell_stats_flags_ci_containing_base_rate(tcs):
    _, _, labels = tcs
    c = build(labels, stride=20, stride_mode="phase")["counts_stride"]
    cells = cell_stats(c, state_distribution(labels), 20, "phase")
    cell = next(x for x in cells if x["from"] == "BULL" and x["to"] == "SIDEWAYS")
    assert cell["count"] == 416
    assert cell["p"] == pytest.approx(0.6341, abs=1e-4)
    assert cell["n_eff"] == pytest.approx(32.8, abs=0.05)
    assert cell["base_rate"] == pytest.approx(0.5488, abs=1e-4)
    assert cell["lift_pp"] == pytest.approx(8.53, abs=0.05)
    # The validation conclusion: not distinguishable from the base rate.
    assert cell["contains_base"] is True
    # BULL clears the n_eff>=30 bar (32.8); BEAR does not (21.6). Only BEAR is thin.
    assert cell["thin"] is False
    bear_cell = next(x for x in cells if x["from"] == "BEAR" and x["to"] == "SIDEWAYS")
    assert bear_cell["thin"] is True
    # Every cell in the TCS matrix is indistinguishable from its base rate.
    assert all(x["contains_base"] for x in cells)


# ------------------------------------------- 4. circular permutation properties
def test_circular_rotation_preserves_counts_and_run_structure():
    rng = np.random.default_rng(0)
    lab = rng.integers(0, 3, 500)
    rot = circular_rotation(lab, 137)
    assert np.array_equal(np.bincount(lab, minlength=3), np.bincount(rot, minlength=3))
    # run-length multiset is preserved (rotation can only join/split at the seam)
    def runs(a):
        return sorted(len(list(g)) for _, g in __import__("itertools").groupby(a))
    assert sum(runs(rot)) == sum(runs(lab))
    assert len(rot) == len(lab)


def test_circular_rotation_preserves_the_transition_matrix():
    rng = np.random.default_rng(1)
    lab = rng.integers(0, 3, 1000)
    a = counts_stride(lab, stride=20, mode="phase")
    b = counts_stride(circular_rotation(lab, 333), stride=20, mode="phase")
    # rotation only re-phases; total transition mass is unchanged
    assert a.sum() == b.sum()


def test_iid_shuffle_preserves_counts_but_destroys_autocorrelation():
    rng = np.random.default_rng(2)
    lab = np.repeat(np.arange(3), 200)  # maximal autocorrelation
    sh = iid_shuffle(lab, rng)
    assert np.array_equal(np.bincount(lab, minlength=3), np.bincount(sh, minlength=3))
    same_lab = float((lab[:-1] == lab[1:]).mean())
    same_sh = float((sh[:-1] == sh[1:]).mean())
    assert same_lab > 0.99 and same_sh < 0.5


def test_permutation_null_runs_requested_count_and_is_seed_reproducible():
    lab = np.random.default_rng(3).integers(0, 3, 300)
    calls = []

    def evaluate(perm):
        calls.append(perm.copy())
        return {"sharpe": float(perm[0]), "cagr": 0.0,
                "max_drawdown": -0.1, "profit_factor": 1.0, "exposure": 1.0}

    a = permutation_null(lab, evaluate, n_perm=25, method="rotate", seed=7, guard=10)
    b = permutation_null(lab, evaluate, n_perm=25, method="rotate", seed=7, guard=10)
    assert len(a) == 25
    assert a["sharpe"].tolist() == b["sharpe"].tolist()
    assert set(a.columns) >= {"sharpe", "cagr", "max_drawdown", "profit_factor"}


def test_percentile_and_p_use_finite_sample_correction():
    null = np.zeros(999)
    out = percentile_and_p(null, 1.0)
    assert out["percentile"] == 100.0
    assert out["p_one_sided"] == pytest.approx(1 / 1000)   # never exactly zero
    assert out["p_one_sided"] > 0.0


# -------------------------------------------------------- 5. signal-threshold gate
def test_admissible_when_signal_reaches_threshold():
    P = np.array([[0.1, 0.2, 0.7], [1 / 3, 1 / 3, 1 / 3], [0.7, 0.2, 0.1]])
    out = signal_admissibility(P, 0.10)
    assert out["admissible"] is True
    assert out["status"] == VALIDATED
    assert out["max_abs_signal"] == pytest.approx(0.6)


def test_no_admissible_signal_when_below_threshold():
    P = np.array([[0.33, 0.34, 0.33], [0.34, 0.33, 0.33], [0.33, 0.33, 0.34]])
    out = signal_admissibility(P, 0.10)
    assert out["admissible"] is False
    assert out["status"] == "NO_ADMISSIBLE_SIGNAL"


def test_tmpv_signal_is_inadmissible_at_default_threshold(tmpv_spliced):
    _, _, labels, _ = tmpv_spliced
    P = build(labels, stride=20, stride_mode="phase")["P_stride"]
    out = signal_admissibility(P, 0.10)
    # validated value: TMPV peaks at ~0.073 against a 0.10 gate
    assert out["max_abs_signal"] < 0.10
    assert out["status"] == "NO_ADMISSIBLE_SIGNAL"


# ------------------------------------------------ 6/7. corporate-action detection
def test_no_false_positive_on_a_clean_series(tcs):
    _, close, _ = tcs
    assert detect_corporate_actions(close, 0.25) == []


def test_detects_tmpv_2025_10_14_demerger():
    df = load_fixture("TMPV.NS")
    hits = detect_corporate_actions(df["Close"], 0.25)
    assert len(hits) == 1
    hit = hits[0]
    assert hit["date"] == "2025-10-14"
    assert hit["return"] == pytest.approx(-0.4015, abs=5e-4)
    assert hit["suggested_splice"] == "2025-10-14"


def test_detection_is_not_auto_splice():
    """A detected bar must not be silently modified - only reported."""
    df = load_fixture("TMPV.NS")
    before = df["Close"].copy()
    detect_corporate_actions(df["Close"], 0.25)
    pd.testing.assert_series_equal(before, df["Close"])


def test_splice_neutralises_the_demerger_bar():
    df = load_fixture("TMPV.NS")
    out, applied = splice(df, ["2025-10-14"])
    assert applied[0]["ok"] is True
    assert applied[0]["raw_move_pct"] == pytest.approx(-40.15, abs=0.05)
    assert detect_corporate_actions(out["Close"], 0.25) == []


def test_unhandled_corporate_action_blocks_a_tradeable_verdict():
    corp = [{"date": "2025-10-14", "return": -0.4015, "suggested_splice": "2025-10-14",
             "likely": "unadjusted corporate action"}]
    t = tradeability(
        corporate_actions=corp, spliced_dates=[],
        admissibility={"admissible": True, "detail": "ok"},
        null_summary={"sharpe": {"percentile": 99.0, "p_one_sided": 0.001}},
        baseline_verdict={"beats": True, "verdict": "ok"},
    )
    assert t["status"] == NOT_VALIDATED
    assert "DATA_CONTAMINATED" in t["failed_gates"]
    # once spliced, the same inputs pass
    t2 = tradeability(
        corporate_actions=corp, spliced_dates=["2025-10-14"],
        admissibility={"admissible": True, "detail": "ok"},
        null_summary={"sharpe": {"percentile": 99.0, "p_one_sided": 0.001}},
        baseline_verdict={"beats": True, "verdict": "ok"},
    )
    assert t2["status"] == VALIDATED


def test_weak_null_is_not_validated_but_never_called_invalid():
    t = tradeability(
        corporate_actions=[], spliced_dates=[],
        admissibility={"admissible": True, "detail": "ok"},
        null_summary={"sharpe": {"percentile": 62.3, "p_one_sided": 0.377}},
        baseline_verdict={"beats": True, "verdict": "ok"},
    )
    assert t["status"] == NOT_VALIDATED
    assert t["research_status"] == "RESEARCH_ONLY"
    assert "FAILS_NULL" in t["failed_gates"]
    assert not any("invalid" in r.lower() for r in t["reasons"])


# ------------------------------------------------------- 8. transaction costs
def test_zero_cost_is_a_no_op():
    r = np.array([0.01, -0.02, 0.03])
    pos = np.array([1.0, 0.0, 1.0])
    assert np.array_equal(apply_costs(r, pos, 0.0), r)


def test_costs_charge_each_unit_of_position_change():
    r = np.zeros(3)
    pos = np.array([1.0, 1.0, 0.0])          # entry (1.0) then exit (1.0) = 2.0 turnover
    net = apply_costs(r, pos, 10.0)
    assert net[0] == pytest.approx(-10.0 / 10_000)   # 0 -> 1
    assert net[1] == pytest.approx(0.0)              # held
    assert net[2] == pytest.approx(-10.0 / 10_000)   # 1 -> 0
    assert turnover(pos)["total"] == pytest.approx(2.0)


def test_turnover_annualisation():
    pos = np.concatenate([np.ones(126), np.zeros(126)])
    t = turnover(pos)
    assert t["total"] == pytest.approx(2.0)
    assert t["annualised"] == pytest.approx(2.0 / 252 * 252)


def test_costs_reduce_sharpe_monotonically(tcs):
    _, close, labels = tcs
    gross = walk_forward(close, labels, matrix_kind="stride", min_train=MIN_TRAIN, cost_bps=0.0)
    net = walk_forward(close, labels, matrix_kind="stride", min_train=MIN_TRAIN, cost_bps=10.0)
    assert gross["metrics"]["sharpe"] == pytest.approx(net["metrics"]["sharpe"], rel=RTOL)
    assert net["net_metrics"]["sharpe"] < gross["metrics"]["sharpe"]
    assert net["turnover"]["annualised"] > 0


# ------------------------------------------------------ 9. label-only baseline
def test_label_only_baseline_equals_the_bear_label_formulation(tcs):
    _, close, labels = tcs
    from_trailing = trailing_return_positions(close, 20, 0.05).reindex(labels.index)
    from_label = pd.Series(np.where(labels.to_numpy() == BEAR, 0.0, 1.0), index=labels.index)
    pd.testing.assert_series_equal(from_trailing, from_label, check_names=False)


def test_label_only_baseline_reproduces_validated_tcs_sharpe(tcs):
    _, close, labels = tcs
    res = run_label_only(close, labels, min_train=MIN_TRAIN, cost_bps=0.0)
    assert res["metrics"]["sharpe"] == pytest.approx(0.5302, abs=5e-4)
    assert res["metrics"]["cagr"] == pytest.approx(0.0941, abs=5e-4)
    assert res["metrics"]["max_drawdown"] == pytest.approx(-0.3818, abs=5e-4)


def test_label_only_baseline_reproduces_validated_tmpv_sharpe(tmpv_spliced):
    _, close, labels, _ = tmpv_spliced
    res = run_label_only(close, labels, min_train=MIN_TRAIN, cost_bps=0.0)
    assert res["metrics"]["sharpe"] == pytest.approx(0.9039, abs=5e-4)


def test_markov_must_beat_the_baseline_to_claim_value():
    assert markov_adds_value({"sharpe": 0.60}, {"sharpe": 0.53})["beats"] is True
    tie = markov_adds_value({"sharpe": 0.5302}, {"sharpe": 0.5302})
    assert tie["beats"] is False
    assert "not Markov alpha" in tie["verdict"]
    worse = markov_adds_value({"sharpe": 0.21}, {"sharpe": 0.53})
    assert worse["beats"] is False
    assert "baseline is better" in worse["verdict"]


# --------------------------------------------------- 10. standalone deprecation
def test_standalone_emits_deprecation_warning(tcs):
    _, close, labels = tcs
    with pytest.warns(DeprecationWarning, match="DEPRECATED"):
        walk_forward(close, labels, mode="standalone", matrix_kind="stride",
                     min_train=MIN_TRAIN)


def test_filter_mode_does_not_warn(tcs):
    _, close, labels = tcs
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        walk_forward(close, labels, mode="filter", matrix_kind="stride", min_train=MIN_TRAIN)


def test_standalone_still_reproduces_its_verified_numbers(tcs):
    """Deprecated, not removed: the old result must remain reproducible."""
    _, close, labels = tcs
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        r = walk_forward(close, labels, mode="standalone", matrix_kind="stride",
                         min_train=MIN_TRAIN)
    assert r["metrics"]["sharpe"] == pytest.approx(0.024, abs=5e-4)


# --------------------------------------------- 11. walk-forward reproducibility
def _naive_signals(lab, matrix_kind, stride, min_train):
    """From-scratch reference: rebuild the counts at every bar, as before."""
    n = len(lab)
    out = np.full(n, np.nan)
    for t in range(min_train, n - 1):
        hist = lab[: t + 1]
        c = (counts_stride(hist, stride=stride, mode="phase") if matrix_kind == "stride"
             else counts_overlapping(hist))
        P, _ = counts_to_matrix(c)
        out[t] = P[int(lab[t]), BULL] - P[int(lab[t]), BEAR]
    return out


@pytest.mark.parametrize("matrix_kind", ["stride", "overlapping"])
def test_incremental_signals_match_from_scratch_rebuild(matrix_kind):
    lab = np.random.default_rng(11).integers(0, 3, 1200)
    fast = walk_forward_signals(lab, matrix_kind=matrix_kind, stride=20, min_train=800)
    slow = _naive_signals(lab, matrix_kind, 20, 800)
    np.testing.assert_allclose(fast[800:-1], slow[800:-1], rtol=RTOL, atol=0.0)


def test_incremental_signals_match_on_real_data(tcs):
    _, _, labels = tcs
    lab = labels.to_numpy(int)
    fast = walk_forward_signals(lab, matrix_kind="stride", stride=20, min_train=MIN_TRAIN)
    slow = _naive_signals(lab, "stride", 20, MIN_TRAIN)
    np.testing.assert_allclose(fast[MIN_TRAIN:-1], slow[MIN_TRAIN:-1], rtol=RTOL, atol=0.0)


def test_walk_forward_reproduces_validated_tcs_results(tcs):
    _, close, labels = tcs
    fixed = walk_forward(close, labels, matrix_kind="stride", min_train=MIN_TRAIN)
    legacy = walk_forward(close, labels, matrix_kind="overlapping", min_train=MIN_TRAIN)
    assert fixed["metrics"]["sharpe"] == pytest.approx(0.211, abs=5e-4)
    assert fixed["metrics"]["cagr"] == pytest.approx(0.0224, abs=5e-4)
    assert fixed["metrics"]["max_drawdown"] == pytest.approx(-0.4900, abs=5e-4)
    assert fixed["metrics"]["exposure"] == pytest.approx(0.736, abs=1e-3)
    assert fixed["metrics"]["n_bars"] == 1694
    assert legacy["metrics"]["sharpe"] == pytest.approx(0.376, abs=5e-4)
    bh = fixed["buy_hold_metrics"]
    assert bh["sharpe"] == pytest.approx(0.329, abs=5e-4)
    assert bh["cagr"] == pytest.approx(0.0521, abs=5e-4)


def test_walk_forward_reproduces_validated_tmpv_results(tmpv_spliced):
    _, close, labels, _ = tmpv_spliced
    fixed = walk_forward(close, labels, matrix_kind="stride", min_train=MIN_TRAIN)
    assert fixed["metrics"]["sharpe"] == pytest.approx(-0.799, abs=5e-4)
    assert fixed["metrics"]["cagr"] == pytest.approx(-0.1897, abs=5e-4)
    assert fixed["buy_hold_metrics"]["sharpe"] == pytest.approx(0.755, abs=5e-4)
    assert fixed["buy_hold_metrics"]["cagr"] == pytest.approx(0.2549, abs=5e-4)


def test_walk_forward_has_no_lookahead(tcs):
    """Truncating the series must not change any signal on the retained bars."""
    _, close, labels = tcs
    lab = labels.to_numpy(int)
    full = walk_forward_signals(lab, matrix_kind="stride", stride=20, min_train=MIN_TRAIN)
    cut = walk_forward_signals(lab[:1500], matrix_kind="stride", stride=20, min_train=MIN_TRAIN)
    np.testing.assert_allclose(full[MIN_TRAIN:1499], cut[MIN_TRAIN:1499], rtol=RTOL)


def test_metrics_coherence_guard_holds(tcs):
    _, close, labels = tcs
    r = walk_forward(close, labels, matrix_kind="stride", min_train=MIN_TRAIN)
    assert r["metrics"]["coherent"] is True
    assert r["buy_hold_metrics"]["coherent"] is True
