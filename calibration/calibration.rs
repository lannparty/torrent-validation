//! Probability recalibration via Platt scaling.
//!
//! TORRENT DEVIATION: Platt scaling recalibration trained on 2,995 USGS
//! binary outcome observations. The raw Staley M1 model has good
//! discrimination (AUC ~0.85) but overconfident probabilities (Brier skill
//! score negative). This module applies a learned logistic transform to
//! the raw logit, preserving ranking while fixing calibration.
//!
//! Method: Platt (1999), "Probabilistic Outputs for Support Vector Machines"
//! Coefficients fit via sklearn LogisticRegression on USGS dataset with
//! 5-fold cross-validation.

use serde::Deserialize;
use std::path::Path;

/// Platt scaling calibration parameters.
///
/// Transforms raw M1 logit to calibrated probability:
///   P_calibrated = sigmoid(A * logit_raw + B)
#[derive(Debug, Clone)]
pub struct PlattCalibration {
    pub a: f64,
    pub b: f64,
}

/// Default calibration coefficients trained on 2,995 USGS observations.
/// These are compiled into the binary so no file I/O is needed at runtime.
impl Default for PlattCalibration {
    fn default() -> Self {
        // From scripts/calibrate_probabilities.py, fit on usgs-binary-outcomes.csv
        // Raw Brier: 0.1590 -> Calibrated Brier (CV): 0.0837
        PlattCalibration {
            a: 0.398962,
            b: -2.129460,
        }
    }
}

#[derive(Deserialize)]
struct PlattJson {
    #[serde(rename = "A")]
    a: f64,
    #[serde(rename = "B")]
    b: f64,
}

impl PlattCalibration {
    /// Load calibration parameters from a JSON file.
    ///
    /// Falls back to compiled-in defaults if the file is missing or malformed.
    pub fn load(path: &Path) -> Self {
        match std::fs::read_to_string(path) {
            Ok(contents) => match serde_json::from_str::<PlattJson>(&contents) {
                Ok(params) => {
                    tracing::info!(
                        a = params.a,
                        b = params.b,
                        "loaded Platt calibration from {}",
                        path.display()
                    );
                    PlattCalibration {
                        a: params.a,
                        b: params.b,
                    }
                }
                Err(e) => {
                    tracing::warn!(
                        "failed to parse {}: {}, using compiled-in defaults",
                        path.display(),
                        e
                    );
                    PlattCalibration::default()
                }
            },
            Err(_) => {
                tracing::debug!(
                    "calibration file {} not found, using compiled-in defaults",
                    path.display()
                );
                PlattCalibration::default()
            }
        }
    }

    /// Calibrate a raw probability from the Staley M1 model.
    ///
    /// Takes the raw logit (before sigmoid) and returns a calibrated probability.
    /// This preserves ranking (AUC unchanged) while improving calibration (Brier score).
    ///
    /// Formula: P_calibrated = sigmoid(A * logit_raw + B)
    pub fn calibrate_from_logit(&self, logit_raw: f64) -> f64 {
        sigmoid(self.a * logit_raw + self.b)
    }

    /// Calibrate a raw probability (after sigmoid).
    ///
    /// Converts probability back to logit, applies Platt transform, returns calibrated probability.
    /// Use `calibrate_from_logit` when you have the raw logit — it avoids the logit roundtrip.
    pub fn calibrate(&self, raw_probability: f64) -> f64 {
        let logit_raw = logit(raw_probability);
        self.calibrate_from_logit(logit_raw)
    }
}

/// Logistic sigmoid function.
fn sigmoid(x: f64) -> f64 {
    1.0 / (1.0 + (-x).exp())
}

/// Logit (inverse sigmoid). Clamps input to avoid infinities.
fn logit(p: f64) -> f64 {
    let p = p.clamp(1e-15, 1.0 - 1e-15);
    (p / (1.0 - p)).ln()
}

/// Calibration method identifier for CalculationTrace.
pub const CALIBRATION_METHOD: &str = "platt_scaling_v1_n2995";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sigmoid_logit_roundtrip() {
        for p in [0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99] {
            let roundtrip = sigmoid(logit(p));
            assert!(
                (roundtrip - p).abs() < 1e-10,
                "roundtrip failed for p={p}: got {roundtrip}"
            );
        }
    }

    #[test]
    fn test_calibration_reduces_high_probabilities() {
        let cal = PlattCalibration::default();
        // Raw M1 is overconfident: high raw probabilities should be reduced
        // With A < 1 and B < 0, calibration compresses and shifts down
        let raw_logit = 5.0; // raw P ~= 0.993
        let calibrated = cal.calibrate_from_logit(raw_logit);
        let raw_p = sigmoid(raw_logit);
        assert!(
            calibrated < raw_p,
            "calibrated ({calibrated}) should be less than raw ({raw_p}) for high logit"
        );
    }

    #[test]
    fn test_calibration_preserves_ordering() {
        let cal = PlattCalibration::default();
        // Platt scaling is monotonic — ordering must be preserved
        let logits = [-3.0, -1.0, 0.0, 1.0, 3.0, 5.0, 8.0];
        let calibrated: Vec<f64> = logits.iter().map(|&l| cal.calibrate_from_logit(l)).collect();
        for i in 1..calibrated.len() {
            assert!(
                calibrated[i] >= calibrated[i - 1],
                "ordering violated at index {i}: {} >= {}",
                calibrated[i - 1],
                calibrated[i]
            );
        }
    }

    #[test]
    fn test_calibration_bounds() {
        let cal = PlattCalibration::default();
        // Output must always be in [0, 1]
        for logit in [-100.0, -10.0, 0.0, 10.0, 100.0] {
            let p = cal.calibrate_from_logit(logit);
            assert!(
                (0.0..=1.0).contains(&p),
                "out of bounds for logit={logit}: {p}"
            );
        }
        // Moderate inputs should be strictly in (0, 1)
        for logit in [-10.0, 0.0, 10.0] {
            let p = cal.calibrate_from_logit(logit);
            assert!(p > 0.0 && p < 1.0, "not strictly interior for logit={logit}: {p}");
        }
    }

    #[test]
    fn test_default_coefficients_match_python() {
        let cal = PlattCalibration::default();
        assert!((cal.a - 0.398962).abs() < 1e-5);
        assert!((cal.b - (-2.129460)).abs() < 1e-5);
    }

    #[test]
    fn test_calibrate_from_probability() {
        let cal = PlattCalibration::default();
        // calibrate(sigmoid(logit)) should equal calibrate_from_logit(logit)
        let logit = 3.0;
        let from_logit = cal.calibrate_from_logit(logit);
        let from_prob = cal.calibrate(sigmoid(logit));
        assert!(
            (from_logit - from_prob).abs() < 1e-10,
            "calibrate({}) vs calibrate_from_logit: {} vs {}",
            sigmoid(logit),
            from_prob,
            from_logit
        );
    }

    #[test]
    fn test_known_calibration_values() {
        // Verify against Python: sigmoid(0.398962 * logit + (-2.129460))
        let cal = PlattCalibration::default();

        // logit = 0 -> sigmoid(0.398962 * 0 + (-2.129460)) = sigmoid(-2.12946)
        let p0 = cal.calibrate_from_logit(0.0);
        let expected = 1.0 / (1.0 + (2.129460_f64).exp());
        assert!(
            (p0 - expected).abs() < 1e-6,
            "logit=0: expected {expected}, got {p0}"
        );

        // logit = 5.0 (raw P ~0.993)
        let p5 = cal.calibrate_from_logit(5.0);
        let expected5 = 1.0 / (1.0 + (-(0.398962 * 5.0 - 2.129460_f64)).exp());
        assert!(
            (p5 - expected5).abs() < 1e-6,
            "logit=5: expected {expected5}, got {p5}"
        );
    }
}
