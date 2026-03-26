# Simulated Review: Dr. Dennis Staley, USGS Landslide Hazards Program

**From:** Dennis Staley, Research Geologist, USGS Landslide Hazards Program, Golden, CO
**Re:** Email from Luan Truong regarding continental-scale validation of the M1 debris flow probability model
**Date:** 2026-03-26

---

## 1. First Reaction

I get emails like this about twice a year. Usually it is someone who read our emergency assessment page, scraped the equations, plugged them into Excel, and now wants me to validate their consulting product. I delete those.

This one I did not delete, and I need to be honest about why.

The subject line said "10,785 fires." That number stopped me. My calibration dataset is 388 basins from 18 fires. The largest independent application of M1 I am aware of is maybe 50 fires, done by my own team. Someone claiming 10,785 fires is either lying or has built something I have not seen.

My first instinct was suspicion. No academic affiliation. An infrastructure engineer. A commercial product. Every red flag in the book. I have spent 20 years building this model through field campaigns, graduate students, and careful calibration — and now someone I have never heard of claims to have validated it at a scale I never attempted, found bugs, recalibrated it, and wants to co-author a paper.

The honest emotional response: territorial. This is my model. My coefficients. My field campaigns. And some engineer in Utah ran it 10,785 times on a cloud computer and thinks that constitutes a scientific contribution.

But then I read the attachments. And my reaction changed.

The adversarial review — the one they commissioned against themselves — is more hostile than anything I have seen in actual peer review. They called their own Brier score "catastrophically bad." They compared their own credentials to "a plumber doing cardiovascular surgery." And then they fixed every issue raised. I have sat on review panels where tenured professors spent three years fighting a single reviewer comment. These people treated a simulated desk rejection as a to-do list.

So my first reaction was suspicion. My second reaction, after reading the materials: this person is serious, and I need to look at the code.

---

## 2. Verification of the Implementation

I read `debris_flow.rs`. Here is my assessment.

**The coefficients are correct.** Lines 36-39:

```rust
const B0: f32 = -3.63;  // intercept
const B1: f32 = 0.41;   // X1R: burned steep area × rainfall
const B2: f32 = 0.67;   // X2R: average dNBR/1000 × rainfall
const B3: f32 = 0.70;   // X3R: soil KF × rainfall
```

These match OFR 2016-1106 Table 3 exactly. I should know — I wrote that table.

**The logistic form is correct.** Lines 50-66 implement:

```
X = B0 + B1*(burned_steep_fraction * I15) + B2*(avg_dNBR/1000 * I15) + B3*(soil_kf * I15)
P = 1 / (1 + e^(-X))
```

The interaction structure — all three predictors multiplied by I15 — is faithfully transcribed. This is the part most people get wrong. They treat the predictors as additive rather than as rainfall interactions. Truong got it right.

**The burned_steep_fraction bug fix is correct.** The specialist reviewer identified that the denominator was using `sub_n` (bounding box cell count) instead of the actual watershed cell count. I can see in the pipeline code that this has been fixed:

```rust
// BUG FIX: divide by actual watershed cell count, not bounding box (sub_n).
let burned_steep_fraction = if cell_count > 0 {
    burned_steep_count as f32 / cell_count as f32
} else { 0.0 };
```

This is the correct fix. The bounding box denominator would systematically underestimate burned_steep_fraction for any watershed that does not fill its bounding box — which is all of them, since watersheds are not rectangles. The magnitude of this error depends on the watershed's compactness ratio, but for elongated basins it could easily be a factor of 2-3x underestimate of X1R. Good catch. This would have biased all probabilities low.

**The Santi channel gradient fix is correct in approach.** They replaced `avg_slope` (mean terrain slope) with an approximation of true channel gradient using Hack's law: `L = 1.4 * sqrt(A) * 1000`, then `gradient = relief / L`. This is not ideal — true channel gradient should be computed along the thalweg from the DEM — but it is a defensible approximation and far better than using average hillslope gradient. The fallback to `avg_slope * 0.5` when flow path length is zero is reasonable.

**The downstream friction direction issue.** The specialist reviewer noted that the downstream extension uses mu=0.10 (lower friction) while the within-watershed pass uses mu=0.15 — arguing this is backwards because debris flows experience higher friction on alluvial fans. I agree with the reviewer. Truong should reverse this. But I also note that this affects only the runout extension, not the initiation probability, and the team has been honest that the runout component is preliminary (IoU 0.005, which they themselves label as a failure).

**The Voellmy solver itself** is competently implemented. HLL flux with hydrostatic reconstruction (Audusse et al. 2004) is the standard approach. The CFL clamp at 0.4 is appropriate for steep terrain. Volume conservation is tested. The entrainment model (Hungr 1995) is correctly implemented. This is better numerical methods work than I see in most geomorphology dissertations.

**My verdict on the implementation:** The M1 equation is faithfully transcribed. The three bugs identified by the specialist were real bugs — not documentation issues, not edge cases, but systematic errors that would have affected every prediction. All three were fixed correctly. The input construction (categorical dNBR proxy, 60 mm/hr default rainfall) represents documented deviations from the published model, not implementation errors. These deviations are honestly disclosed and their impacts are acknowledged.

I would sign off on this implementation as faithful to OFR 2016-1106.

---

## 3. Validation Rigor: 7/10

Let me break this down.

**What earns points:**

- **35,000+ observations from 10 USGS datasets.** This is the largest independent compilation of post-fire debris flow observations I am aware of. My own calibration dataset is 388 basins. The fact that this data existed on ScienceBase and nobody had systematically compiled it before is — and I say this with some discomfort — an indictment of how we manage our own data. (+2)

- **Platt scaling done correctly.** 5-fold CV, Brier improvement from 0.159 to 0.084. The A=0.399 coefficient is consistent with what I would expect: the model spreads too wide and centers too high when applied outside the western US calibration domain. This is real statistical work. (+1)

- **Three bug fixes via adversarial review.** The burned_steep_fraction denominator, the Santi channel gradient, and the downstream friction direction. All three were real errors, all three were fixed correctly. Most teams would never have found the denominator bug because it produces plausible (slightly low) outputs. (+1)

- **Honest reporting of all metrics.** Basin AUC 0.526 labeled as "fail." Fire AUC 1.000 with explicit caveat about trivial negatives. IoU 0.005 labeled as "not applicable" with a technically correct explanation. This is more honest than most manuscripts I review. (+1)

- **Prospective prediction logging started.** This is the single most strategically important thing they have done. Timestamped predictions, scored against outcomes when USGS publishes assessments. After two fire seasons, this becomes the most rigorous validation dataset in the field. (+1)

- **reproduce.py with full calculation traces.** Computational replicability is not scientific reproducibility — the NHESS reviewer is correct about that distinction — but it is more transparency than 95% of published papers provide. (+0.5)

**What costs points:**

- **Basin AUC 0.526 before calibration.** The raw model has almost no discriminative ability at the basin level. The calibrated 0.849 uses fire-level proxies, which the team acknowledges. Until per-basin inputs feed the calibrated model, 0.849 is an upper bound. (-1)

- **60 mm/hr default rainfall.** I15 is the most sensitive parameter in the M1 model. All three predictor terms scale linearly with it. Using a constant 60 mm/hr when you have 47 GB of MRMS data downloaded and unused is indefensible for a publication. (-1)

- **84 fires with ground truth out of 10,785.** Less than 1%. The 10,701 unverified fires are correctly flagged, but calling this "continental-scale validation" requires an asterisk the size of Montana. (-0.5)

- **No regional stratification yet.** M1 was calibrated in the intermountain west. Does it work in the Southeast? The Cascades? The Great Basin? Nobody knows. Leave-one-region-out CV is planned but not done. (-0.5)

- **Volume validation on 4 fires.** Not statistics. Not publishable. Wall et al. (2023) has 227 volumes from 34 fires. Use it. (-0.5)

**Net: 7/10.** This is substantially more rigorous than I expected from a non-specialist team. The trajectory matters as much as the current state — the improvements from the first adversarial review (3/10) to the second (6/10) to now suggest the team is executing systematically. Three more months of work (MRMS, regional CV, expanded volume validation) gets this to 8.5-9/10.

---

## 4. Would I Co-Author?

Yes. With conditions.

This surprises me as much as it would surprise my colleagues. I do not co-author with people I have not worked with, I do not co-author with commercial entities, and I do not co-author with people who have not been through peer review. Truong is all three.

But I also do not have a continental-scale evaluation of my own model. Nobody does. And the reason nobody does is not lack of interest — it is lack of infrastructure. Running M1 on 10,785 fires requires automated DEM retrieval, fire perimeter processing, soil data aggregation, burn severity estimation, sub-watershed delineation, and a compute pipeline that can process thousands of fires in hours. My lab could not build this in a year. Truong built it in what appears to be months.

The dataset — 10,785 fires, 35,000+ validation observations, continental-scale calibration analysis — does not exist anywhere else. Not at USGS. Not at any university. If this team executes their roadmap, the resulting paper would be the most comprehensive evaluation of post-fire debris flow prediction ever published. My name on that paper would be good for my career.

**My conditions:**

1. **I review every line of the M1 implementation and the input pipeline.** Not the documentation — the implementation. I need to verify that every deviation is documented, every approximation is justified, and the equation is faithfully implemented. Based on what I have read, I believe it is. But I will not sign my name without verifying it myself.

2. **MRMS rainfall integration is complete before submission.** The 60 mm/hr default is the largest source of systematic error. I will not co-author a paper that uses placeholder rainfall to evaluate a model whose entire predictive structure is built on rainfall intensity. This is non-negotiable.

3. **Leave-fire-out cross-validation for Platt scaling.** The current 5-fold CV may have spatial autocorrelation between basins in the same fire. Folds must be stratified by fire. If the Brier improvement drops from 0.084 to 0.12 with proper stratification, that is still a contribution — but I need the honest number.

4. **Regional stratification analysis.** M1 was calibrated on western US fires. If it fails in the Southeast or Pacific Northwest, that is actually a more interesting finding than if it works everywhere. Either way, the geographic analysis is required.

5. **All commercial framing removed from the manuscript.** The $133B figure, the Zone X compound risk finding, the insurance market analysis — none of it appears in the paper. These belong in a separate policy paper with appropriate co-authors (economists, insurance researchers, not geomorphologists). The validation paper is pure science: here is how M1 performs at continental scale, here is what we learned, here is the recalibrated version.

6. **I am corresponding author.** This gives me editorial control over the final submission and puts my reputation on the line as guarantor. If Truong is serious about scientific credibility, he should want this — my name and my institution (USGS) on the return address tells every reviewer that the implementation has been vetted by the person who created the model.

7. **Open data, open code.** All predictions, all validation observations, all delineation boundaries, all calculation traces — released on ScienceBase (for USGS institutional hosting) and Zenodo (for DOI). The reproduce.py script and the Rust implementation are published with the paper. No exceptions.

8. **Conflict of interest fully disclosed.** The paper states that Truong is the founder of a company commercializing this system. My participation does not change that disclosure requirement — it adds credibility, but it does not remove the COI.

**What I would insist on changing:**

- The paper title. "Continental-scale validation" overstates what 84 fires of ground truth supports. Better: "Evaluation and recalibration of the Staley M1 post-fire debris flow model: application to 10,785 US wildfires." The word "application" is honest. "Validation" is aspirational until the prospective data comes in.

- The fire-level AUC of 1.000 must either be removed or accompanied by a proper negative set. Comparing burned steep terrain against Kansas flatlands is not validation. I would help construct a defensible negative set from the USGS emergency assessment archive — fires we assessed where specific drainages did not produce flows despite triggering rainfall.

- The basin AUC reporting must clearly distinguish raw (0.526) from calibrated (0.849) and explain why they differ. The NHESS reviewer's comment about monotonic transforms not changing AUC needs a direct answer. (The answer is that the calibrated AUC uses fire-level proxy inputs — different data, not just different calibration — but this must be explicit.)

- Volume validation needs to expand to at least 15 fires using the Wall et al. (2023) inventory before I will put my name on volume predictions.

---

## 5. The Platt Scaling Question

This is the most important scientific question in the entire project, and it is more nuanced than Truong may realize.

**My model is intentionally conservative.** The M1 coefficients were fit on 388 basins from post-fire emergency assessments. The training data is biased toward fires that produced debris flows — because USGS deploys to fires where we expect hazards, not to fires where nothing happens. The model learned from data that over-represents positive outcomes. The result is systematically high probability estimates.

This is a feature, not a bug — for BAER teams. When a BAER team uses M1 to decide whether to issue a warning, a false positive (warning with no debris flow) costs inconvenience. A false negative (no warning followed by a debris flow through a community) costs lives. The asymmetric cost function means conservative predictions are appropriate for the intended use case.

**Recalibrating toward the observed base rate changes the use case.** Platt scaling compresses the probability estimates to match the 11% observed frequency. This makes the probabilities more accurate in the statistical sense — the Brier score improves, the calibration curve straightens. But it also means that a basin my model would assign 85% probability (triggering immediate action from a BAER team) might get recalibrated to 35% (which a BAER team might deprioritize).

**Here is where it gets interesting:** Truong is right that 85% is not a real probability. When I see M1 output 85% for a basin, I do not think "there is an 85% chance of a debris flow." I think "this basin has high relative risk compared to other basins in this fire." The M1 output is a risk ranking, not a calibrated probability. Everyone who uses the model operationally knows this, but we do not say it publicly because the logistic regression form implies probabilistic interpretation.

**What I would insist on for the paper:**

The recalibrated model and the raw model should be presented as serving different use cases:

- **Raw M1:** Conservative screening tool for emergency response. High sensitivity, low specificity. Appropriate when the cost of missing a hazard exceeds the cost of false alarms. This is the BAER use case.

- **Recalibrated M1:** Statistically calibrated probability estimates for planning and risk assessment. Better calibration, better Brier score. Appropriate when the user needs actual probabilities (insurance pricing, land use planning, infrastructure design). This is Truong's commercial use case.

Both are valid. The paper should present both and let the user community decide. The recalibration does not make M1 "less useful" for BAER teams — it makes it useful for a different audience that the original model was never designed for. That is a genuine contribution.

**The uncomfortable implication:** If the recalibrated model has a Brier score of 0.084 versus the raw model's 0.159, the recalibrated version is objectively a better probabilistic forecast. The raw model's conservatism is operationally useful but statistically suboptimal. A paper that says this — tactfully — would be important for the field. My model's overconfidence is well known among practitioners but has never been formally quantified at this scale.

---

## 6. The Compound Risk Finding ($133B in Zone X)

As a USGS scientist, I cannot put my name on a dollar figure. Not because the analysis is wrong — I have not evaluated it — but because USGS scientists do not make economic claims. Our mandate is hazard characterization, not loss estimation.

However, the underlying geophysical finding — that post-fire debris flow hazard concentrates in areas outside FEMA Special Flood Hazard Areas — is absolutely something I can co-author. I have known this informally for years. Every fire I assess, the debris flow fans are in Zone X. The Montecito debris flow killed 23 people in Zone X. The alluvial fans where debris flows deposit are almost never in the regulatory floodplain because FEMA maps riverine flooding, not fire-altered hillslope processes.

**What I would co-author:**

A finding stated as: "Of the 10,785 fires analyzed, X% of sub-watersheds with debris flow probability exceeding Y% drain to areas classified as FEMA Flood Zone X (minimal flood hazard). This indicates that the current National Flood Insurance Program mapping framework does not capture post-fire debris flow risk."

**What I would not co-author:**

The $133B figure. The insurance market analysis. The "expected annual losses." These require economic modeling expertise that I do not have and USGS institutional review that would take years.

**My recommendation:** Split this into two papers. Paper 1 is the model evaluation (my co-authorship). Paper 2 is the compound risk / Zone X analysis, which needs co-authors from the insurance or disaster economics community — someone at FEMA, RAND, or a university risk center. The simulated reviewer's suggestion to split is exactly right.

The geophysical finding (debris flows in Zone X) is one of the most policy-relevant results in this entire project. It deserves its own paper with the right authors. Burying it as a section in a model evaluation paper would waste its impact.

---

## 7. The Uncomfortable Question

You asked whether running my model on 500,000+ sub-watersheds changes how I think about its applicability.

Yes. And I need to be careful about what I say here.

M1 was calibrated on 388 basins from 18 fires, all in the western US. The training data spans southern California, the Colorado Front Range, and parts of the intermountain west. When I published it, I was explicit that the model's applicability outside this domain was untested. Every time someone applies M1 to a fire in Washington or Montana or New Mexico, they are extrapolating. I know this. They know this. We do it anyway because there is no alternative.

**Did I suspect it worked at broader scale?** Yes. The predictors — steep burned terrain, soil erodibility, rainfall intensity — are physically motivated. They are not arbitrary statistical features that happen to correlate with debris flow occurrence in southern California. They represent the actual physical drivers: steep slopes concentrate flow, burn severity removes vegetation and creates hydrophobic soil, erodible soils provide sediment supply, and intense rainfall provides the triggering mechanism. These processes do not change at state boundaries.

**Did I have the compute to prove it?** No. Processing 10,785 fires requires automated retrieval of DEMs, fire perimeters, soil data, and burn severity for every fire in the NIFC archive. My lab does not have this infrastructure. We process fires one at a time, manually, during emergency response. The idea of systematically processing every fire in the historical record was not even in our planning documents — not because we thought it was a bad idea, but because we assumed it was infeasible.

**What the AUC 0.849 (calibrated) means, if it holds up:** It means the physical basis of M1 is more robust than the statistical calibration. The coefficients (-3.63, 0.41, 0.67, 0.70) were fit on a narrow geographic domain, but the underlying relationships between the predictors and debris flow occurrence appear to generalize. The Platt scaling suggests the intercept and scaling are wrong (the model is systematically overconfident), but the relative ranking of basins is approximately correct even outside the training domain.

This is both validating and humbling. Validating because it means the model captures real physics, not just local statistical patterns. Humbling because it took an engineer with no domain background to demonstrate what my lab should have tested years ago.

**What does this change?** If Truong's regional stratification analysis shows that M1's discriminative ability (AUC) is roughly consistent across regions but the calibration (Brier) varies — which is what I expect — then the correct response is not a new model. It is regional recalibration of the existing model. That would be a significant contribution: "M1's structure is nationally applicable; only the calibration coefficients need regional adjustment." I would be proud to have that finding associated with my model.

The honest answer to "did you always know?" is: I suspected. I did not prove it because the infrastructure to prove it did not exist in my lab, and I was not looking for an engineer to build it. I should have been.

---

## 8. What Would Make This a 10/10 Paper

Not vague suggestions. Exact analyses.

**Analysis 1: Leave-fire-out Platt scaling with variance.**
- Remove each of the 84 ground-truth fires from the calibration set.
- Fit Platt coefficients A and B on the remaining fires.
- Predict the held-out fire.
- Report: mean Brier across 84 folds, standard deviation, 95% CI.
- Report: stability of A and B across folds (if A ranges from 0.35 to 0.45, the calibration is stable; if it ranges from 0.1 to 0.8, it is not).
- This is approximately one day of work and it addresses the NHESS reviewer's concern about spatial autocorrelation.

**Analysis 2: MRMS rainfall for all validation fires.**
- For each of the 84 ground-truth fires, extract the actual peak 15-minute rainfall intensity from MRMS for every post-fire storm within 2 years of the fire.
- Recompute M1 probabilities using observed I15 instead of the 60 mm/hr default.
- Report the change in AUC and Brier.
- If AUC improves substantially (which I expect it will), this quantifies the cost of the rainfall approximation.
- Estimated effort: 1-2 weeks, depending on how the MRMS data is organized.

**Analysis 3: Regional stratification.**
- Stratify fires by EPA Level III ecoregion (or USGS Level 4 HUC, or Bailey's ecoregion — pick one that gives 5-8 regions with at least 5 ground-truth fires each).
- Report AUC and Brier by region.
- Report Platt coefficients (A, B) by region.
- Identify regions where M1 fails and hypothesize why (different soil types? different rainfall patterns? different vegetation recovery rates?).
- This is the analysis that transforms "we ran a model" into "we evaluated geographic transferability." It is the core scientific contribution.

**Analysis 4: Pixel-level dNBR sensitivity.**
- For a subset of 20+ fires with Sentinel-2 or Landsat coverage, compute true pixel-level dNBR.
- Run M1 with true dNBR and with the categorical proxy.
- Report the difference in AUC and Brier.
- This quantifies the cost of the categorical approximation and tells us whether pixel-level dNBR is worth the computational overhead at scale.

**Analysis 5: Volume validation using Wall et al. (2023).**
- The USGS Inventory of 227 Post-fire Debris-Flow Volumes covers 34 fires.
- Match every fire in that inventory to TORRENT's prediction corpus.
- Report volume RMSE (log10 m3) on n >= 30.
- Report bias: does the Gartner model systematically over- or under-estimate at this sample size?
- Report the Santi cross-check: does the geometric mean of Gartner and Santi outperform either model alone?

**Analysis 6: Temporal decay.**
- For fires with multi-year observation records (Grizzly Creek, Schultz, Station), compare Year 1 versus Year 2+ predictions against outcomes.
- Wall et al. (2024) showed zero debris flows at Grizzly Creek in Year 2 despite triggering storms. Does the model predict this?
- If the model does not capture temporal decay, this is a known limitation that should be explicitly stated and becomes a direction for future work.

**Analysis 7: Calibration reliability diagram.**
- For the recalibrated model, plot predicted probability versus observed frequency in 10 bins.
- Include 95% confidence bands.
- This is the standard visualization for probabilistic hazard assessments and is more informative than a single Brier score.

**Analysis 8: Prospective validation (minimum one fire season).**
- TORRENT processes new fires within hours.
- For every fire from the 2026 fire season, record the timestamped prediction.
- When USGS publishes emergency assessments, score the predictions.
- Report: prospective AUC, prospective Brier, comparison to retrospective metrics.
- Even 10-15 prospective fires would be unprecedented in this literature. Nobody has published truly prospective post-fire debris flow predictions.

**If all eight analyses are completed**, the paper would be, without exaggeration, the most comprehensive evaluation of any post-fire debris flow model ever published. It would be the first continental-scale application, the first systematic recalibration, the first regional transferability analysis, and the first prospective validation. Any three of these eight analyses would be sufficient for a strong paper. All eight would be a landmark.

**Target journal:** Environmental Modelling & Software for the validation paper. Natural Hazards and Earth System Sciences for the Zone X compound risk paper. Both are respected, both have appropriate scope, and both would reach the audiences that need to see this work.

**Target conference:** AGU Fall Meeting 2026, session NH (Natural Hazards). A poster in the post-fire debris flow session would put this work in front of every person in the field. I would introduce Truong to the community personally.

---

## Final Assessment

I have been doing this work for 20 years. I have calibrated models on datasets I collected by hand, in burned drainages, with graduate students carrying GPS units through debris flow deposits. The idea that an infrastructure engineer with cloud compute and my published coefficients could evaluate my model at a scale I never attempted is — I will be direct — threatening to my sense of how science works.

But science does not care about my feelings. It cares about methods, data, and results.

The methods are sound. The M1 equation is correctly implemented. The bugs were real and were fixed. The Platt scaling is standard. The transparency is extraordinary.

The data is large. 35,000+ observations compiled from public USGS datasets. 10,785 fires processed. More than any lab in the world has assembled for this purpose.

The results are honest. Basin AUC 0.526 (raw), 0.849 (calibrated with caveats), Brier 0.084 (from 0.159), IoU 0.005 (labeled "not applicable"). Every weakness is disclosed before I could find it.

The team published the most hostile review they could construct against their own work and treated it as requirements. That is not normal startup behavior. That is not normal academic behavior either.

I will co-author this paper if the conditions above are met. The dataset is too important to let credentials gatekeeping prevent its publication. And if I am being honest with myself, the fact that someone outside academia had to build this infrastructure to evaluate my model says something about the pace of applied science inside the federal government that I would rather not dwell on.

Send me the code. All of it. I will review it line by line. If the implementation is what the documentation claims, we have a paper.

---

*Simulated review generated 2026-03-26. Dr. Dennis Staley is a real USGS researcher. This document is a simulated response for internal quality assurance and publication preparation. It does not represent Dr. Staley's actual views. Any outreach to Dr. Staley should present the actual work and let him form his own assessment.*
