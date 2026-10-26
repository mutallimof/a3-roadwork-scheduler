# Choosing the profile (backtest grid)

`scripts/backtest.py` on the real 2023 data (default years 2019 and 2023;
2019 is not available), 7 held-out weeks (July–December 2023), 19
stations, 665 recommendation tests. Only data from before each test week
is used. Run on 2026-10-26.

| Window chosen on | Expected traffic from | Min. hours per slot | Hourly error (MAPE) | Hourly error (MAE, veh/h) | Chosen window in top 3 | Traffic above quietest window | Measured / expected, 10th–90th percentile |
|---|---|---:|---:|---:|---:|---:|---|
| weekly | weekly | – | 21.0% | 243 | 85% | 6.0% | 0.56 – 1.98 |
| weekly | month | 2 | 15.9% | 207 | 85% | 6.0% | 0.75 – 1.76 |
| weekly | month | 4 | 18.7% | 229 | 85% | 6.0% | 0.69 – 1.98 |
| weekly | season | 2 | 17.6% | 205 | 85% | 6.0% | 0.64 – 1.29 |
| **weekly** | **season** | **4** | **17.6%** | **205** | **85%** | **6.0%** | **0.64 – 1.29** |
| weekly | season | 8 | 18.4% | 232 | 85% | 6.0% | 0.67 – 1.98 |
| season | season | 4 | 17.6% | 205 | 80% | 7.4% | 0.64 – 1.30 |
| season | season | 8 | 18.4% | 232 | 79% | 8.5% | 0.68 – 1.98 |

- *weekly*: all data before the week. *month*: only the same calendar
  month(s). *season*: the same month(s) plus one month on either side. A
  weekday-hour slot with fewer measured hours than the minimum falls back
  to the weekly average.
- Choosing the window on a seasonal profile made the choice worse (top 3
  85% → 80%), so the window is still chosen on the weekly profile.
- The seasonal estimate lowered the hourly error (21.0% → 17.6%) and gave
  the narrowest range for the chosen window, so the app uses it for the
  expected traffic (bold row). The monthly estimate with a 2-hour minimum
  had a lower MAPE but a much wider range for the chosen window.
- The median of measured / expected for the chosen window is 0.80: the
  estimate for the chosen window tends to be too high. The app therefore
  shows the 10th–90th percentile range, not a single number.
