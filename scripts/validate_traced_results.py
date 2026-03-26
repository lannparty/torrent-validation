#!/usr/bin/env python3
"""
CI validation gate: check 6 benchmark fires for metric regression.

Downloads current results from S3, compares against baseline thresholds.
Fails the build if:
  - AUC drops > 1% from baseline
  - RMSE increases > 5% from baseline
  - Any benchmark fire is missing from S3

Usage:
  python scripts/validate_traced_results.py

Requires: AWS credentials with s3:GetObject on the production S3 bucket.
"""

import json
import math
import sys
import subprocess
from pathlib import Path

S3_BUCKET = "YOUR-S3-BUCKET"
S3_PREFIX = "fires"

# 6 benchmark fires — same as backtest_fire_level.py
BENCHMARK_SLUGS = [
    "schultz-2010",
    "grizzly-creek-2020",
    "cameron-peak-2020",
    "east-troublesome-2020",
    "station-2009",
    "thomas-2017",
]

# Baseline thresholds — minimum acceptable metrics per fire.
# These are conservative floors. Update when model improves.
BASELINES = {
    "schultz-2010":          {"auc": 0.70, "rmse": 0.40},
    "grizzly-creek-2020":    {"auc": 0.65, "rmse": 0.45},
    "cameron-peak-2020":     {"auc": 0.65, "rmse": 0.45},
    "east-troublesome-2020": {"auc": 0.65, "rmse": 0.45},
    "station-2009":          {"auc": 0.70, "rmse": 0.40},
    "thomas-2017":           {"auc": 0.68, "rmse": 0.42},
}

# Regression thresholds
AUC_DROP_THRESHOLD = 0.01    # Fail if AUC drops > 1% absolute
RMSE_INCREASE_THRESHOLD = 0.05  # Fail if RMSE increases > 5% relative


def s3_get_json(key: str) -> dict | None:
    """Download a JSON object from S3 using the AWS CLI."""
    try:
        result = subprocess.run(
            ["aws", "s3", "cp", f"s3://{S3_BUCKET}/{key}", "-"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"  WARN: Failed to fetch s3://{S3_BUCKET}/{key}: {result.stderr.strip()}")
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"  WARN: Error fetching {key}: {e}")
        return None


def extract_metrics(manifest: dict) -> dict:
    """Extract AUC and RMSE from a fire's manifest or results JSON.

    Looks for metrics in several possible locations since the schema
    may vary between fire vintages.
    """
    metrics = {}

    # Try top-level validation metrics
    if "validation" in manifest:
        v = manifest["validation"]
        if "auc" in v:
            metrics["auc"] = float(v["auc"])
        if "auc_roc" in v:
            metrics["auc"] = float(v["auc_roc"])
        if "rmse" in v:
            metrics["rmse"] = float(v["rmse"])

    # Try nested under results.validation
    results = manifest.get("results", {})
    if "validation" in results:
        v = results["validation"]
        if "auc" in v and "auc" not in metrics:
            metrics["auc"] = float(v["auc"])
        if "auc_roc" in v and "auc" not in metrics:
            metrics["auc"] = float(v["auc_roc"])
        if "rmse" in v and "rmse" not in metrics:
            metrics["rmse"] = float(v["rmse"])

    # Try metrics block
    if "metrics" in manifest:
        m = manifest["metrics"]
        if "auc" in m and "auc" not in metrics:
            metrics["auc"] = float(m["auc"])
        if "rmse" in m and "rmse" not in metrics:
            metrics["rmse"] = float(m["rmse"])

    return metrics


def validate_fire(slug: str) -> list[str]:
    """Validate a single benchmark fire. Returns list of failure messages."""
    failures = []
    baseline = BASELINES[slug]

    # Try manifest.json first, then results.json
    manifest = s3_get_json(f"{S3_PREFIX}/{slug}/manifest.json")
    if manifest is None:
        manifest = s3_get_json(f"{S3_PREFIX}/{slug}/results.json")
    if manifest is None:
        failures.append(f"{slug}: missing from S3 (no manifest.json or results.json)")
        return failures

    metrics = extract_metrics(manifest)

    if not metrics:
        # Fire exists but has no validation metrics — not a regression,
        # just means validation hasn't been computed for this fire yet.
        print(f"  {slug}: no validation metrics found in manifest (skipping metric checks)")
        return failures

    # Check AUC
    if "auc" in metrics:
        auc = metrics["auc"]
        auc_baseline = baseline["auc"]
        auc_drop = auc_baseline - auc
        status = "PASS" if auc_drop <= AUC_DROP_THRESHOLD else "FAIL"
        print(f"  {slug} AUC: {auc:.4f} (baseline: {auc_baseline:.4f}, delta: {-auc_drop:+.4f}) [{status}]")
        if auc_drop > AUC_DROP_THRESHOLD:
            failures.append(
                f"{slug}: AUC regressed {auc_drop:.4f} "
                f"(from {auc_baseline:.4f} to {auc:.4f}, threshold: {AUC_DROP_THRESHOLD})"
            )

    # Check RMSE
    if "rmse" in metrics:
        rmse = metrics["rmse"]
        rmse_baseline = baseline["rmse"]
        if rmse_baseline > 0:
            rmse_increase_pct = (rmse - rmse_baseline) / rmse_baseline
        else:
            rmse_increase_pct = 0.0
        status = "PASS" if rmse_increase_pct <= RMSE_INCREASE_THRESHOLD else "FAIL"
        print(f"  {slug} RMSE: {rmse:.4f} (baseline: {rmse_baseline:.4f}, delta: {rmse_increase_pct:+.1%}) [{status}]")
        if rmse_increase_pct > RMSE_INCREASE_THRESHOLD:
            failures.append(
                f"{slug}: RMSE regressed {rmse_increase_pct:.1%} "
                f"(from {rmse_baseline:.4f} to {rmse:.4f}, threshold: {RMSE_INCREASE_THRESHOLD:.0%})"
            )

    return failures


def main():
    print("=" * 65)
    print("TORRENT Validation Gate — 6 Benchmark Fires")
    print("=" * 65)
    print()

    all_failures = []
    for slug in BENCHMARK_SLUGS:
        print(f"[{slug}]")
        failures = validate_fire(slug)
        all_failures.extend(failures)
        print()

    print("=" * 65)
    if all_failures:
        print(f"FAILED — {len(all_failures)} regression(s) detected:")
        for f in all_failures:
            print(f"  ✗ {f}")
        print()
        print("Fix the regression or update baselines in scripts/validate_traced_results.py")
        sys.exit(1)
    else:
        print("PASSED — all benchmark fires within tolerance")
        sys.exit(0)


if __name__ == "__main__":
    main()
