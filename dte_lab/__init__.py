"""0DTE / 1DTE options strategy backtesting.

No historical options-chain data is used anywhere in this package: every
option price is a Black-Scholes estimate driven by the underlying's own
price history (spot + a realized-volatility-based IV proxy). Treat results
as "what this strategy should have earned under BS pricing with this vol
assumption", not a replay of prices you could actually have been filled at.
See README.md for the full list of simplifications.
"""
