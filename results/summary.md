
### E0  False alarms per 30 days on clean test tubes (all hidden effects, unseen materials; budget was 1.0 on tune)

| name                               |   fa30 |   fa_cusum |   fa_frozen |   fa_verify |
|:-----------------------------------|-------:|-----------:|------------:|------------:|
| A  Night-only level model          |   0.46 |       0.46 |        0    |        0    |
| B  Static physics, calibrated once |   0.19 |       0.19 |        0    |        0    |
| C  Adaptive, no guardrails         |   2.69 |       2.69 |        0    |        0    |
| D  Adaptive, all guardrails        |   1.17 |       0.94 |        0.01 |        0.22 |
| D  cold start (no settings model)  |   1.27 |       0.76 |        0.13 |        0.38 |
| D  datasheet-only start            |   1.67 |       1.21 |        0.08 |        0.39 |
| D- fast learning                   |   1.78 |       1.49 |        0.01 |        0.28 |
| D- no bounds                       |   1.12 |       0.83 |        0.02 |        0.26 |
| D- no frozen copy                  |   1.51 |       1.28 |        0    |        0.23 |
| D- no hold test                    |   1.12 |       1.12 |        0.01 |        0    |
| D- no pause                        |   1.48 |       1.27 |        0.02 |        0.19 |


### E1  Alarms per run in the 7 days after a change (week_after) and false alarms per 30 days elsewhere (steady_per30)

| name                               |   ('week_after', 'outdoor_move') |   ('week_after', 'seal_swap') |   ('week_after', 'vent') |   ('week_after', 'weather_front') |   ('steady_per30', 'outdoor_move') |   ('steady_per30', 'seal_swap') |   ('steady_per30', 'vent') |   ('steady_per30', 'weather_front') |
|:-----------------------------------|---------------------------------:|------------------------------:|-------------------------:|----------------------------------:|-----------------------------------:|--------------------------------:|---------------------------:|------------------------------------:|
| A  Night-only level model          |                             0    |                          0    |                     7.56 |                              0.08 |                               0.7  |                            0.45 |                       4.02 |                                0.36 |
| B  Static physics, calibrated once |                             0    |                          0    |                     7.12 |                              0    |                               0.08 |                            0    |                       1.87 |                                0    |
| C  Adaptive, no guardrails         |                             2.48 |                          1.28 |                     0.56 |                              0.64 |                               3.29 |                            3.71 |                       2.2  |                                3.01 |
| D  Adaptive, all guardrails        |                             0.64 |                          0.2  |                     1.72 |                              0.2  |                               2.15 |                            1.37 |                       0.95 |                                0.92 |
| D  cold start (no settings model)  |                             0.32 |                          0.12 |                     1.32 |                              0.08 |                               1.56 |                            1.31 |                       1.48 |                                0.67 |
| D  datasheet-only start            |                             0.64 |                          0.2  |                     0.4  |                              0.32 |                               2.4  |                            2.34 |                       1.28 |                                1.62 |
| D- fast learning                   |                             1.04 |                          0.56 |                     1.88 |                              0.36 |                               2.85 |                            2.9  |                       1.84 |                                1.98 |
| D- no bounds                       |                             0.44 |                          0.12 |                     1.76 |                              0.24 |                               1.93 |                            1.59 |                       1    |                                1.06 |
| D- no frozen copy                  |                             0.68 |                          0.32 |                     0.72 |                              0.4  |                               2.48 |                            1.79 |                       0.87 |                                1.45 |
| D- no hold test                    |                             0.6  |                          0.2  |                     1.6  |                              0.28 |                               2.15 |                            1.34 |                       0.98 |                                1.28 |
| D- no pause                        |                             1.6  |                          0.6  |                     1.92 |                              0.4  |                               1.79 |                            2.29 |                       1.48 |                                1.45 |


### E1  Residual size after a change (RMS of standardized residual; about 1.0 means well-behaved)

| name                               |   ('z_d0_3', 'outdoor_move') |   ('z_d0_3', 'seal_swap') |   ('z_d0_3', 'vent') |   ('z_d0_3', 'weather_front') |   ('z_d3_7', 'outdoor_move') |   ('z_d3_7', 'seal_swap') |   ('z_d3_7', 'vent') |   ('z_d3_7', 'weather_front') |
|:-----------------------------------|-----------------------------:|--------------------------:|---------------------:|------------------------------:|-----------------------------:|--------------------------:|---------------------:|------------------------------:|
| A  Night-only level model          |                       nan    |                    nan    |                21.77 |                          1.41 |                       nan    |                    nan    |                 8.33 |                          1.48 |
| B  Static physics, calibrated once |                       nan    |                    nan    |                18    |                          1.41 |                       nan    |                    nan    |                 8.22 |                          1.26 |
| C  Adaptive, no guardrails         |                         2.82 |                      2.25 |                 1.24 |                          0.95 |                         1.85 |                      1.3  |                 0.69 |                          0.88 |
| D  Adaptive, all guardrails        |                         2.94 |                      2.27 |                 1.85 |                          1.11 |                         2.07 |                      1.5  |                 0.86 |                          1.05 |
| D  cold start (no settings model)  |                         3.15 |                      2.5  |                 1.6  |                          0.91 |                         2.02 |                      1.51 |                 0.94 |                          0.89 |
| D  datasheet-only start            |                         3.11 |                      2.46 |                 1.26 |                          1.1  |                         2.05 |                      1.5  |                 0.84 |                          1.05 |
| D- fast learning                   |                         2.84 |                      2.14 |                 1.31 |                          1.03 |                         1.98 |                      1.43 |                 0.77 |                          1.01 |
| D- no bounds                       |                         2.91 |                      2.37 |                 1.79 |                          1.11 |                         2.01 |                      1.41 |                 0.82 |                          1.03 |
| D- no frozen copy                  |                         2.94 |                      2.27 |                 1.85 |                          1.14 |                         2.07 |                      1.5  |                 0.86 |                          1.09 |
| D- no hold test                    |                         2.94 |                      2.27 |                 1.86 |                          1.12 |                         2.07 |                      1.5  |                 0.86 |                          1.08 |
| D- no pause                        |                         2.94 |                      2.27 |                 1.77 |                          0.98 |                         1.97 |                      1.46 |                 0.82 |                          0.92 |


### E2  Share of leaks detected (leak size = extra rise in Pa/h)

| name                               |   ('intermittent', 0.05) |   ('intermittent', 0.1) |   ('intermittent', 0.25) |   ('ramp', 0.05) |   ('ramp', 0.1) |   ('ramp', 0.25) |   ('sudden', 0.05) |   ('sudden', 0.1) |   ('sudden', 0.25) |
|:-----------------------------------|-------------------------:|------------------------:|-------------------------:|-----------------:|----------------:|-----------------:|-------------------:|------------------:|-------------------:|
| A  Night-only level model          |                     0.43 |                    0.6  |                     0.87 |             0.4  |            0.73 |             0.9  |               0.77 |              0.73 |               0.9  |
| B  Static physics, calibrated once |                     0.27 |                    0.6  |                     0.83 |             0.5  |            0.6  |             0.97 |               0.63 |              0.7  |               0.97 |
| C  Adaptive, no guardrails         |                     0.9  |                    1    |                     1    |             0.87 |            0.93 |             1    |               0.8  |              0.97 |               1    |
| D  Adaptive, all guardrails        |                     1    |                    0.97 |                     1    |             0.93 |            1    |             1    |               1    |              1    |               1    |
| D  cold start (no settings model)  |                     0.67 |                    0.87 |                     0.97 |             0.87 |            0.93 |             1    |               0.83 |              0.9  |               1    |
| D  datasheet-only start            |                     0.97 |                    0.97 |                     1    |             0.93 |            1    |             1    |               0.93 |              1    |               1    |
| D- fast learning                   |                     0.97 |                    1    |                     1    |             1    |            0.97 |             1    |               0.93 |              1    |               1    |
| D- no bounds                       |                     0.97 |                    0.97 |                     1    |             0.93 |            0.97 |             1    |               0.97 |              1    |               1    |
| D- no frozen copy                  |                     1    |                    1    |                     1    |             1    |            1    |             1    |               1    |              1    |               1    |
| D- no hold test                    |                     0.97 |                    0.97 |                     1    |             0.93 |            1    |             1    |               1    |              1    |               1    |
| D- no pause                        |                     1    |                    1    |                     1    |             0.9  |            1    |             1    |               0.97 |              1    |               1    |


### E2  Median detection delay (hours)

| name                               |   ('intermittent', 0.05) |   ('intermittent', 0.1) |   ('intermittent', 0.25) |   ('ramp', 0.05) |   ('ramp', 0.1) |   ('ramp', 0.25) |   ('sudden', 0.05) |   ('sudden', 0.1) |   ('sudden', 0.25) |
|:-----------------------------------|-------------------------:|------------------------:|-------------------------:|-----------------:|----------------:|-----------------:|-------------------:|------------------:|-------------------:|
| A  Night-only level model          |                      130 |                      81 |                       20 |              112 |              73 |               39 |                 97 |                91 |                 43 |
| B  Static physics, calibrated once |                      410 |                     223 |                       88 |              204 |             208 |              141 |                225 |                81 |                 44 |
| C  Adaptive, no guardrails         |                       31 |                      10 |                        3 |               88 |              25 |               15 |                 19 |                 6 |                  4 |
| D  Adaptive, all guardrails        |                       54 |                      30 |                        5 |               56 |              34 |               20 |                 38 |                14 |                  6 |
| D  cold start (no settings model)  |                       51 |                      49 |                        8 |              106 |              33 |               22 |                 40 |                15 |                  9 |
| D  datasheet-only start            |                       51 |                      22 |                        6 |               47 |              32 |               21 |                 26 |                13 |                  6 |
| D- fast learning                   |                       36 |                      22 |                        4 |               63 |              28 |               20 |                 40 |                14 |                  6 |
| D- no bounds                       |                       53 |                      23 |                        6 |               56 |              34 |               18 |                 30 |                12 |                  6 |
| D- no frozen copy                  |                       54 |                      23 |                        5 |               54 |              32 |               19 |                 33 |                11 |                  5 |
| D- no hold test                    |                       63 |                      23 |                        5 |               56 |              32 |               20 |                 36 |                13 |                  7 |
| D- no pause                        |                       39 |                      10 |                        4 |               47 |              26 |               14 |                 23 |                 8 |                  5 |


### E3  Creeping leaks (grow over 21 days; 120-day runs). absorbed = share of the leak the model had already learned as normal when it alarmed

| name                               |   ('detected', 0.05) |   ('detected', 0.1) |   ('detected', 0.25) |   ('delay_days', 0.05) |   ('delay_days', 0.1) |   ('delay_days', 0.25) |   ('absorbed', 0.05) |   ('absorbed', 0.1) |   ('absorbed', 0.25) |   ('fa_before', 0.05) |   ('fa_before', 0.1) |   ('fa_before', 0.25) |
|:-----------------------------------|---------------------:|--------------------:|---------------------:|-----------------------:|----------------------:|-----------------------:|---------------------:|--------------------:|---------------------:|----------------------:|---------------------:|----------------------:|
| A  Night-only level model          |                 0.53 |                0.77 |                 0.97 |                  26.69 |                 10.23 |                   9.15 |               nan    |              nan    |               nan    |                   0.4 |                  0.6 |                   1   |
| B  Static physics, calibrated once |                 0.63 |                0.8  |                 0.97 |                  20.73 |                 22.59 |                  15.87 |               nan    |              nan    |               nan    |                   0   |                  0   |                   0.1 |
| C  Adaptive, no guardrails         |                 0.97 |                0.97 |                 0.97 |                   7.78 |                  2.56 |                   3.81 |                 0.57 |                0.17 |                 0.38 |                   3.5 |                  5.3 |                   5.4 |
| D  Adaptive, all guardrails        |                 0.97 |                1    |                 1    |                  14.53 |                  7.43 |                   5.48 |                 0.12 |                0.06 |                 0.05 |                   0.6 |                  1.4 |                   0.6 |
| D  cold start (no settings model)  |                 0.83 |                0.97 |                 1    |                  18.7  |                  8.62 |                   6.18 |                 0.01 |                0.13 |                 0.03 |                   0.5 |                  0.8 |                   0.9 |
| D  datasheet-only start            |                 1    |                1    |                 1    |                   9.73 |                  6.82 |                   6.47 |                 0.06 |                0.04 |                 0.02 |                   1.2 |                  0.7 |                   0.3 |
| D- fast learning                   |                 1    |                1    |                 1    |                  13.68 |                  6.43 |                   6.19 |                 0.05 |                0.28 |                 0.13 |                   1.5 |                  2.9 |                   1.6 |
| D- no bounds                       |                 0.97 |                1    |                 1    |                  12.62 |                  7.9  |                   4.89 |                 0.08 |                0.09 |                 0.03 |                   1.1 |                  0.9 |                   0.9 |
| D- no frozen copy                  |                 1    |                1    |                 1    |                  12.2  |                  6.84 |                   4.94 |                 0.1  |                0.09 |                 0.04 |                   0.8 |                  1.3 |                   0.8 |
| D- no hold test                    |                 1    |                1    |                 1    |                  14.32 |                  6.84 |                   5.48 |                 0.13 |                0.08 |                 0.04 |                   0.5 |                  1   |                   0.3 |
| D- no pause                        |                 1    |                0.97 |                 1    |                  13.9  |                  4.42 |                   4.91 |                 0.22 |                0.18 |                 0.22 |                   1.5 |                  2.6 |                   2.4 |


### E4  False alarms per 30 days, one hidden effect switched on at a time

| cond   |   A Night-only |   B Static physics |   C Adaptive, no guardrails |   D Adaptive + guardrails |
|:-------|---------------:|-------------------:|----------------------------:|--------------------------:|
| none   |           0.56 |               0    |                        1.16 |                      0.2  |
| gauge  |           0.52 |               0    |                        1.4  |                      0.4  |
| seal   |           0.82 |               0.5  |                        1.34 |                      0.88 |
| second |           0.3  |               0    |                        0.98 |                      0.26 |
| solar  |           0.42 |               0    |                        2.52 |                      0.48 |
| vent   |           0.56 |               0    |                        1.1  |                      0.16 |
| wind   |           0.54 |               0.02 |                        2.36 |                      0.96 |
| all    |           1.2  |               0.64 |                        2.9  |                      1.92 |


### E4  Share of 0.10 Pa/h ramp leaks detected, one hidden effect on at a time

| cond   |   A Night-only |   B Static physics |   C Adaptive, no guardrails |   D Adaptive + guardrails |
|:-------|---------------:|-------------------:|----------------------------:|--------------------------:|
| none   |       0.7      |           0.933333 |                    0.833333 |                  1        |
| gauge  |       0.566667 |           0.966667 |                    0.966667 |                  1        |
| seal   |       0.633333 |           1        |                    0.9      |                  1        |
| second |       0.4      |           0.866667 |                    0.866667 |                  0.9      |
| solar  |       0.566667 |           0.533333 |                    0.9      |                  0.966667 |
| vent   |       0.566667 |           0.966667 |                    0.966667 |                  1        |
| wind   |       0.8      |           0.966667 |                    0.933333 |                  1        |
| all    |       0.833333 |           0.7      |                    0.966667 |                  1        |


### E6  Simulator B (different functional forms; detector and thresholds trained on simulator A)

| det                       |   FA per 30 d (clean) |   ramp_0.05 |   ramp_0.10 |   ramp_0.25 |
|:--------------------------|----------------------:|------------:|------------:|------------:|
| A Night-only              |                  0.76 |    0.5      |    0.733333 |    0.966667 |
| B Static physics          |                  0.25 |    0.333333 |    0.633333 |    1        |
| C Adaptive, no guardrails |                  3.07 |    0.933333 |    0.966667 |    0.966667 |
| D Adaptive + guardrails   |                  1.67 |    0.966667 |    1        |    1        |


### E7  Warm-up: mean absolute one-step error (Pa/h) by days since commissioning

| name                              |   d0_1 |   d1_3 |   d3_10 |
|:----------------------------------|-------:|-------:|--------:|
| D  Adaptive, all guardrails       |  0.114 |  0.086 |   0.085 |
| D  cold start (no settings model) |  0.131 |  0.101 |   0.149 |
| D  datasheet-only start           |  0.112 |  0.099 |   0.098 |
