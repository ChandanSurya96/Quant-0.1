# Quant-Algorithm: Markov-Gated Macro Strategy

This repository implements a quantitative trading algorithm combining two methodologies:
1. **Systematic Global Macro** (Cross-sectional Mom/Value/Carry)
2. **Markov Regime Filter** (Time-series regime detection via HMM/Thresholding)

## Methodology
The algorithm trades a universe of 12 ETFs (Equities, Bonds, Currencies, Commodities). 
Every month, the assets are scored cross-sectionally based on:
* **Momentum:** 12-month trailing return
* **Value:** 3-year mean reversion (z-score inverted)
* **Carry:** Yield proxies

We rank the assets and select the Top 4 for a Long basket and the Bottom 4 for a Short basket.

### The Markov Gate
Before executing the portfolio, we apply a **Markov 2.0 Regime Filter** per asset.
By projecting transition matrices step-by-step with zero look-ahead bias, we forecast if an asset is entering a BULL or BEAR regime.
* If an asset is a Long candidate but its Markov forecast is strongly BEAR, the trade is rejected.
* If an asset is a Short candidate but its Markov forecast is strongly BULL, the trade is rejected.

This effectively blends market-neutral relative-value ranking with directional risk-management overlays.

## Run Instructions
Requires Python 3.9+ and `yfinance`.

```bash
# Run the core single-asset Markov strategy on SPY
python -m markov2.run --ticker SPY

# Run the Markov-Gated Macro Strategy
python -m markov2.run --macro
```