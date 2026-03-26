# Peer Review: NHESS Manuscript

**Manuscript:** "Continental-scale validation of post-fire debris flow predictions: 10,785 fires, 500,000 sub-watersheds, and empirical probability recalibration"

**Journal:** Natural Hazards and Earth System Sciences (NHESS)

**Reviewer:** Anonymous Reviewer #1

**Date:** 2026-03-26

---

## Summary

The authors apply the Staley et al. (2017) M1 logistic regression model and Gartner et al. (2014) volume model to 10,785 historical US wildfires, generating debris flow initiation probabilities and volume estimates for approximately 500,000 sub-watersheds. They report a fire-level AUC of 1.000 (84 fires), a basin-level calibrated AUC of 0.849 (2,995 observations across 17 fires), and demonstrate that Platt scaling improves the raw probability estimates from a Brier Skill Score of -0.63 to +0.14. The paper's core contribution is the identification of systematic overconfidence in uncalibrated M1 outputs at scale and the proposal of post-hoc recalibration as a remedy.

---

## Major Comments

**1. The title overstates what is validated.**

The manuscript title claims "continental-scale validation" of 10,785 fires. In reality, ground-truth observations exist for 17 fires (2,995 basin-storm observations). The remaining 10,768 fires are predictions without outcomes. Running a model at scale is computation, not validation. The title should be revised to something like: "Evaluation and recalibration of the Staley M1 post-fire debris flow model across 17 fires and 2,995 basin-storm observations, with continental-scale application to 10,785 fires." The 10,785-fire corpus is a legitimate demonstration of scalability and enables population-level analysis (e.g., the FEMA Zone X compound risk finding), but it is not a validation dataset and should not be presented as one.

**2. The fire-level AUC of 1.000 is methodologically unsound.**

The 50 negative fires appear to be selected from flat terrain where debris flows are physically impossible. Distinguishing burned steep mountains from unburned plains is trivially achievable by any model — or by a single slope threshold. A meaningful fire-level AUC requires negative examples from steep, burned terrain that received post-fire rainfall but did not produce debris flows. Such fires exist (e.g., fires where monsoon storms did not materialize in the first two post-fire years) but are admittedly difficult to document because non-events are rarely studied. The authors must either (a) construct a defensible negative fire set from the USGS emergency assessment archive, where some assessed basins had zero observed flows, or (b) remove the fire-level AUC from the abstract and headline metrics entirely. Reporting AUC 1.000 without disclosing the composition of the negative set is misleading.

**3. The raw basin-level AUC of 0.526 must be prominently reported alongside the calibrated AUC of 0.849.**

There is a critical distinction between ranking ability and calibration. The raw AUC of 0.526 indicates the uncalibrated model has almost no ability to discriminate between basins that will and will not produce debris flows — it assigns near-identical high probabilities to most basins within a fire perimeter. The calibrated AUC of 0.849 reflects the improvement from Platt scaling, but if Platt scaling only recalibrates probabilities (a monotonic transformation), it cannot change AUC by definition. Please clarify: does the 0.849 figure come from a different evaluation procedure than the 0.526? Are different observation subsets, thresholds, or groupings involved? This apparent contradiction must be resolved. If the two numbers come from different analyses, the paper needs a clear table showing which metric comes from which dataset with which preprocessing.

**4. The Platt scaling cross-validation protocol is insufficiently described.**

The authors report a Brier improvement from -0.63 to +0.14 using 5-fold CV, but critical details are missing: (a) Are the folds stratified by fire or by basin? If basins from the same fire appear in both training and test folds, spatial autocorrelation will inflate the calibration improvement. Basins within the same fire share terrain, soil, severity, and rainfall — they are not independent observations. Folds must be stratified by fire (leave-k-fires-out) to produce honest out-of-sample estimates. (b) Is the reported Brier score the mean across held-out folds, or is it the in-sample score after fitting on all data? (c) What is the variance across folds? A mean improvement is uninformative without confidence intervals.

**5. Four documented deviations from the published M1 model require sensitivity analysis.**

The authors acknowledge deviating from Staley et al. (2017) in four ways: (i) a default rainfall intensity of 60 mm/hr when fire-specific data is unavailable, (ii) basin-averaged dNBR instead of pixel-level burn severity, (iii) Platt scaling of outputs, and (iv) geographic extrapolation beyond the original western US training domain. Each deviation could independently affect model performance. The paper must include a sensitivity analysis quantifying the impact of each deviation — e.g., performance on the subset of fires where Atlas 14 data is available vs. those using the 60 mm/hr default, and performance within vs. outside the original M1 geographic domain. Without this analysis, the reader cannot distinguish whether the reported metrics reflect M1's intrinsic capability or the authors' modifications.

**6. Volume validation on 4 fires is statistically insufficient.**

A Volume RMSE of 0.376 log10 m3 sounds encouraging relative to the Gartner et al. (2014) benchmark of 0.52, but it is computed from 4 data points. No confidence interval is computable at n=4 with any statistical rigor. The formal validation report reveals that two of the benchmark fires (Grizzly Creek, Schultz) showed 5-10x volume underestimates before reprocessing, and the volume model had a bug producing identical outputs across storm scenarios. The authors must clarify: does the reported RMSE of 0.376 come from the pre-fix or post-fix data? Were the bug-affected runs excluded? Regardless, 4 fires is not a publishable sample for volume validation. The USGS Inventory of 227 Postfire Debris-Flow Volumes (Wall et al. 2023) covers 34 fires — the authors should incorporate all available data or explain why they did not.

**7. The large-fire delineation failure is a critical limitation that undermines the "continental-scale" framing.**

Cameron Peak (209K acres, 3 sub-watersheds) and East Troublesome (194K acres, 6 sub-watersheds) show catastrophic under-delineation. Fires above ~50K acres — which include the most consequential events in the validation set — are systematically underrepresented. The authors' own report rates these as "VERY LOW" confidence. Since large fires disproportionately contribute to debris flow casualties (Montecito, Cameron Peak), a system that fails on large fires has a serious gap in exactly the events that matter most. The paper must quantify what fraction of the 10,785-fire corpus is affected by this limitation and characterize the bias it introduces.

---

## Minor Comments

**1.** The manuscript lists "Voellmy (1955) two-phase rheology" as a model component, and the acceptance criteria include runout IoU >= 0.70, yet the actual IoU is 0.005. The runout component appears to be a placeholder (D8 flow accumulation), not a physics-based solver. All references to runout modeling should be removed from the paper until a proper debris flow routing model is implemented. Including IoU 0.005 in any form would severely damage credibility.

**2.** The 100% high burn severity assumption is applied to all fires as a default. This is acknowledged but its impact is not quantified. How many of the 10,785 fires use this default vs. actual MTBS-derived severity? What is the model's performance on the subset with real severity data vs. the subset using the default? This stratification is essential.

**3.** The SCS Type II hyetograph used to disaggregate 1-hour rainfall into sub-hourly intensity is a significant assumption for the western US, where convective storms often have sharper peaks than the Type II curve assumes. The sensitivity of M1 probability outputs to hyetograph shape should be discussed, even if not formally tested.

**4.** The paper would benefit from a calibration reliability diagram (predicted probability vs. observed frequency, with confidence bands) for both the raw and Platt-scaled outputs. This is standard for probabilistic hazard assessments and is more informative than reporting Brier score alone.

**5.** The claim of reproducibility via reproduce.py should be tempered. The script verifies that stored inputs produce consistent outputs (replicability), not that independent researchers using independent data reach the same conclusions (reproducibility in the scientific sense). The distinction matters and should be stated explicitly.

**6.** Table formatting: the cross-fire summary should include the data source status for each fire (which inputs are real vs. default) so the reader can immediately assess which comparisons are high-confidence.

**7.** The temporal decay limitation (no modeling of vegetation recovery) should be discussed more prominently. Wall et al. (2024) showed zero debris flows in Year 2 at Grizzly Creek despite 8 storms exceeding the M1 threshold. This directly affects how TORRENT's predictions should be interpreted for fires older than one year — which is the majority of the 10,785-fire corpus.

**8.** The authors should disclose the commercial interest. If the lead author is the founder of a company commercializing this system, this must be stated in a conflicts of interest declaration per NHESS policy. The absence of such a declaration would be grounds for editorial concern.

---

## Recommendation

**Major Revision**

The paper addresses a genuine gap in the literature — no one has systematically evaluated the Staley M1 model at this scale, and the identification of systematic overconfidence with a recalibration remedy is a useful contribution. However, the current manuscript has several problems that preclude publication:

1. The headline metrics (fire-level AUC 1.000, basin-level calibrated AUC 0.849) are either methodologically flawed or inadequately explained.
2. The Platt scaling — the paper's central methodological contribution — lacks the cross-validation rigor needed to demonstrate it is not overfitting.
3. The volume validation sample (n=4) is too small to support quantitative claims.
4. The four deviations from M1 are documented but their individual impacts are not quantified.
5. The title and framing conflate computation with validation.

None of these are fatal. The underlying dataset (2,995 basin-storm observations, 17 fires, 10,785-fire prediction corpus) is substantial and the self-critical analysis in the supporting materials suggests the authors understand the weaknesses. A revised manuscript that (a) reframes the 10,785-fire corpus as application rather than validation, (b) implements leave-fire-out cross-validation for Platt scaling, (c) resolves the AUC discrepancy, (d) includes deviation sensitivity analysis, and (e) expands volume validation using the Wall et al. (2023) 227-volume inventory would be a strong candidate for publication.

---

## Confidence

**High.** I review 15-20 papers per year in post-fire geomorphology and am familiar with the Staley M1 model, the Gartner volume model, the Wall et al. (2024) Grizzly Creek study, and the USGS emergency assessment framework. The statistical concerns (calibration, cross-validation, AUC interpretation) are within my area of competence. I have no conflict of interest with the authors.
