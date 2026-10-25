| Case | Setup | Best possible (measured) |
|---|---|---|
| 1 | 9033 both, any, 1 h, from 2023-09-04 (Monday start) | Sun 10 Sep 04:00 (870) |
| 2 | 9033 both, any, 4 h, from 2023-09-04 (Monday start) | Sun 10 Sep 02:00 (955) |
| 3 | 9033 R1, day, 2 h, from 2023-09-13 (one side, day shift) | Sun 17 Sep 06:00 (625) |
| 4 | 9040 both, night, 4 h, from 2023-10-16 (night shift) | Sun 22 Oct 02:00 (312) |
| 5 | 9040 both, day, 4 h, from 2023-11-05 (Sunday start) | Sun 05 Nov 06:00 (792) |
| 6 | 9521 R2, any, 2 h, from 2023-11-10 (Friday start) | Sun 12 Nov 03:00 (174) |
| 7 | 9507 both, any, 4 h, from 2023-10-02 (holiday week (Tue 3 Oct)) | Sun 08 Oct 02:00 (540) |
| 8 | 9093 both, day, 4 h, from 2023-10-30 (holiday week (Wed 1 Nov)) | Sun 05 Nov 06:00 (970) |
| 9 | 9159 both, night, 2 h, from 2023-12-18 (Christmas week (25/26 Dec)) | Sun 24 Dec 03:00 (446) |
| 10 | 9050 both, any, 1 h, from 2023-07-10 (station with 'u' flags) | Tue 11 Jul 03:00 (1085) |
| 11 | 9085 R1, day, 1 h, from 2023-08-10 (holiday Tue 15 Aug, 41% estimated) | Tue 15 Aug 06:00 (550) |
| 12 | 9011 both, night, 4 h, from 2023-09-22 (Friday start, night shift) | Sun 24 Sep 02:00 (514) |

| case | tool | shown | data_slot | expected | reduction | measured | measured_reduction | in_horizon | in_shift | rank |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | aitraffic | Sun 10 Sep 03:00 | Sun 10 Sep 03:00 | 434 | 89% | 889 | 88% | yes | yes | 2/168 |
| 1 | ours v1 | Sun 10 Sep 05:00 | Sun 10 Sep 04:00 | 703 | 91% | 870 | 89% | yes | yes | 1/168 |
| 1 | ours v1 (data before start only) | Sun 10 Sep 05:00 | Sun 10 Sep 04:00 | 734 | 91% | 870 | 89% | yes | yes | 1/168 |
| 1 | ours v2 | Sun 10 Sep 04:00 | Sun 10 Sep 04:00 | 706 | 91% | 870 | 89% | yes | yes | 1/168 |
| 1 | ours v2 (data before start only) | Sun 10 Sep 04:00 | Sun 10 Sep 04:00 | 739 | 91% | 870 | 89% | yes | yes | 1/168 |
| 2 | aitraffic | Sun 10 Sep 01:00 | Sun 10 Sep 01:00 | 482 | 88% | 996 | 87% | yes | yes | 2/168 |
| 2 | ours v1 | Sun 10 Sep 05:00 | Sun 10 Sep 04:00 | 703 | 91% | 1362 | 82% | yes | yes | 18/168 |
| 2 | ours v1 (data before start only) | Sun 10 Sep 05:00 | Sun 10 Sep 04:00 | 734 | 91% | 1362 | 82% | yes | yes | 18/168 |
| 2 | ours v2 | Sun 10 Sep 02:00 | Sun 10 Sep 02:00 | 763 | 90% | 955 | 87% | yes | yes | 1/168 |
| 2 | ours v2 (data before start only) | Sun 10 Sep 02:00 | Sun 10 Sep 02:00 | 797 | 90% | 955 | 87% | yes | yes | 1/168 |
| 3 | aitraffic | Sun 17 Sep 06:00 | Sun 17 Sep 06:00 | 626 | 83% | 625 | 85% | yes | yes | 1/77 |
| 3 | ours v1 | Sun 17 Sep 06:00 | Sun 17 Sep 05:00 | 380 | 89% | 450 | 89% | yes | no | - |
| 3 | ours v1 (data before start only) | Sun 17 Sep 06:00 | Sun 17 Sep 05:00 | 411 | 89% | 450 | 89% | yes | no | - |
| 3 | ours v2 | Sun 17 Sep 06:00 | Sun 17 Sep 06:00 | 593 | 83% | 625 | 85% | yes | yes | 1/77 |
| 3 | ours v2 (data before start only) | Sun 17 Sep 06:00 | Sun 17 Sep 06:00 | 651 | 82% | 625 | 85% | yes | yes | 1/77 |
| 4 | aitraffic | Sun 22 Oct 02:00 | Sun 22 Oct 02:00 | 198 | 57% | 312 | 64% | yes | yes | 1/35 |
| 4 | ours v1 | Sun 22 Oct 05:00 | Sun 22 Oct 04:00 | 350 | 75% | 406 | 53% | yes | no | - |
| 4 | ours v1 (data before start only) | Sun 22 Oct 05:00 | Sun 22 Oct 04:00 | 378 | 73% | 406 | 53% | yes | no | - |
| 4 | ours v2 | Sun 22 Oct 02:00 | Sun 22 Oct 02:00 | 379 | 61% | 312 | 64% | yes | yes | 1/35 |
| 4 | ours v2 (data before start only) | Sun 22 Oct 02:00 | Sun 22 Oct 02:00 | 408 | 59% | 312 | 64% | yes | yes | 1/35 |
| 5 | aitraffic | Sun 05 Nov 06:00 | Sun 05 Nov 06:00 | 520 | 70% | 792 | 76% | yes | yes | 1/63 |
| 5 | ours v1 | Sun 12 Nov 06:00 | Sun 12 Nov 05:00 | 400 | 90% | 481 | 86% | no | no | - |
| 5 | ours v1 (data before start only) | Sun 12 Nov 06:00 | Sun 12 Nov 05:00 | 429 | 89% | 481 | 86% | no | no | - |
| 5 | ours v2 | Sun 05 Nov 06:00 | Sun 05 Nov 06:00 | 1000 | 73% | 792 | 76% | yes | yes | 1/63 |
| 5 | ours v2 (data before start only) | Sun 05 Nov 06:00 | Sun 05 Nov 06:00 | 1076 | 72% | 792 | 76% | yes | yes | 1/63 |
| 6 | aitraffic | Sun 12 Nov 04:00 | Sun 12 Nov 04:00 | 240 | 94% | 201 | 96% | yes | yes | 3/168 |
| 6 | ours v1 | Sun 12 Nov 05:00 | Sun 12 Nov 04:00 | 354 | 92% | 201 | 96% | yes | yes | 3/168 |
| 6 | ours v1 (data before start only) | Sun 12 Nov 05:00 | Sun 12 Nov 04:00 | 376 | 92% | 201 | 96% | yes | yes | 3/168 |
| 6 | ours v2 | Sun 12 Nov 04:00 | Sun 12 Nov 04:00 | 398 | 91% | 201 | 96% | yes | yes | 3/168 |
| 6 | ours v2 (data before start only) | Sun 12 Nov 04:00 | Sun 12 Nov 04:00 | 423 | 90% | 201 | 96% | yes | yes | 3/168 |
| 7 | aitraffic | Sun 08 Oct 01:00 | Sun 08 Oct 01:00 | 354 | 91% | 563 | 93% | yes | yes | 2/168 |
| 7 | ours v1 | Sun 08 Oct 05:00 | Sun 08 Oct 04:00 | 570 | 93% | 821 | 90% | yes | yes | 11/168 |
| 7 | ours v1 (data before start only) | Sun 08 Oct 05:00 | Sun 08 Oct 04:00 | 618 | 92% | 821 | 90% | yes | yes | 11/168 |
| 7 | ours v2 | Sun 08 Oct 02:00 | Sun 08 Oct 02:00 | 624 | 92% | 540 | 93% | yes | yes | 1/168 |
| 7 | ours v2 (data before start only) | Sun 08 Oct 02:00 | Sun 08 Oct 02:00 | 674 | 91% | 540 | 93% | yes | yes | 1/168 |
| 8 | aitraffic | Sun 05 Nov 06:00 | Sun 05 Nov 06:00 | 544 | 65% | 970 | 68% | yes | yes | 1/63 |
| 8 | ours v1 | Sun 05 Nov 06:00 | Sun 05 Nov 05:00 | 518 | 84% | 640 | 79% | yes | no | - |
| 8 | ours v1 (data before start only) | Sun 05 Nov 06:00 | Sun 05 Nov 05:00 | 563 | 83% | 640 | 79% | yes | no | - |
| 8 | ours v2 | Sun 05 Nov 06:00 | Sun 05 Nov 06:00 | 1201 | 63% | 970 | 68% | yes | yes | 1/63 |
| 8 | ours v2 (data before start only) | Sun 05 Nov 06:00 | Sun 05 Nov 06:00 | 1303 | 60% | 970 | 68% | yes | yes | 1/63 |
| 9 | aitraffic | Sun 24 Dec 03:00 | Sun 24 Dec 03:00 | 399 | 78% | 446 | 85% | yes | yes | 1/49 |
| 9 | ours v1 | Sun 24 Dec 05:00 | Sun 24 Dec 04:00 | 585 | 81% | 507 | 83% | yes | yes | 3/49 |
| 9 | ours v1 (data before start only) | Sun 24 Dec 05:00 | Sun 24 Dec 04:00 | 594 | 81% | 507 | 83% | yes | yes | 3/49 |
| 9 | ours v2 | Sun 24 Dec 03:00 | Sun 24 Dec 03:00 | 575 | 76% | 446 | 85% | yes | yes | 1/49 |
| 9 | ours v2 (data before start only) | Sun 24 Dec 03:00 | Sun 24 Dec 03:00 | 584 | 75% | 446 | 85% | yes | yes | 1/49 |
| 10 | aitraffic | Sun 16 Jul 03:00 | Sun 16 Jul 03:00 | 886 | 77% | 1113 | 87% | yes | yes | 3/168 |
| 10 | ours v1 | Sun 16 Jul 05:00 | Sun 16 Jul 04:00 | 586 | 91% | 1138 | 87% | yes | yes | 4/168 |
| 10 | ours v1 (data before start only) | Sun 16 Jul 05:00 | Sun 16 Jul 04:00 | 527 | 91% | 1138 | 87% | yes | yes | 4/168 |
| 10 | ours v2 | Sun 16 Jul 04:00 | Sun 16 Jul 04:00 | 608 | 91% | 1138 | 87% | yes | yes | 4/168 |
| 10 | ours v2 (data before start only) | Sun 16 Jul 04:00 | Sun 16 Jul 04:00 | 562 | 92% | 1138 | 87% | yes | yes | 4/168 |
| 11 | aitraffic | Sun 13 Aug 06:00 | Sun 13 Aug 06:00 | 616 | 65% | 696 | 64% | yes | yes | 7/84 |
| 11 | ours v1 | Sun 13 Aug 06:00 | Sun 13 Aug 05:00 | 237 | 78% | 564 | 71% | yes | no | - |
| 11 | ours v1 (data before start only) | Sun 13 Aug 06:00 | Sun 13 Aug 05:00 | 213 | 78% | 564 | 71% | yes | no | - |
| 11 | ours v2 | Sun 13 Aug 06:00 | Sun 13 Aug 06:00 | 284 | 74% | 696 | 64% | yes | yes | 7/84 |
| 11 | ours v2 (data before start only) | Sun 13 Aug 06:00 | Sun 13 Aug 06:00 | 258 | 74% | 696 | 64% | yes | yes | 7/84 |
| 12 | aitraffic | Sun 24 Sep 02:00 | Sun 24 Sep 02:00 | 308 | 71% | 514 | 70% | yes | yes | 1/35 |
| 12 | ours v1 | Sun 24 Sep 05:00 | Sun 24 Sep 04:00 | 555 | 82% | 854 | 51% | yes | no | - |
| 12 | ours v1 (data before start only) | Sun 24 Sep 05:00 | Sun 24 Sep 04:00 | 608 | 81% | 854 | 51% | yes | no | - |
| 12 | ours v2 | Sun 24 Sep 02:00 | Sun 24 Sep 02:00 | 596 | 68% | 514 | 70% | yes | yes | 1/35 |
| 12 | ours v2 (data before start only) | Sun 24 Sep 02:00 | Sun 24 Sep 02:00 | 653 | 66% | 514 | 70% | yes | yes | 1/35 |
