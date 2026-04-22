# TORRENT Validation

Open-source validation results for the [TORRENT](https://torrentrisk.com) post-fire debris flow hazard platform.

**Last updated:** 2026-04-20

## Debris Flow Initiation (Staley M1 AUC)

Basin-level AUC for the USGS Staley et al. (2016) M1 logistic regression model,
validated against USGS field observations from Graber (2023/2024), Gorr (2024),
and Selander (2024) inventories.

| State | AUC | Observations | Status | Notes |
|-------|-----|-------------|--------|-------|
| CA | 0.532 | 15,239 | modest | Pooled Graber 2023/2024. Per-fire: Thomas 0.584, Butte 0.574, Briceburg 0.500. |
| AZ | 0.649 | 2,400 | pass_moderate | 5 fires matched (Pinal, Museum, Woodbury, Flag, Pipeline). |
| CO | 0.682 | 25 | pass_moderate | Cameron Peak 0.843, Spring Creek 0.375 (8 obs). |
| NM | 0.707 | 6,180 | pass_strong | Buzzard, Tadpole, McBride, Whitewater-Baldy. |
| WA | 0.500 | 586 | fail | Muckamuck 0.726 good; Cub Creek 2 inverting (0.461). PNW maritime outside M1 domain. |
| OR | 0.566 | 1,604 | below_threshold | Holiday Farm 0.71; others near random (shallow landslides != runoff). |
| UT | N/A | 5 | data_gap | 5 obs all positive; needs UGS + PFDF ground-truth negatives. |

WA and OR are labeled "screening only" in the product until AUC >= 0.60.

## Debris Flow Volume (Gartner/Santi)

Volume predictions using Gartner et al. (2014) + Santi et al. (2008) geometric
mean, validated against 151/227 matched field observations
from Gorr et al. (2024).

| Metric | Value |
|--------|-------|
| Observations matched | 151 / 227 |
| Fires represented | 14 |
| RMSE ln(volume) | 1.185 |
| Storm scenario | 10-year return period, 1-hour duration (NOAA Atlas 14) |
| Match radius | 5.0 km |

## Methodology

TORRENT implements published USGS empirical models for post-fire debris flow
hazard assessment:

1. **Initiation probability** -- Staley et al. (2016) M1 logistic regression
   with 3 interaction terms (slope x burn severity x soil KF x rainfall I15).
   Platt-calibrated. Basin AUC computed at the sub-watershed level.

2. **Volume estimation** -- Geometric mean of Gartner et al. (2014) and Santi
   et al. (2008) log-linear models. Volume clamped to 20,000 m3/km2 max per
   Wall et al. (2024) finding that unclamped Gartner overestimates 10-50x.

3. **Runout simulation** -- Voellmy rheology (mu=0.15-0.20, xi=500) on
   10-30m DEM grids (USGS 3DEP).

All source equations, parameters, and deviations from published methods are
documented in the product methodology page and in this repository.

## Data Files

- `metrics/state_auc.json` -- Per-state AUC metrics
- `metrics/volume_rmse.json` -- Volume validation summary
- `metrics/per_fire_auc.csv` -- Per-fire AUC breakdown

## Key References

- Staley, D.M. et al. (2016). Objective definition of rainfall intensity-duration
  thresholds for the initiation of post-fire debris flows in southern California.
  *Landslides*, 14(2), 547-563.
- Gartner, J.E. et al. (2014). Empirical models for predicting volumes of sediment
  deposited by debris flows and sediment-laden floods in the transverse ranges of
  southern California. *Engineering Geology*, 176, 45-56.
- Santi, P.M. et al. (2008). Sources of debris flow material in burned areas.
  *Geomorphology*, 96, 310-321.
- Gorr, A.N., McGuire, L.A., & Youberg, A.M. (2024). Empirical Models for Postfire
  Debris-Flow Volume in the Southwest United States. *JGR Earth Surface*.
  doi:10.1029/2024JF007825
- Graber, A.P. et al. (2023). Post-fire debris-flow hazard assessment of the 2020
  fire season, western United States. USGS data release.

## Citation

If you use these validation results in your research, please cite:

```
TORRENT Validation Results (2026-04-20).
https://github.com/lannparty/torrent-validation
```

## Contributing Field Observations

Have field observations from a post-fire debris flow event? Submit them via the TORRENT Research API to help improve model accuracy.

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- How to submit observations via API
- How to file calibration issues on GitHub
- What happens during weekly recalibration
- Data format requirements
- Credit and attribution policy

## Live Metrics

Current validation metrics are published at:
https://torrentrisk.com/validation

## License

MIT
