#!/usr/bin/env python3
"""Reproduce TORRENT debris flow calculations from a traced_result.json.

This standalone script re-runs the Staley M1 probability model and
Gartner volume model from the stored input values, verifying that
the outputs match within floating-point tolerance.

Requires only: Python 3.8+, numpy (optional, for batch mode)

Usage:
    python reproduce.py traced_result.json
    python reproduce.py --from-s3 schultz-2010 --storm 10

References:
    Staley et al. (2016), USGS OFR 2016-1106
    Gartner et al. (2014), Geomorphology
    Santi et al. (2008), Geomorphology
"""
import json
import math
import sys
import argparse


def staley_m1(rainfall_15min_mm: float, burned_steep_fraction: float,
              avg_dnbr: float, soil_kf: float) -> float:
    """Staley et al. (2016) M1 logistic regression.

    X = -3.63 + 0.41*X1R + 0.67*X2R + 0.70*X3R
    where:
        X1R = burned_steep_fraction * rainfall_15min_mm
        X2R = (avg_dnbr / 1000) * rainfall_15min_mm
        X3R = soil_kf * rainfall_15min_mm

    Returns: probability of debris flow [0, 1]
    Reference: USGS OFR 2016-1106, Table 3
    """
    x1r = burned_steep_fraction * rainfall_15min_mm
    x2r = (avg_dnbr / 1000.0) * rainfall_15min_mm
    x3r = soil_kf * rainfall_15min_mm
    logit = -3.63 + 0.41 * x1r + 0.67 * x2r + 0.70 * x3r
    return 1.0 / (1.0 + math.exp(-logit))


def gartner_volume(i15_mm_hr: float, burned_area_km2: float,
                   relief_m: float) -> float:
    """Gartner et al. (2014) empirical volume model.

    ln(V) = 4.22 + 0.39*sqrt(i15) + 0.36*ln(Bmh) + 0.13*sqrt(R)

    Returns: volume in m³
    Reference: Gartner et al. 2014
    """
    bmh = max(burned_area_km2, 0.001)
    r = max(relief_m, 1.0)
    ln_v = 4.22 + 0.39 * math.sqrt(i15_mm_hr) + 0.36 * math.log(bmh) + 0.13 * math.sqrt(r)
    return math.exp(ln_v)


def santi_volume(channel_gradient: float, burned_area_km2: float) -> float:
    """Santi et al. (2008) volume cross-check.

    ln(V) = 0.59 + 7.21*gradient + 0.54*ln(area)

    Returns: volume in m³
    Reference: Santi et al. 2008
    """
    area = max(burned_area_km2, 1e-6)
    ln_v = 0.59 + 7.21 * channel_gradient + 0.54 * math.log(area)
    return math.exp(ln_v)


def verify_watershed(ws: dict, tolerance: float = 0.02) -> list:
    """Verify a single watershed's calculations.

    Returns list of (check_name, expected, actual, pass) tuples.
    """
    results = []
    calc = ws.get('calculation', {})
    if not calc:
        return [('calculation_trace', 'present', 'missing', False)]

    # Verify Staley M1 probability
    inputs = calc if 'rainfall_15min_mm' in calc else calc.get('inputs', calc)
    rain = inputs.get('rainfall_15min_mm', 0)
    steep = inputs.get('burned_steep_fraction', 0)
    dnbr = inputs.get('avg_dnbr', 0)
    kf = inputs.get('soil_kf', 0)

    if rain > 0:
        expected_p = staley_m1(rain, steep, dnbr, kf)
        actual_p = ws['probability_pct'] / 100.0
        diff = abs(expected_p - actual_p)
        results.append(('staley_probability', f'{expected_p:.4f}', f'{actual_p:.4f}',
                        diff < tolerance))

    # Verify Staley logit
    x1r = calc.get('x1r_burned_steep_rain', steep * rain)
    x2r = calc.get('x2r_dnbr_rain', (dnbr / 1000.0) * rain)
    x3r = calc.get('x3r_kf_rain', kf * rain)
    expected_logit = -3.63 + 0.41 * x1r + 0.67 * x2r + 0.70 * x3r
    actual_logit = calc.get('logit', 0)
    if actual_logit != 0:
        results.append(('staley_logit', f'{expected_logit:.3f}', f'{actual_logit:.3f}',
                        abs(expected_logit - actual_logit) < 0.01))

    # Verify Gartner volume
    gv = calc.get('gartner_volume', calc)
    i15 = gv.get('i15_mm_hr', rain * 4)
    bmh = gv.get('burned_area_km2', 0)
    relief = gv.get('relief_m', 100)
    if i15 > 0 and bmh > 0:
        expected_v = gartner_volume(i15, bmh, relief)
        actual_raw = gv.get('raw_volume_m3', gv.get('gartner_raw_volume_m3', 0))
        if actual_raw > 0:
            diff = abs(math.log10(expected_v) - math.log10(actual_raw))
            results.append(('gartner_raw_volume', f'{expected_v:.0f}', f'{actual_raw:.0f}',
                            diff < 0.01))

    return results


def verify_traced_result(tr: dict) -> tuple:
    """Verify all watersheds in a traced result.

    Returns (total_checks, passed_checks, failures)
    """
    total = 0
    passed = 0
    failures = []

    for ws in tr.get('watersheds', []):
        checks = verify_watershed(ws)
        for name, expected, actual, ok in checks:
            total += 1
            if ok:
                passed += 1
            else:
                failures.append(f"WS-{ws['id']} {name}: expected={expected}, actual={actual}")

    return total, passed, failures


def main():
    parser = argparse.ArgumentParser(description='Reproduce TORRENT calculations')
    parser.add_argument('file', nargs='?', help='traced_result.json file path')
    parser.add_argument('--from-s3', help='Fire slug to fetch from S3')
    parser.add_argument('--storm', type=int, default=10, help='Storm return period (default: 10)')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()

    if args.from_s3:
        import subprocess
        result = subprocess.run(
            ['aws', 's3', 'cp',
             f's3://YOUR-S3-BUCKET/fires/{args.from_s3}/storm-{args.storm}yr/traced_result.json',
             '-'],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            # Fall back to calculation_traces.json
            result = subprocess.run(
                ['aws', 's3', 'cp',
                 f's3://YOUR-S3-BUCKET/fires/{args.from_s3}/storm-{args.storm}yr/calculation_traces.json',
                 '-'],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f'ERROR: Could not fetch data for {args.from_s3}')
                sys.exit(1)
            # Wrap traces in a minimal traced_result structure
            traces = json.loads(result.stdout)
            tr = {
                'watersheds': [
                    {'id': t['sub_watershed_id'], 'probability_pct': 0, 'calculation': t}
                    for t in traces.get('traces', [])
                ]
            }
        else:
            tr = json.loads(result.stdout)
    elif args.file:
        with open(args.file) as f:
            tr = json.load(f)
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Reproducing calculations for {len(tr.get('watersheds', []))} sub-watersheds...")
    total, passed, failures = verify_traced_result(tr)

    if args.verbose or failures:
        for f in failures:
            print(f'  FAIL: {f}')

    print(f'\n{passed}/{total} checks passed')
    if failures:
        print(f'{len(failures)} FAILURES')
        sys.exit(1)
    else:
        print('ALL CHECKS PASS — calculations reproduced successfully')


if __name__ == '__main__':
    main()
