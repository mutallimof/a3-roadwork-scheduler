Backtest (window chosen on 'weekly', expected traffic from 'weekly', min 4 hours per slot) on held-out weeks (2023-07-10, 2023-08-07, 2023-09-04, 2023-10-02, 2023-10-30, 2023-11-27, 2023-12-18), data years [2023], run 2026-10-26. Real BASt data.

Hourly error of the expected traffic, per direction: 42,863 hours, MAE 243 vehicles/hour, MAPE 21.0%

All cases: 665 tests, chosen window in top 3: 85%, traffic above the quietest window: 6%, measured / expected for the chosen window: 10th percentile 0.55, median 0.86, 90th percentile 1.98

| Case | Tests | Outside shift or week | Median rank of chosen window | Chosen window in top 3 | Traffic above the quietest window | Windows per week |
|---|---:|---:|---:|---:|---:|---:|
| R1, day, 2 h | 133 | 0% | 1 | 99% | 0% | 77 |
| both, any, 1 h | 133 | 0% | 2 | 68% | 16% | 168 |
| both, any, 4 h | 133 | 0% | 1 | 77% | 7% | 168 |
| both, day, 4 h | 133 | 0% | 1 | 99% | 0% | 63 |
| both, night, 4 h | 133 | 0% | 1 | 80% | 6% | 35 |

Rank: position of the chosen window among all windows of that length in the shift and week, ordered by measured traffic (1 = quietest). Windows outside the shift or the week count as not in the top 3.
