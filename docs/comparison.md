# Comparison with aitraffic

This compares this app with the aitraffic project
([github.com/DanieMyl/aitraffic](https://github.com/DanieMyl/aitraffic)),
a joint project, on the same raw BASt data, and records what was taken
over. All figures below come from real BASt counts (2018, 2022, 2023) run
in October 2026 on Linux with Python 3.13. Nothing here uses generated
data.

## 1. Running aitraffic

aitraffic was copied (the original folder was not changed) and its
pipeline rebuilt from the raw files, in a separate environment with its
`requirements.txt` (lightgbm 4.7, pandas 3.1, holidays 0.107, pyarrow 26):

| Step | Result |
|---|---|
| `clean_data.py` | Ran in 5 s. 551,880 raw rows, 32 stations, 63 station-years, no gaps; 1,486 counts flagged `u` (same figures as this app's checks). |
| `forecast_lgbm.py` | Ran in 58 s. Same training size and best iteration as the model committed in aitraffic. Reported validation error: MAPE 7.3%. |
| `recommend_windows.py` | Used through its own functions (`get_recommendations`, `compute_burden`). |
| API / frontend / Docker | Not run; not needed for the comparison. |

Everything that was needed ran. The reported 7.3% is measured with the true
counts of the previous hour, day and week as inputs (one hour ahead); see
section 4 for the error when forecasting a week ahead.

## 2. Test cases

12 cases, each a 7-day search period in July–December 2023. aitraffic's
model is trained on data before 2023-07-01, so these weeks are held out
for it, and the measured counts are there to check both tools against. Its
forecast is seeded with the measured week before the period, as it would
be in use. The cases cover full closures and single sides, day
(06:00–18:00), night (22:00–06:00) and any time, 1-, 2- and 4-hour
windows, Monday, Friday and Sunday starts, weeks with public holidays
(3 Oct, 1 Nov, Christmas, 15 Aug), and station 9050 with implausible flags.

For each recommendation the measured traffic in that window was looked
up in the raw data, and the window was ranked against every window of the
same length in the same shift and week (rank 1 = it really was the
quietest).

Full tables: `docs/comparison_results_v1.md` (before), `docs/comparison_results_v2.md`
(after). Rebuild with `python scripts/compare_with_aitraffic.py --aitraffic-dir <copy>`.

## 3. Differences found and their causes

| # | Difference | Cause | Evidence | Who was right |
|---|---|---|---|---|
| 1 | This app showed every time 1 hour later (e.g. "05:00" where aitraffic shows "04:00" for the same data) | Hour convention. aitraffic reads BASt `Stunde` n as (n−1):00–n:00; this app displayed n:00. | On the spring daylight-saving day Stunde 3 is 0 at every station in 2018, 2022 and 2023: the hour 02:00–03:00 that does not exist. In autumn Stunde 3 holds about twice the normal count (02:00–03:00 happens twice). These hours carry flag `z`. The BASt data-set description (2015) defines "Stunde 01 = 0.00–1.00 Uhr" (seen in a search result; the PDF itself could not be opened from the test environment). | **aitraffic** |
| 2 | In 5 of 12 cases this app's window was outside the requested shift | Its "Day (06-18)" included Stunde 6 (05:00–06:00); for night shifts a 4-hour window was drawn from the best hour onwards, past 06:00. | Cases 3, 4, 8, 11, 12 in `comparison_results_v1.md`. | **aitraffic** |
| 3 | For 4-hour windows this app ranked 18th and 11th of 168 (cases 2, 7); aitraffic 2nd | This app scored single hours and stretched the best one to 4 hours; aitraffic scores whole windows. | Measured traffic 1,362 vs 996 (case 2), 821 vs 563 (case 7). | **aitraffic** |
| 4 | Sunday start: this app recommended the following Sunday | The earliest start day itself was never allowed. | Case 5: 12 Nov instead of 5 Nov. | **aitraffic** |
| 5 | aitraffic's expected traffic for full closures is about half the measured traffic (e.g. 434 vs 889) | It combines the two directions with the maximum, not the sum; it scores congestion per direction against capacity, so this is by design, but the number it shows is one direction's traffic. | For single-side cases its figure matches (626 vs 625 measured, case 3). | **This app** for the number shown as traffic of a full closure; neither is wrong about the ranking. |
| 6 | Expected traffic for the week ahead | aitraffic forecasts (LightGBM, recursive); this app uses the weekly average profile. | Section 4. | **aitraffic** when the week before is measured; **this app** otherwise. |
| 7 | Holiday weeks | Neither tool chose a public holiday. In case 11 the quietest window was Tuesday 15 August 06:00 (a local holiday around station 9085, not a statewide one); both chose Sunday (rank 7 of 84). | Case 11. | Neither |
| 8 | Station 9050 (implausible flags) | aitraffic drops `u` hours; this app used them. | Case 10: both picked a top-4 window; no visible effect. | aitraffic (cleaner), no practical difference here |

## 4. Accuracy of the expected traffic (held-out weeks)

Hours with at least 10 vehicles, per direction, 19 stations.

| Situation | aitraffic LightGBM | Weekly profile (this app) |
|---|---:|---:|
| Measured week right before the forecast week (7 weeks, Jul–Dec 2023) | MAPE 13.5%, MAE 167 | MAPE 22.8%, MAE 253 (2023 data before the week) |
| No data for the 1–4 months before the week (5 weeks, Aug–Nov 2023; data up to 1 July) | **MAPE 71.6%, MAE 1,149** | MAPE 20.5%, MAE 237; same-month profile from 2018/2022: 18.0% |

Without recent measured data aitraffic's recursive forecast sinks towards
zero within days (station 9033, direction 1, week of 2 Oct 2023: forecast
daily means 477 → 218 vehicles/hour, measured about 1,850). Its API plans
from 22 June 2026, two and a half years after the data ends. In that
horizon the forecast for 9033 rises from 508 to 1,094 vehicles/hour per
week as the recursion warms up (measured 2023 average about 1,960 per
direction); the best 4-hour window is still Sunday 02:00, but the best
72-hour window starts on a Friday at 07:00 in the first weeks, only
because those weeks are forecast lowest.

**Which to trust:** aitraffic's numbers only when the week before the
planned work has been measured. For planning months ahead, as this app is
used, the weekly profile is the more reliable basis.

## 5. Shortlist (decided before implementing)

| Feature | From | Fixes | Size | Risk | Done |
|---|---|---|---|---|---|
| BASt hour convention for all times | aitraffic `clean_data.parse_timestamp` | #1 | Small | Low (all times shift by 1 h) | yes |
| Shifts as clock hours, end excluded, across midnight | aitraffic `ShiftDuration` | #2 | Small | Low | yes |
| Score whole windows of N hours | aitraffic `_find_continuous_windows` | #3 | Medium | Medium (main result changes) | yes |
| Earliest start day allowed | — | #4 | Small | Low | yes |
| Leave out `u` hours | aitraffic `forecast_lgbm.load_data` | #8 | Small | Low | yes |
| Bavarian holidays: out of the averages, listed in the project period | aitraffic `is_holiday` | #7 (partly) | Small | Low; no new dependency | yes |
| Accuracy test on held-out weeks | aitraffic `evaluate`, without in-week values | section 4 | Small–medium | None | yes (`scripts/backtest.py`) |
| LightGBM forecast | aitraffic | #6 | Large | High: fails without recent data, adds lightgbm | no |
| Capacity/disruption score (lanes, p97 capacity) | aitraffic | — | Medium | Needs lane data per section | no |
| Multi-station sections, API, Docker, Vue frontend | aitraffic | — | Large | Rewrite | no |

Features of this app that aitraffic lacks: data checks shown in the app,
unit tests (29), repaired station names and the Bavaria filter for
Jawe2023, a demo sample, one-command data setup, configurable years.

## 6. Before and after

12 comparison cases (`comparison_results_v1.md` → `comparison_results_v2.md`):

| | This app v1 | This app v2 | aitraffic |
|---|---:|---:|---:|
| Window inside the shift and the search week | 6 / 12 | 12 / 12 | 12 / 12 |
| Measured quietest window chosen (rank 1) | 1 / 12 | 9 / 12 | 6 / 12 |
| Same window as aitraffic | 0 / 12 | 7 / 12 | — |

Backtest on 7 held-out weeks × 19 stations, 133 tests per case
(`docs/backtest_v1.md` → `docs/backtest_v2.md`):

| Case | v1: outside shift | v1: in top 3 | v1: traffic above quietest | v2: outside shift | v2: in top 3 | v2: traffic above quietest |
|---|---:|---:|---:|---:|---:|---:|
| both, any, 1 h | 0% | 71% | 15% | 0% | 68% | 16% |
| both, any, 4 h | 0% | 6% | 54% | 0% | 77% | 7% |
| both, day, 4 h | 100% | 0% | – | 0% | 99% | 0% |
| both, night, 4 h | 100% | 0% | – | 0% | 80% | 6% |
| one side, day, 2 h | 97% | 3% | – | 0% | 99% | 0% |

For 1-hour windows at any time v2 is slightly worse than v1 (68% vs 71% in
the top 3). The only difference there is that v2 leaves public holidays
and `u` hours out of the averages.

## 7. Remaining differences and open decisions

- **Hour convention:** implemented as BASt Stunde 1 = 00:00–01:00, based
  on the daylight-saving evidence. Please confirm against the current BASt
  "Datensatzbeschreibung – Stundendaten".
- **Expected traffic:** this app's weekly averages are about 21% off per
  hour; aitraffic's forecast is better (13.5%) only with the previous week
  measured. Not adopted.
- **Full-closure traffic:** aitraffic shows one direction (maximum), this
  app the sum of both. Both are labelled in their tools; the numbers are
  not comparable directly.
- **Local holidays:** 15 August is a holiday only in Catholic-majority
  communities and is not in the statewide list; case 11 shows its effect.
- **Case 10 (9050, 1 hour):** v2 ranks 4th (1,138 vehicles/hour), aitraffic
  3rd (1,113). Within 2%.
- **Seasonal suggestion:** `prophet_results.json` is unchanged (it would
  now be trained on 2023 only); a same-month weekly profile was more
  accurate in the gap test (18.0% vs 20.5%) and could replace it later.
