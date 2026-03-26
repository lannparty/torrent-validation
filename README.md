# TORRENT Open Validation

Open-source implementation of published post-fire debris flow models,
validation data, and reproducibility tools.

**This is the science. The product is at [torrentrisk.com](https://torrentrisk.com).**

## What's Here

```
equations/          Published model implementations (Staley M1, Gartner, Santi, Voellmy)
calibration/        Platt scaling parameters, training script, leave-fire-out CV
validation/         35,000+ observations from 10 USGS datasets
scripts/            reproduce.py, validate_traced_results.py, backtests
docs/               Validation report, peer reviews, deviation analysis
```

## Reproduce Any Result

```bash
python reproduce.py traced_result.json
```

## Validation Metrics

| Metric | Value | Target |
|---|---|---|
| AUC-ROC (full M1) | 0.849 | >= 0.85 |
| Fire-level AUC | 1.000 | — |
| Volume RMSE | 0.376 | <= 0.52 |
| Brier Score | 0.084 | <= 0.20 |

### Leave-Fire-Out Cross-Validation

Addresses spatial autocorrelation concerns. Each fire held out entirely during calibration.

| Method | Brier Score | AUC | BSS |
|---|---|---|---|
| Raw M1 (uncalibrated) | 0.159 | 0.849 | -0.626 |
| Platt 5-fold random CV | 0.084 | 0.836 | 0.144 |
| **Platt leave-fire-out CV** | **0.083** | **0.832** | **0.151** |

**Spatial leakage: NEGLIGIBLE** — Brier delta is -0.9%. Coefficients stable (CV 3.3-3.6%).

## References

- Staley et al. (2016), USGS OFR 2016-1106
- Gartner et al. (2014), Geomorphology
- Santi et al. (2008), Geomorphology
- Voellmy (1955), Schweizerische Bauzeitung

## License

MIT — use it, cite it, improve it.
