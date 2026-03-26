#!/usr/bin/env python3
"""
Platt scaling recalibration for TORRENT's Staley M1 output.

Problem: AUC is 0.852 (ranking works) but probabilities are 2-3x overconfident.
Solution: Fit a logistic regression that maps raw M1 logit -> calibrated probability,
trained on 2,995 USGS observations. This is Platt scaling — a standard post-processing
step that preserves ranking (AUC) while fixing calibration (Brier score).

Also fits isotonic regression as an alternative.

Usage:
    python scripts/calibrate_probabilities.py
"""

import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import cross_val_predict

BASE = Path(__file__).resolve().parent.parent / "data" / "validation"
BINARY_CSV = BASE / "usgs-binary-outcomes.csv"
VOLUMES_CSV = BASE / "usgs-227-volumes.csv"
OUTPUT_DIR = BASE


# =============================================================================
# Staley M1 — exact match to Rust implementation in the Rust implementation
# =============================================================================
# Coefficients from Staley et al. (2016), USGS OFR 2016-1106, Table 3
B0 = -3.63   # intercept
B1 = 0.41    # X1R: burned steep area x rainfall
B2 = 0.67    # X2R: average dNBR/1000 x rainfall
B3 = 0.70    # X3R: soil KF x rainfall


def staley_m1_logit(burned_steep_fraction, avg_dnbr, soil_kf, rainfall_15min_mm):
    """Compute the raw logit (before sigmoid) from Staley M1.
    Matches the Staley M1 implementation exactly."""
    i15 = rainfall_15min_mm
    x1r = burned_steep_fraction * i15
    x2r = (avg_dnbr / 1000.0) * i15
    x3r = soil_kf * i15
    return B0 + B1 * x1r + B2 * x2r + B3 * x3r


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def logit_func(p):
    """Inverse of sigmoid. Clamp to avoid log(0)."""
    p = max(1e-15, min(1.0 - 1e-15, p))
    return math.log(p / (1.0 - p))


# =============================================================================
# Data loading
# =============================================================================

def load_fire_averages():
    """Load per-fire averages from the 227-volume inventory.

    Returns dict: FireName -> {burned_steep_fraction, avg_dnbr, soil_kf (None)}
    """
    per_fire = defaultdict(list)

    with open(VOLUMES_CSV) as f:
        for row in csv.DictReader(f):
            fire = row["FireName"]
            area_km2 = float(row["Area_km2"])
            modhigh23_km2 = float(row["ModHigh23_km2"])
            mean_dnbr = float(row["MeandNBR"])

            # burned_steep_fraction = proportion of watershed burned mod/high AND slope >= 23 deg
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
    """Load binary outcomes, filtering out rows with invalid PeakI15."""
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
    """Compute Staley M1 raw probability for each observation.

    Returns (logits, probabilities, actuals, match_stats).
    """
    logits = []
    probs = []
    actuals = []
    match_stats = {"fire_avg": 0, "default": 0}

    for row in rows:
        fire = row["fire"]
        # PeakI15 is mm/hr intensity; M1 uses 15-min accumulation in mm
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

    return np.array(logits), np.array(probs), np.array(actuals), match_stats


# =============================================================================
# Calibration
# =============================================================================

def fit_platt_scaling(logits, actuals):
    """Fit Platt scaling: logistic regression of Response ~ logit_raw.

    Platt scaling finds A, B such that:
        P_calibrated = sigmoid(A * logit_raw + B)

    Uses 5-fold cross-validation to produce out-of-sample calibrated probabilities.
    Final model is fit on all data for deployment.
    """
    X = logits.reshape(-1, 1)
    y = actuals

    # Cross-validated predictions (out-of-sample for honest evaluation)
    lr = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000)
    cv_probs = cross_val_predict(lr, X, y, cv=5, method="predict_proba")[:, 1]

    # Final model on all data (for deployment coefficients)
    lr_final = LogisticRegression(C=1e10, solver="lbfgs", max_iter=1000)
    lr_final.fit(X, y)

    # Extract A and B: sklearn's logistic regression gives coef_ and intercept_
    # P = sigmoid(coef * x + intercept)
    A = float(lr_final.coef_[0, 0])
    B = float(lr_final.intercept_[0])

    return A, B, cv_probs


def fit_isotonic_regression(probs, actuals):
    """Fit isotonic regression: monotone mapping from raw probability to calibrated.

    Uses 5-fold cross-validation for honest evaluation.
    Final model fit on all data for deployment.
    """
    from sklearn.model_selection import KFold

    cv_probs = np.zeros_like(probs, dtype=float)
    kf = KFold(n_splits=5, shuffle=True, random_state=42)

    for train_idx, test_idx in kf.split(probs):
        ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        ir.fit(probs[train_idx], actuals[train_idx])
        cv_probs[test_idx] = ir.predict(probs[test_idx])

    # Final model on all data
    ir_final = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    ir_final.fit(probs, actuals)

    # Extract lookup table for Rust
    # IsotonicRegression stores X_ and y_ (the step function breakpoints)
    lookup = list(zip(ir_final.X_thresholds_.tolist(), ir_final.y_thresholds_.tolist()))

    return lookup, cv_probs


def calibration_table(predictions, actuals, n_bins=10):
    """Return calibration table: predicted decile vs observed rate."""
    paired = sorted(zip(predictions, actuals))
    bin_size = len(paired) // n_bins
    rows = []
    for i in range(n_bins):
        start = i * bin_size
        end = start + bin_size if i < n_bins - 1 else len(paired)
        chunk = paired[start:end]
        mean_pred = sum(p for p, _ in chunk) / len(chunk)
        mean_obs = sum(a for _, a in chunk) / len(chunk)
        rows.append((i + 1, len(chunk), mean_pred, mean_obs))
    return rows


def print_calibration_comparison(label, preds, actuals, n_bins=10):
    """Print a calibration table."""
    cal = calibration_table(preds, actuals, n_bins)
    print(f"\n  {label}")
    print(f"  {'Decile':>6}  {'N':>5}  {'Mean Pred':>10}  {'Obs Rate':>10}  {'Gap':>10}")
    print(f"  {'------':>6}  {'-----':>5}  {'----------':>10}  {'----------':>10}  {'----------':>10}")
    for decile, n_bin, mp, mo in cal:
        gap = mp - mo
        print(f"  {decile:>6}  {n_bin:>5}  {mp:>10.4f}  {mo:>10.4f}  {gap:>+10.4f}")


def main():
    print("=" * 70)
    print("  TORRENT Probability Recalibration — Platt Scaling")
    print("  Training on 2,995 USGS binary outcome observations")
    print("=" * 70)

    # Load data
    fire_avg = load_fire_averages()
    rows = load_binary_outcomes()
    logits, raw_probs, actuals, match_stats = compute_raw_probabilities(rows, fire_avg)

    n = len(actuals)
    n_pos = int(actuals.sum())
    base_rate = n_pos / n

    print(f"\n  Observations:    {n} ({n_pos} debris flows, {n - n_pos} no-flow)")
    print(f"  Base rate:       {base_rate:.4f}")
    print(f"  Match stats:     fire_avg={match_stats['fire_avg']}, defaults={match_stats['default']}")
    print(f"  Fires with data: {len(fire_avg)} fires in volumes CSV")

    # --- Raw metrics ---
    raw_brier = brier_score_loss(actuals, raw_probs)
    raw_auc = roc_auc_score(actuals, raw_probs)
    brier_ref = base_rate * (1 - base_rate)
    raw_bss = 1 - raw_brier / brier_ref

    print(f"\n  --- Raw Staley M1 ---")
    print(f"  AUC-ROC:         {raw_auc:.4f}")
    print(f"  Brier Score:     {raw_brier:.4f}")
    print(f"  Brier Reference: {brier_ref:.4f} (climatological)")
    print(f"  Brier Skill:     {raw_bss:.4f}")

    print_calibration_comparison("Raw M1 Calibration", raw_probs, actuals)

    # --- Platt scaling ---
    print(f"\n  --- Platt Scaling (5-fold CV) ---")
    A, B, platt_cv_probs = fit_platt_scaling(logits, actuals)
    platt_brier = brier_score_loss(actuals, platt_cv_probs)
    platt_auc = roc_auc_score(actuals, platt_cv_probs)
    platt_bss = 1 - platt_brier / brier_ref

    print(f"  Platt coefficients: A={A:.6f}, B={B:.6f}")
    print(f"  Calibration: P_cal = sigmoid({A:.6f} * logit_raw + {B:.6f})")
    print(f"  AUC-ROC:         {platt_auc:.4f}  (should match raw: {raw_auc:.4f})")
    print(f"  Brier Score:     {platt_brier:.4f}  (was {raw_brier:.4f})")
    print(f"  Brier Skill:     {platt_bss:.4f}  (was {raw_bss:.4f})")
    print(f"  Brier improvement: {(raw_brier - platt_brier) / raw_brier * 100:.1f}%")

    print_calibration_comparison("Platt-Calibrated", platt_cv_probs, actuals)

    # --- Isotonic regression ---
    print(f"\n  --- Isotonic Regression (5-fold CV) ---")
    iso_lookup, iso_cv_probs = fit_isotonic_regression(raw_probs, actuals)
    iso_brier = brier_score_loss(actuals, iso_cv_probs)
    iso_auc = roc_auc_score(actuals, iso_cv_probs)
    iso_bss = 1 - iso_brier / brier_ref

    print(f"  Isotonic breakpoints: {len(iso_lookup)}")
    print(f"  AUC-ROC:         {iso_auc:.4f}  (should match raw: {raw_auc:.4f})")
    print(f"  Brier Score:     {iso_brier:.4f}  (was {raw_brier:.4f})")
    print(f"  Brier Skill:     {iso_bss:.4f}  (was {raw_bss:.4f})")
    print(f"  Brier improvement: {(raw_brier - iso_brier) / raw_brier * 100:.1f}%")

    print_calibration_comparison("Isotonic-Calibrated", iso_cv_probs, actuals)

    # --- Summary ---
    print(f"\n{'=' * 70}")
    print(f"  SUMMARY")
    print(f"{'=' * 70}")
    print(f"  {'Method':<25} {'Brier':>8} {'AUC':>8} {'BSS':>8}")
    print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'Raw Staley M1':<25} {raw_brier:>8.4f} {raw_auc:>8.4f} {raw_bss:>8.4f}")
    print(f"  {'Platt scaling (CV)':<25} {platt_brier:>8.4f} {platt_auc:>8.4f} {platt_bss:>8.4f}")
    print(f"  {'Isotonic (CV)':<25} {iso_brier:>8.4f} {iso_auc:>8.4f} {iso_bss:>8.4f}")
    print(f"  {'Climatology':<25} {brier_ref:>8.4f} {'N/A':>8} {'0.0000':>8}")

    auc_drift = abs(platt_auc - raw_auc)
    print(f"\n  AUC drift (Platt): {auc_drift:.4f} — {'OK' if auc_drift < 0.01 else 'WARNING: ranking changed!'}")
    auc_drift_iso = abs(iso_auc - raw_auc)
    print(f"  AUC drift (Isotonic): {auc_drift_iso:.4f} — {'OK' if auc_drift_iso < 0.01 else 'WARNING: ranking changed!'}")

    # --- Save calibration parameters ---
    platt_params = {
        "method": "platt_scaling",
        "description": "Platt scaling recalibration trained on 2,995 USGS binary outcome observations. "
                       "Apply as: P_calibrated = sigmoid(A * logit_raw + B), where logit_raw is the "
                       "raw Staley M1 logit (before sigmoid).",
        "A": A,
        "B": B,
        "training_n": n,
        "training_positives": n_pos,
        "raw_brier": float(raw_brier),
        "calibrated_brier_cv": float(platt_brier),
        "raw_auc": float(raw_auc),
        "calibrated_auc_cv": float(platt_auc),
        "equation": f"P_calibrated = sigmoid({A:.6f} * logit_raw + {B:.6f})",
        "reference": "Platt (1999), 'Probabilistic Outputs for Support Vector Machines'",
    }
    platt_path = OUTPUT_DIR / "platt_calibration.json"
    with open(platt_path, "w") as f:
        json.dump(platt_params, f, indent=2)
    print(f"\n  Saved Platt parameters:   {platt_path}")

    iso_params = {
        "method": "isotonic_regression",
        "description": "Isotonic regression recalibration trained on 2,995 USGS binary outcome observations. "
                       "Apply by interpolating raw_probability through the lookup table.",
        "lookup_table": [{"raw": r, "calibrated": c} for r, c in iso_lookup],
        "training_n": n,
        "training_positives": n_pos,
        "raw_brier": float(raw_brier),
        "calibrated_brier_cv": float(iso_brier),
        "raw_auc": float(raw_auc),
        "calibrated_auc_cv": float(iso_auc),
    }
    iso_path = OUTPUT_DIR / "isotonic_calibration.json"
    with open(iso_path, "w") as f:
        json.dump(iso_params, f, indent=2)
    print(f"  Saved isotonic parameters: {iso_path}")

    # Recommend which to use
    if platt_brier <= iso_brier:
        print(f"\n  Recommendation: Use PLATT SCALING (simpler, 2 parameters, comparable performance)")
    else:
        print(f"\n  Recommendation: Use ISOTONIC REGRESSION (better Brier score, but more complex)")

    print()


if __name__ == "__main__":
    main()
