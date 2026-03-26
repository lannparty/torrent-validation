# Peer Review: Specialist (Debris Flow Mechanics)

**Manuscript:** "Continental-scale validation of post-fire debris flow predictions: 10,785 fires, 500,000 sub-watersheds, and empirical probability recalibration"

**Reviewer:** Anonymous Reviewer #2 (debris flow mechanics, Staley model specialist)

**Confidence:** High. I have applied the Staley M1 model operationally on 40+ fires and published on its calibration properties. I am intimately familiar with OFR 2016-1106 Table 3, the Gartner volume model, and USGS operational deployment procedures.

---

## Summary

The authors apply the Staley et al. (2016) M1 likelihood model and Gartner et al. (2014) volume regression to 10,785 NIFC fire perimeters, generating debris flow initiation probabilities and volume estimates for ~500,000 delineated sub-watersheds. They identify systematic overconfidence in the raw M1 outputs and propose Platt scaling recalibration trained on 2,995 USGS binary outcome observations. The system couples initiation probability with a Voellmy runout solver for downstream hazard mapping. The authors frame this as a continental-scale validation, though as I discuss below, the actual validation sample is far smaller than the headline number implies.

The contribution, if the technical issues are resolved, is meaningful: nobody has stress-tested Staley M1 at this scale, and the overconfidence finding aligns with my own unpublished observations from operational deployment.

---

## Major Comments

### M1. Staley M1 coefficients are correct but the input construction is not faithful to the published model

The coefficients (B0=-3.63, B1=0.41, B2=0.67, B3=0.70) in `debris_flow.rs` line 36-39 match OFR 2016-1106 Table 3 exactly. The logistic form and interaction term structure (all three predictors multiplied by I15) are correctly implemented. The `initiation_probability()` function at line 50-67 is a faithful transcription of the equation.

**However, the pipeline feeds this correct equation with degraded inputs:**

(a) **dNBR approximation (the pipeline implementation).** The M1 model was calibrated on continuous dNBR values from Landsat imagery. The pipeline maps categorical severity factors to fixed dNBR proxies (high=500, moderate=300, low=150, unburned=0) and averages them. This is not what Staley M1 expects. The X2R term is `(avg_dNBR/1000) * I15`. With categorical proxies, you lose the within-category variance that the logistic regression was trained on. A basin with heterogeneous high-severity burn (dNBR ranging 400-800) behaves differently from one with uniform dNBR=500, even though your proxy treats them identically.

The authors acknowledge this and call it "conservative (under-predicts X2R)." That characterization is wrong in general. For fires with large unburned areas within the perimeter (common for large fires), averaging over all cells including unburned=0 will indeed underestimate. But for small, intensely burned fires, the categorical mapping may overestimate if the true mean dNBR is below your proxy values. The bias direction is fire-dependent, not consistently conservative.

(b) **Burned steep fraction computation (the pipeline implementation).** The slope threshold of tan(23 deg) = 0.42 is correct per the published model. However, the fraction is computed over `sub_n` (total sub-grid cells including padding from the bounding box extraction), not over the actual watershed cell count. If the bounding box contains significant non-watershed area, the denominator is inflated, systematically underestimating `burned_steep_fraction` and thus X1R. This is a bug, not a documented deviation.

(c) **Rainfall input.** The adversarial review acknowledges the 60 mm/hr default. Having run M1 operationally, I can confirm this is the single largest error source. The M1 model is extraordinarily sensitive to I15 because all three predictor terms scale linearly with it. A factor-of-2 error in I15 produces a factor-of-2 error in every X term simultaneously, which can shift the logit by 3-5 units. The authors' own test case (line 477-485) shows they understand this but the fallback path is still present.

**Required action:** (a) Quantify the dNBR proxy error by running the 17 validation fires with true Landsat/Sentinel-2 dNBR and comparing. (b) Fix the burned_steep_fraction denominator to use watershed cell count, not bounding box cell count. (c) Remove or prominently flag results computed with the 60 mm/hr default.

### M2. Gartner volume equation: correct transcription, problematic modifications

The Gartner et al. (2014) equation at the pipeline-678 is correctly transcribed:

```
ln(V) = 4.22 + 0.39*sqrt(i15) + 0.36*ln(Bmh) + 0.13*sqrt(R)
```

where i15 is peak 15-min intensity in mm/hr, Bmh is burned area at moderate/high severity in km^2, and R is relief in meters. This matches the published equation.

**However, two modifications require scrutiny:**

(a) **The area-scaled volume clamp (line 696).** Capping at 20,000 m^3/km^2 with a hard ceiling of 200,000 m^3 is physically reasonable as an engineering safeguard, but it is scientifically problematic because you are then reporting a "Gartner volume" that is not the Gartner volume. The Wall et al. (2024) citation for systematic overestimation is appropriate, but the correct response is to acknowledge the limitation of the Gartner model at scale, not to silently clamp it and still call the output "Gartner." Every clamped result should carry a flag in the output indicating that the published model was overridden.

The authors do trace this in their `CalculationTrace` (line 823-829), which is good practice. But the downstream hazard mapping uses the clamped volume as if it were a model prediction rather than an engineering override.

(b) **The Gartner-Santi geometric mean (lines 781-800).** Using the geometric mean of two independent volume estimates when they disagree by >10x is reasonable from a forecast combination perspective (the Clemen 1989 citation is appropriate). However, the Santi et al. (2008) model was calibrated on a different dataset with different basin characteristics than Gartner. The two models are not estimating the same quantity with independent errors -- they have different systematic biases. Taking the geometric mean assumes the errors are symmetric in log-space around the true value, which is unverified.

More importantly: the Santi model (line 1020-1024) uses `channel_gradient` as input, but the pipeline passes `avg_slope` (the average terrain slope of the sub-watershed). Channel gradient and basin-average slope are different quantities. Channel gradient should be computed along the thalweg, not averaged over the hillslopes. This is a systematic input error that biases Santi volumes.

**Required action:** (a) Clearly label clamped volumes as "engineering-adjusted" in all outputs. (b) Either compute true channel gradient for the Santi model or acknowledge that you are using a proxy. (c) Report unclamped Gartner volumes alongside clamped values so the reader can assess the impact.

### M3. The Platt scaling is methodologically appropriate but the reported improvement needs verification

The Platt scaling implementation in `calibration.rs` is technically correct. The sigmoid(A*logit + B) form is the standard Platt (1999) transform. The coefficients (A=0.399, B=-2.129) produce the expected behavior: compression of overconfident predictions toward lower values while preserving monotonicity (AUC invariant).

**Three concerns:**

(a) **The training/test overlap problem.** The adversarial review (Section 2) flags this correctly. If the same 2,995 observations were used to fit A and B and to evaluate the calibrated Brier score, the improvement is overstated. The code comments reference "5-fold cross-validation" but the compiled-in coefficients are single values, implying they were fit on the full dataset. Proper reporting requires: (i) the mean Brier score across held-out folds, (ii) the variance across folds, and (iii) the coefficients fit on each fold to demonstrate stability.

(b) **A < 1 implies the raw model has insufficient spread, not overconfidence.** With A=0.399, the Platt transform compresses the logit range by 60%. This means the raw M1 logits vary more than they should to match observed outcome frequencies. Combined with B=-2.129 (a large negative intercept shift), this tells us the raw model both spreads too wide and centers too high. This is consistent with applying a model outside its calibration domain (the western US training set has different base rates than the national dataset). The authors should discuss what A < 1 implies about model transferability.

(c) **The Brier scores reported in comments (raw: 0.1590, calibrated: 0.0837) differ from the adversarial review (raw: -6.940).** The adversarial review uses Brier Skill Score (relative to climatology), while the code comments use raw Brier Score. These are different metrics. The paper must use consistent notation and clearly define which Brier metric is reported.

**Required action:** (a) Report 5-fold CV results with variance. (b) Discuss what A=0.399 means for model transferability. (c) Standardize Brier metric notation throughout.

### M4. The fire-level AUC of 1.000 is meaningless as reported

The adversarial review identifies this correctly (Section 4). Comparing fires that produced debris flows (all on steep, burned terrain) against flat-terrain controls is not a validation of the M1 model -- it is a validation of topographic screening. Any model that includes slope as a predictor will achieve AUC 1.000 on this comparison.

A meaningful fire-level metric requires negative examples from steep, recently burned terrain that did NOT produce debris flows despite receiving rainfall. Such fires exist (the 2020 fire season in Colorado produced several large fires where subsequent rainfall did not trigger debris flows in all burned drainages), but they require careful identification.

**Required action:** Either construct a proper fire-level negative set with comparable terrain characteristics or remove the fire-level AUC from the manuscript. Presenting AUC 1.000 without immediate qualification that the negatives are topographically trivial would be grounds for rejection at any journal I review for.

### M5. The downstream Voellmy extension is physically unjustified as parameterized

The Voellmy runout solver in `debris_flow.rs` is competently implemented. The HLL flux solver with hydrostatic reconstruction (Audusse et al. 2004) is the standard approach. The CFL clamp at 0.4 is conservative and appropriate for steep terrain. Volume conservation without entrainment (tested at line 544-583) is a necessary verification.

**However, the downstream extension pass (the pipeline implementation) has serious problems:**

(a) **Friction parameter selection is ad hoc.** The downstream pass uses mu=0.10 and xi=800 (line 315-320), while the within-watershed pass uses mu=0.15 and xi=500 (line 743-748). The justification ("lower friction for channelized downstream flow") is backwards. Debris flows on alluvial fans experience HIGHER friction as they spread laterally and lose confinement, not lower. The mu reduction from 0.15 to 0.10 would produce longer runout, which makes the product's hazard footprint larger -- a commercial incentive that aligns with the conflict of interest identified in the adversarial review.

The literature on Voellmy parameters for post-fire debris flows (Rickenmann 1999; Hungr & McDougall 2009; Aaron & Hungr 2016) consistently shows mu in the range 0.05-0.20 with typical values of 0.10-0.15 for channelized flows. For unconfined fan deposition, mu should INCREASE to 0.20-0.30 as the flow thins and decelerates. The downstream extension should use higher mu, not lower.

(b) **The 3x3 cell initialization at pour points (lines 276-304) distributes volume uniformly.** Real debris flows arrive at fan apices as concentrated, high-velocity surges, not as uniform depth distributions over 90m x 90m squares. The initialization geometry strongly affects subsequent routing.

(c) **The 600-second simulation time (line 321) is arbitrary.** Post-fire debris flows on alluvial fans can deposit within seconds to minutes depending on fan geometry. A fixed 10-minute window may cut off deposition prematurely on long fans or allow unphysical propagation on short ones. Simulation should run until flow velocity drops below a deposition threshold, not for a fixed duration.

(d) **Erodible depth of 0.005m for the downstream domain (line 259) is unrealistically low.** Alluvial fan surfaces typically have 0.5-2m of entrainable material. However, given the concern about over-predicting hazard extent, a conservative (low) entrainment assumption is defensible.

**Required action:** (a) Reverse the friction parameter relationship: downstream mu >= upstream mu. (b) Justify all Voellmy parameters with literature citations. (c) Replace fixed simulation time with a velocity-based termination criterion. (d) Perform sensitivity analysis on downstream parameters and report the range of outcomes.

---

## Minor Comments

### m1. The slope calculation for the Voellmy friction term (debris_flow.rs line 291-297) uses central differences on raw elevation. On a 10m DEM with meter-scale noise, this can produce noisy slope estimates that cause oscillatory friction forcing. A Gaussian-smoothed elevation field for slope computation would be more stable, though the CFL clamp at 0.4 may compensate.

### m2. The velocity clamp at 20 m/s (debris_flow.rs line 318) is reasonable for channelized debris flows but may be too high for unconfined fan flows. The fastest documented post-fire debris flows are ~15 m/s (Montecito); 20 m/s is more typical of volcanic lahars. Consider reducing to 15 m/s for the post-fire context.

### m3. The entrainment model (Hungr 1995) at line 334-340 is correctly implemented as `E = Es * |u| * dt`, where Es is the entrainment coefficient. However, the model erodes the bed and adds mass to the flow without adjusting flow density. In reality, entrainment of bed material changes the sediment concentration and thus the rheological properties. For a first-order model this simplification is acceptable, but it should be stated.

### m4. The Santi et al. (2008) equation (the pipeline) is cited as:
```
ln(V) = 0.59 + 7.21 * gradient + 0.54 * ln(area_km2)
```
I cannot verify this against my copy of Santi et al. (2008). The Santi volume models I am familiar with use different functional forms depending on the debris flow generation mechanism (runoff vs. landslide). The authors should specify which Santi equation they are implementing and provide the exact table/equation number from the source paper.

### m5. The `burned_steep_fraction` computation (the pipeline) divides by `sub_n` (bounding box area) rather than the actual watershed cell count. As noted in M1(b), this is a bug. It also means that elongated watersheds with large bounding boxes relative to their area will have artificially low X1R terms.

### m6. The `i15_mm_hr` conversion (the pipeline) computes `rainfall_15min_mm * 4.0` to convert 15-minute accumulation to hourly intensity. This is correct only if the 15-minute accumulation represents a constant-intensity period. If the 15-minute value is from Atlas 14 or MRMS (which report accumulation, not intensity), the conversion is correct. If it comes from a non-uniform hyetograph, the peak instantaneous intensity could be higher. The Gartner model expects peak 15-minute intensity in mm/hr, which is the accumulation divided by 0.25 hours -- i.e., multiplied by 4. So the conversion is correct but should be commented to explain the unit transformation.

### m7. The `compute_average_slope` function (called at line 472) is used to derive `avg_slope`, which is then passed to the Santi volume model as `channel_gradient`. These are geometrically different quantities and should not be used interchangeably (see M2(b)).

---

## Recommendation

**Major Revision.**

The Staley M1 implementation is correct at the equation level, which is the most important thing to get right. The Gartner equation is also correctly transcribed. The Platt scaling approach is methodologically sound. The Voellmy solver is competently implemented with appropriate numerical methods.

The problems are in the input construction (categorical dNBR proxy, bounding-box denominator bug, avg_slope vs. channel gradient conflation), the downstream extension parameterization (inverted friction logic, ad hoc parameters), and the validation framing (fire-level AUC 1.000 on trivial negatives).

None of these are fatal. The input issues are engineering fixes. The downstream extension needs a parameter sensitivity analysis and corrected friction assumptions. The validation framing needs honesty about what the metrics actually measure.

The overconfidence finding -- that M1 applied at continental scale produces systematically uncalibrated probabilities requiring recalibration -- is a genuine and useful contribution that aligns with my operational experience. I would like to see this published after the issues above are addressed.

**Confidence:** High. This is my domain. I have run Staley M1 on dozens of fires and I know where it breaks. The implementation is closer to correct than I expected from a non-specialist team, and the deviations are documented with unusual transparency.

---

*Generated 2026-03-26. Anonymous Reviewer #2 (simulated specialist review for internal quality assurance).*
