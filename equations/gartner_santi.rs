// Extracted published equation implementations
// Full pipeline is proprietary

pub fn santi_volume_estimate(channel_gradient: f64, upstream_burned_area_km2: f64) -> f64 {
    // Guard against log(0)
    let burned_area = upstream_burned_area_km2.max(1e-6);
    let ln_v = 0.59 + 7.21 * channel_gradient + 0.54 * burned_area.ln();
    ln_v.exp()
}

fn cross_check_volumes(primary_volume_m3: f64, santi_volume_m3: f64) -> (f64, String) {
    if primary_volume_m3 <= 0.0 || santi_volume_m3 <= 0.0 {
        return (primary_volume_m3.max(santi_volume_m3).max(1.0), "low".to_string());
    }

    // log_diff in natural-log units; 1 "log-unit" (order of magnitude) = ln(10) ≈ 2.303
    let log_diff = (primary_volume_m3.ln() - santi_volume_m3.ln()).abs();
    let half_log_unit = 10.0_f64.ln() * 0.5; // ~1.15
    let one_log_unit = 10.0_f64.ln();          // ~2.30

    if log_diff <= half_log_unit {
        // Within 0.5 log-units (~3.2x): high confidence, use primary
        (primary_volume_m3, "high".to_string())
    } else if log_diff <= one_log_unit {
        // Within 1 log-unit (~10x): moderate confidence, use primary
        (primary_volume_m3, "moderate".to_string())
    } else {
        // >1 log-unit (>10x difference): low confidence, use geometric mean
        let geomean = (primary_volume_m3 * santi_volume_m3).sqrt();
        warn!(
            primary = primary_volume_m3,
            santi = santi_volume_m3,
            geomean,
            "volume estimates differ by >10x, using geometric mean"
        );
        (geomean, "low".to_string())
    }
}

