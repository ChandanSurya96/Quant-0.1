"""Markov 2.0 - Hedge Fund Method (corrected).

Same core as 1.0 (states -> transition matrix -> stickiness -> signal) with
three documented flaws fixed:

  FIX 1  stride sampling      - transitions counted between NON-overlapping
                                windows, so the diagonal is not inflated by
                                windows that share 19 of 20 days.
  FIX 2  label verification   - state->name mapping is programmatically checked
                                against known historical periods and a
                                monotone-return invariant before anything is
                                rendered. Arbitrary-index labelers (KMeans, HMM)
                                are auto-remapped rather than displayed wrong.
  FIX 3  explicit modes       - FILTER (regime gates your strategy) or
                                STANDALONE (trade the differential directly).
"""

__version__ = "2.0.0"
