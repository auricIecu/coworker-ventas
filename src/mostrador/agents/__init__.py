"""Three-agent HQ: Profiler, StockObserver and Auditor run in parallel.

Profiler    — builds a cumulative purchase/interest profile per customer.
StockObserver — aggregates multi-source stock view, detects seasonality patterns.
Auditor     — crosses both profiles, generates actionable insights, waits for
              manager approval, then executes (simulated alerts / campaigns).

All data is synthetic. No real customer records, no live connections.
"""
