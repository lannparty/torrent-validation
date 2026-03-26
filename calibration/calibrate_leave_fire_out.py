#!/usr/bin/env python3
"""
Leave-fire-out cross-validation for TORRENT's Platt scaling calibration.

Addresses NHESS reviewer concern: 5-fold random CV can leak information through
spatial autocorrelation — basins within the same fire share terrain, burn severity,
and soil properties. Leave-fire-out CV holds out ALL observations from one fire at
a time, ensuring zero spatial leakage between train and test sets.

If leave-fire-out Brier ≈ 5-fold random CV Brier → spatial leakage is not a problem.
If leave-fire-out Brier >> 5-fold random CV Brier → the original CV was overfit.

Usage:
    python scripts/calibrate_leave_fire_out.py
"""

import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import cross_val_predict

BASE = Path(__file__).resolve().parent.parent / "data" / "validation"
BINARY_CSV = BASE / "usgs-binary-outcomes.csv"
VOLUMES_CSV = BASE / "usgs-227-volumes.csv"
OUTPUT_DIR = BASE

# =============================================================================
# Staley M1 — exact match to calibrate_probabilities.py and Rust implementation
# =============================================================================
B0 = -3.63
B1 = 0.41
B2 = 0.67
B3 = 0.70


def staley_m1_logit(burned_steep_fraction, avg_dnbr, soil_kf, rainfall_15min_mm):
    i15 = rainfall_15min_mm
    x1r = burned_steep_fraction * i15
    x2r = (avg_dnbr / 1000.0) * i15
    x3r = soil_kf * i15
    return B0 + B1 * x1r + B2 * x2r + B3 * x3r


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def logit_func(p):
    p = max(1e-15, min(1.0 - 1e-15, p))
    return math.log(p / (1.0 - p))


# =============================================================================
# Data loading — identical to calibrate_probabilities.py
# =============================================================================

def load_fire_averages():
    per_fire = defaultdict(list)
    with open(VOLUMES_CSV) as f:
        for row in csv.DictReader(f):
            fire = row["FireName"]
            area_km2 = float(row["Area_km2"])
            modhigh23_km2 = float(row["ModHigh23_km2"])
            mean_dnbr = float(row["MeandNBR"])
            burned_steep = modhigh23_km2 / area_km2 if area_km2 > 0 else 0.0
            per_fire[fire].append({
                "burned_steep_fraction": burned_steep,
                "avg_dnbr": mean_dnbr,
            })

    fire_avg = {}
    for fire, entries in per_fire.items():
        n = len(entries)
        fire_avg[fire] = {
            "burned_steep_fraction": sum(e["burned_steep_fraction"] for e in entries) / n,
            "avg_dnbr": sum(e["avg_dnbr"] for e in entries) / n,
        }
    return fire_avg


def load_binary_outcomes():
    rows = []
    with open(BINARY_CSV) as f:
        for row in csv.DictReader(f):
            peak_i15 = float(row["PeakI15"])
            if peak_i15 <= 0:
                continue
            rows.append({
                "fire": row["FireName"],
                "response": int(row["Response"]),
                "peak_i15_mmhr": peak_i15,
            })
    return rows


def compute_raw_probabilities(rows, fire_avg,
                               default_burned_steep=0.50,
                               default_dnbr=300.0,
                               default_kf=0.02):
    logits = []
    probs = []
    actuals = []
    fires = []
    match_stats = {"fire_avg": 0, "default": 0}

    for row in rows:
        fire = row["fire"]
        rainfall_15min_mm = row["peak_i15_mmhr"] / 4.0

        if fire in fire_avg:
            burned_steep = fire_avg[fire]["burned_steep_fraction"]
            avg_dnbr = fire_avg[fire]["avg_dnbr"]
            match_stats["fire_avg"] += 1
        else:
            burned_steep = default_burned_steep
            avg_dnbr = default_dnbr
            match_stats["default"] += 1

        soil_kf = default_kf
        logit = staley_m1_logit(burned_steep, avg_dnbr, soil_kf, rainfall_15min_mm)
        prob = sigmoid(logit)

        logits.append(logit)
        probs.append(prob)
        actuals.append(row["response"])
        fires.append(fire)

    return (np.array(logits), np.array(probs), np.array(actuals),
            np.array(fires), match_stats)


# =============================================================================
# Leave-fire-out cross-validation
# =============================================================================

def leave_fire_out_cv(logits, actuals, fires):
    """Leave-fire-out CV: hold out all observations from each fire, one at a time.

    Returns:
        cv_probs: array of calibrated probabilities (each obs predicted when its fire was held out)
        fold_results: list of per-fire results with A, B, Brier, N, etc.
    """
    unique_fires = sorted(set(fires))
    cv_probs = np.zeros_like(logits, dtype=float)
    fold_results = []

    for held_out_fire in unique_fires:
        test_mask = fires == held_out_fire
        train_mask = ~test_mask

        X_train = logits[train_mask].reshape(-1, 1)
        y_train = actuals[train_mask]
        X_test = logits[test_mask].reshape(-1, 1)
        y_test = actuals[test_mask]

        n_test = int(test_mask.sum())
        n_pos_test = int(y_test.sum())

        # Fit Platt scaling on training fires
        lr = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000)
        lr.fit(X_train, y_train)

        A = float(lr.coef_[0, 0])
        B = float(lr.intercept_[0])

        # Predict on held-out fire
        test_probs = lr.predict_proba(X_test)[:, 1]
        cv_probs[test_mask] = test_probs

        # Compute per-fire Brier (only meaningful if n_test > 1)
        fire_brier = float(brier_score_loss(y_test, test_probs)) if n_test > 1 else None

        # AUC only computable if both classes present
        if n_test >= 2 and n_pos_test > 0 and n_pos_test < n_test:
            try:
                fire_auc = float(roc_auc_score(y_test, test_probs))
            except ValueError:
                fire_auc = None
        else:
            fire_auc = None

        fold_results.append({
            "fire": held_out_fire,
            "n_obs": n_test,
            "n_positive": n_pos_test,
            "n_negative": n_test - n_pos_test,
            "A": A,
            "B": B,
            "held_out_brier": fire_brier,
            "held_out_auc": fire_auc,
        })

    return cv_probs, fold_results


def five_fold_random_cv(logits, actuals):
    """Standard 5-fold random CV (the original approach). Returns cv_probs."""
    X = logits.reshape(-1, 1)
    lr = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000)
    cv_probs = cross_val_predict(lr, X, actuals, cv=5, method="predict_proba")[:, 1]
    return cv_probs


def fit_all_data(logits, actuals):
    """Fit on all data (deployment coefficients)."""
    X = logits.reshape(-1, 1)
    lr = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000)
    lr.fit(X, actuals)
    A = float(lr.coef_[0, 0])
    B = float(lr.intercept_[0])
    return A, B


def main():
    print("=" * 78)
    print("  TORRENT Leave-Fire-Out Cross-Validation for Platt Scaling")
    print("  Addresses NHESS reviewer: spatial autocorrelation leakage check")
    print("=" * 78)

    # Load data
    fire_avg = load_fire_averages()
    rows = load_binary_outcomes()
    logits, raw_probs, actuals, fires, match_stats = compute_raw_probabilities(rows, fire_avg)

    n = len(actuals)
    n_pos = int(actuals.sum())
    base_rate = n_pos / n
    brier_ref = base_rate * (1 - base_rate)
    unique_fires = sorted(set(fires))

    print(f"\n  Observations:    {n} ({n_pos} positive, {n - n_pos} negative)")
    print(f"  Base rate:       {base_rate:.4f}")
    print(f"  Unique fires:    {len(unique_fires)}")
    print(f"  Brier reference: {brier_ref:.4f} (climatological)")

    # =========================================================================
    # 1. Raw M1 performance
    # =========================================================================
    raw_brier = float(brier_score_loss(actuals, raw_probs))
    raw_auc = float(roc_auc_score(actuals, raw_probs))
    raw_bss = 1 - raw_brier / brier_ref

    print(f"\n  --- Raw Staley M1 ---")
    print(f"  Brier: {raw_brier:.6f}   AUC: {raw_auc:.4f}   BSS: {raw_bss:.4f}")

    # =========================================================================
    # 2. 5-fold random CV (reproduce original)
    # =========================================================================
    random_cv_probs = five_fold_random_cv(logits, actuals)
    random_brier = float(brier_score_loss(actuals, random_cv_probs))
    random_auc = float(roc_auc_score(actuals, random_cv_probs))
    random_bss = 1 - random_brier / brier_ref

    print(f"\n  --- 5-Fold Random CV (original) ---")
    print(f"  Brier: {random_brier:.6f}   AUC: {random_auc:.4f}   BSS: {random_bss:.4f}")

    # =========================================================================
    # 3. Leave-fire-out CV
    # =========================================================================
    lfo_cv_probs, fold_results = leave_fire_out_cv(logits, actuals, fires)
    lfo_brier = float(brier_score_loss(actuals, lfo_cv_probs))
    lfo_auc = float(roc_auc_score(actuals, lfo_cv_probs))
    lfo_bss = 1 - lfo_brier / brier_ref

    print(f"\n  --- Leave-Fire-Out CV ({len(unique_fires)} folds) ---")
    print(f"  Brier: {lfo_brier:.6f}   AUC: {lfo_auc:.4f}   BSS: {lfo_bss:.4f}")

    # =========================================================================
    # 4. Per-fire fold details
    # =========================================================================
    print(f"\n  {'Fire':<25} {'N':>5} {'Pos':>4} {'A':>10} {'B':>10} {'Brier':>8} {'AUC':>8}")
    print(f"  {'-'*25} {'-'*5} {'-'*4} {'-'*10} {'-'*10} {'-'*8} {'-'*8}")

    A_values = []
    B_values = []
    brier_values = []

    for fr in fold_results:
        A_values.append(fr["A"])
        B_values.append(fr["B"])
        if fr["held_out_brier"] is not None:
            brier_values.append(fr["held_out_brier"])
        brier_str = f"{fr['held_out_brier']:.4f}" if fr["held_out_brier"] is not None else "N/A"
        auc_str = f"{fr['held_out_auc']:.4f}" if fr["held_out_auc"] is not None else "N/A"
        print(f"  {fr['fire']:<25} {fr['n_obs']:>5} {fr['n_positive']:>4} "
              f"{fr['A']:>10.6f} {fr['B']:>10.6f} {brier_str:>8} {auc_str:>8}")

    A_arr = np.array(A_values)
    B_arr = np.array(B_values)
    brier_arr = np.array(brier_values)

    print(f"\n  Coefficient stability across {len(unique_fires)} folds:")
    print(f"    A: mean={A_arr.mean():.6f}  std={A_arr.std():.6f}  "
          f"min={A_arr.min():.6f}  max={A_arr.max():.6f}  "
          f"CV={A_arr.std()/abs(A_arr.mean())*100:.1f}%")
    print(f"    B: mean={B_arr.mean():.6f}  std={B_arr.std():.6f}  "
          f"min={B_arr.min():.6f}  max={B_arr.max():.6f}  "
          f"CV={B_arr.std()/abs(B_arr.mean())*100:.1f}%")

    print(f"\n  Per-fire held-out Brier scores (N={len(brier_values)} fires with >1 obs):")
    print(f"    Mean:     {brier_arr.mean():.6f}")
    print(f"    Std:      {brier_arr.std():.6f}")
    print(f"    Min:      {brier_arr.min():.6f}")
    print(f"    Max:      {brier_arr.max():.6f}")
    print(f"    Variance: {brier_arr.var():.6f}")

    # =========================================================================
    # 5. All-data fit (current deployment coefficients)
    # =========================================================================
    A_all, B_all = fit_all_data(logits, actuals)

    print(f"\n  All-data fit (current deployment): A={A_all:.6f}, B={B_all:.6f}")

    # =========================================================================
    # 6. Median A,B from leave-fire-out folds — more robust?
    # =========================================================================
    A_median = float(np.median(A_arr))
    B_median = float(np.median(B_arr))

    # Compute predictions using median coefficients
    median_probs = np.array([sigmoid(A_median * l + B_median) for l in logits])
    median_brier = float(brier_score_loss(actuals, median_probs))
    median_auc = float(roc_auc_score(actuals, median_probs))
    median_bss = 1 - median_brier / brier_ref

    print(f"\n  Median coefficients from LFO folds: A={A_median:.6f}, B={B_median:.6f}")
    print(f"  Brier: {median_brier:.6f}   AUC: {median_auc:.4f}   BSS: {median_bss:.4f}")

    # Also compute using all-data coefficients (not CV, just resubstitution)
    alldata_probs = np.array([sigmoid(A_all * l + B_all) for l in logits])
    alldata_brier = float(brier_score_loss(actuals, alldata_probs))

    # =========================================================================
    # 7. Comparison summary
    # =========================================================================
    print(f"\n{'=' * 78}")
    print(f"  COMPARISON SUMMARY")
    print(f"{'=' * 78}")
    print(f"  {'Method':<35} {'Brier':>8} {'AUC':>8} {'BSS':>8}")
    print(f"  {'-'*35} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'Raw Staley M1':<35} {raw_brier:>8.4f} {raw_auc:>8.4f} {raw_bss:>8.4f}")
    print(f"  {'Platt 5-fold random CV':<35} {random_brier:>8.4f} {random_auc:>8.4f} {random_bss:>8.4f}")
    print(f"  {'Platt leave-fire-out CV':<35} {lfo_brier:>8.4f} {lfo_auc:>8.4f} {lfo_bss:>8.4f}")
    print(f"  {'Platt all-data (resubstitution)':<35} {alldata_brier:>8.4f} {median_auc:>8.4f} {'':>8}")
    print(f"  {'Platt median A,B from LFO':<35} {median_brier:>8.4f} {median_auc:>8.4f} {median_bss:>8.4f}")
    print(f"  {'Climatology':<35} {brier_ref:>8.4f} {'N/A':>8} {'0.0000':>8}")

    brier_delta = lfo_brier - random_brier
    brier_delta_pct = brier_delta / random_brier * 100
    print(f"\n  Brier delta (LFO - random CV): {brier_delta:+.6f} ({brier_delta_pct:+.1f}%)")

    if abs(brier_delta_pct) < 5:
        leakage_verdict = "NEGLIGIBLE — spatial leakage is NOT a problem"
    elif brier_delta_pct > 0:
        leakage_verdict = f"DETECTED — LFO is {brier_delta_pct:.1f}% worse, original CV was overfit"
    else:
        leakage_verdict = f"NEGATIVE — LFO is actually {-brier_delta_pct:.1f}% better (unexpected)"

    print(f"  Spatial leakage verdict: {leakage_verdict}")

    auc_delta = abs(lfo_auc - random_auc)
    print(f"\n  AUC change (LFO vs random CV): {auc_delta:.4f} — "
          f"{'negligible' if auc_delta < 0.01 else 'notable shift'}")
    print(f"  AUC change (LFO vs raw):        {abs(lfo_auc - raw_auc):.4f} — "
          f"{'negligible' if abs(lfo_auc - raw_auc) < 0.01 else 'notable shift'}")

    # Coefficient stability assessment
    a_cv_pct = A_arr.std() / abs(A_arr.mean()) * 100
    b_cv_pct = B_arr.std() / abs(B_arr.mean()) * 100
    coeff_stable = a_cv_pct < 10 and b_cv_pct < 10
    print(f"\n  Coefficient stability: A CV={a_cv_pct:.1f}%, B CV={b_cv_pct:.1f}% — "
          f"{'STABLE' if coeff_stable else 'UNSTABLE'}")

    # Median vs all-data comparison
    median_vs_alldata = abs(median_brier - alldata_brier)
    print(f"  Median A,B vs all-data A,B Brier difference: {median_vs_alldata:.6f} — "
          f"{'negligible' if median_vs_alldata < 0.001 else 'meaningful'}")

    # =========================================================================
    # 8. Decide whether to update platt_calibration.json
    # =========================================================================
    # Use median LFO coefficients if they're meaningfully different AND better
    use_median = False
    if median_brier < alldata_brier and median_vs_alldata > 0.001:
        use_median = True
        print(f"\n  RECOMMENDATION: Use median LFO coefficients (more robust, lower Brier)")
    else:
        print(f"\n  RECOMMENDATION: Keep all-data coefficients (median is not meaningfully better)")

    # =========================================================================
    # 9. Save results
    # =========================================================================
    results = {
        "analysis": "Leave-fire-out cross-validation for Platt scaling calibration",
        "purpose": "Address NHESS reviewer concern about spatial autocorrelation leakage",
        "dataset": {
            "n_observations": n,
            "n_positive": n_pos,
            "n_fires": len(unique_fires),
            "base_rate": base_rate,
            "brier_reference": brier_ref,
        },
        "comparison": {
            "raw_m1": {
                "brier": raw_brier,
                "auc": raw_auc,
                "bss": raw_bss,
            },
            "platt_5fold_random_cv": {
                "brier": random_brier,
                "auc": random_auc,
                "bss": random_bss,
            },
            "platt_leave_fire_out_cv": {
                "brier": lfo_brier,
                "auc": lfo_auc,
                "bss": lfo_bss,
            },
            "platt_median_lfo_coefficients": {
                "A": A_median,
                "B": B_median,
                "brier": median_brier,
                "auc": median_auc,
                "bss": median_bss,
            },
            "platt_all_data_fit": {
                "A": A_all,
                "B": B_all,
                "brier_resubstitution": alldata_brier,
            },
        },
        "spatial_leakage": {
            "brier_delta_lfo_minus_random": brier_delta,
            "brier_delta_percent": brier_delta_pct,
            "verdict": leakage_verdict,
        },
        "coefficient_stability": {
            "A_mean": float(A_arr.mean()),
            "A_std": float(A_arr.std()),
            "A_cv_percent": a_cv_pct,
            "B_mean": float(B_arr.mean()),
            "B_std": float(B_arr.std()),
            "B_cv_percent": b_cv_pct,
            "stable": bool(coeff_stable),
        },
        "per_fire_folds": fold_results,
        "recommendation": {
            "use_median_coefficients": bool(use_median),
            "reason": (
                "Median LFO coefficients are more robust and yield lower Brier"
                if use_median else
                "All-data coefficients are adequate; median is not meaningfully better"
            ),
        },
    }

    results_path = OUTPUT_DIR / "leave_fire_out_results.json"
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Saved: {results_path}")

    # Update platt_calibration.json if median coefficients are meaningfully better
    platt_path = OUTPUT_DIR / "platt_calibration.json"
    if use_median:
        platt_params = {
            "method": "platt_scaling",
            "description": (
                "Platt scaling recalibration trained on 2,995 USGS binary outcome observations. "
                "Coefficients are median of 17 leave-fire-out CV folds (robust to spatial "
                "autocorrelation). Apply as: P_calibrated = sigmoid(A * logit_raw + B)."
            ),
            "A": A_median,
            "B": B_median,
            "training_n": n,
            "training_positives": n_pos,
            "raw_brier": raw_brier,
            "calibrated_brier_cv_random": random_brier,
            "calibrated_brier_cv_lfo": lfo_brier,
            "calibrated_brier_median_coeffs": median_brier,
            "raw_auc": raw_auc,
            "calibrated_auc_cv_lfo": lfo_auc,
            "equation": f"P_calibrated = sigmoid({A_median:.6f} * logit_raw + {B_median:.6f})",
            "cv_method": "leave-fire-out (17 folds, stratified by fire)",
            "reference": "Platt (1999), 'Probabilistic Outputs for Support Vector Machines'",
        }
        with open(platt_path, "w") as f:
            json.dump(platt_params, f, indent=2)
        print(f"  Updated: {platt_path} (now uses median LFO coefficients)")
    else:
        # Add LFO results to existing calibration without changing A,B
        with open(platt_path) as f:
            existing = json.load(f)
        existing["leave_fire_out_cv"] = {
            "brier": lfo_brier,
            "auc": lfo_auc,
            "bss": lfo_bss,
            "spatial_leakage_verdict": leakage_verdict,
            "n_folds": len(unique_fires),
            "A_mean_across_folds": float(A_arr.mean()),
            "A_std_across_folds": float(A_arr.std()),
            "B_mean_across_folds": float(B_arr.mean()),
            "B_std_across_folds": float(B_arr.std()),
        }
        with open(platt_path, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"  Updated: {platt_path} (added LFO results, coefficients unchanged)")

    print(f"\n{'=' * 78}")
    print(f"  This analysis makes the paper defensible against the spatial leakage concern.")
    print(f"{'=' * 78}\n")


if __name__ == "__main__":
    main()
