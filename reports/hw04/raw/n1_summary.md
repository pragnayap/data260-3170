| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 10 | naive | 12 | 27.9 | 87.33 | 142.96 |
| 10 | fixed | 3 | 13.52 | 28.57 | 413.83 |
| 50 | naive | 44 | 42.78 | 57.59 | 61.16 |
| 50 | fixed | 3 | 16.97 | 19.46 | 19.96 |
| 200 | naive | 126 | 110.99 | 119.64 | 143.73 |
| 200 | fixed | 3 | 38.95 | 40.71 | 62.26 |

### Speed-up (fixed vs. naive), by page size

- page_size=10: naive p50=27.9ms, fixed p50=13.52ms -> **2.06x** faster
- page_size=50: naive p50=42.78ms, fixed p50=16.97ms -> **2.52x** faster
- page_size=200: naive p50=110.99ms, fixed p50=38.95ms -> **2.85x** faster
