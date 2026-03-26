# Adversarial Peer Review — Pass 2: Re-evaluation After Remediation

**Reviewer:** Dr. Richard Hargrove (simulated), Geomorphology, 30 years, h-index 45
**Original recommendation:** REJECT
**Updated recommendation:** MAJOR REVISIONS (conditional)

---

## Context

Three months ago I wrote a 10-point adversarial review calling for desk rejection. The team — a startup founder with no PhD and a business partner with no domain background — took that review, published it internally, and systematically addressed every finding. I have now reviewed the remediated materials.

Let me be clear about what happened here: a non-academic team subjected themselves to the most hostile review I could construct, then treated it as a punch list. That is not normal behavior. Most startups would have buried the review. Most academics would have written a defensive rebuttal letter arguing about framing. These people fixed the math.

---

## 1. Scientific Rigor Rating: 6/10

### What moved the needle (from ~3/10 to 6/10):

**Honest reporting of all three AUC values.** This was my single biggest complaint. The original materials cherry-picked whichever AUC made them look best. Now the validation-metrics.json shows:

- Basin AUC: 0.526 (labeled "fail," "near-random discrimination")
- Fire AUC: 1.000 (labeled "coarser and easier classification task")
- Calibrated basin AUC: 0.849 (with explicit caveat about proxy inputs)

The self-labeling is remarkable. They called their own basin AUC a failure in a customer-facing file. I have reviewed papers from established labs that would never do this.

**Platt scaling done properly.** 5-fold cross-validation, Brier score improved from 0.159 to 0.084. This is real statistical work. The 47% Brier improvement via standard post-processing is exactly what I prescribed.

**35,000+ validation observations from 10 USGS datasets.** Up from 2,995 observations across 17 fires. The validation corpus is now large enough to support subgroup analysis. This is grunt work that most teams never do because it is boring. They did it.

**Market findings separated from validation.** The $133B figure now has an explicit "not validation" disclaimer. It is no longer masquerading as science. This was the easiest fix but also the one most startups would resist, because the conflation was commercially useful.

**IoU changed to "Not Applicable."** They stopped pretending they have a runout model. The resolution-mismatch explanation is honest and technically correct. This took intellectual honesty — 0.005 was embarrassing, and the temptation would have been to remove the metric silently rather than explain why it does not apply.

**Calculation traces with reproduce.py.** Every deviation documented. Every result traceable to inputs. This does not fix the reproducibility gap I identified (computational replicability is not scientific reproducibility), but it is more transparency than 95% of published geomorphology papers provide.

**Prediction logger started.** Prospective walk-forward validation is the correct long-term answer to the selection bias problem. Starting it now means they will have 2-3 fire seasons of timestamped predictions before any serious publication attempt. This is the single most strategically important thing they did.

### What still does not clear the bar:

**Basin AUC 0.526 is still near-random.** The calibrated value of 0.849 uses fire-level averages as proxy inputs — their own note admits this. Until they have true per-basin slope and severity data feeding the calibrated model, the 0.849 is a best-case estimate, not a demonstrated capability. The honest basin-level discrimination is still poor.

**84 fires with ground truth out of 10,785.** Better than 17. Still less than 1%. The 10,701 unverified fires are correctly flagged, but the validation is still thin relative to the claims.

**No regional stratification.** The NEXT_STEPS.md lists "leave-one-region-out CV" and "regional bias detection" as planned work. Until this is done, the geographic transferability of the model is assumed, not tested. Staley M1 was calibrated in the intermountain west. Does it work in the Southeast? The Cascades? Nobody knows yet.

**No MRMS rainfall integration.** The 60 mm/hr default is still the primary rainfall input. 47GB of MRMS data sits downloaded and unused. This is the single largest source of systematic bias in the system.

**No USGS co-author.** The NEXT_STEPS.md mentions reaching out to Dennis Staley. Until that happens, the credentials gap remains. The work is better. The optics have not changed.

**Volume validation on 4-6 fires.** The benchmark_fires array shows 6 fires with some volume data, but only 4 have both predicted and observed volumes. Volume RMSE of 0.376 on n=4 is not statistically meaningful.

---

## 2. Paper Prospect Rating: 4/10

If "Continental-scale validation of post-fire debris flow predictions" were submitted to Environmental Modelling & Software tomorrow, it would receive major revisions at best, likely rejection.

### Why it fails peer review today:

1. **The headline metric is still problematic.** A paper cannot lead with "AUC 0.849" when the asterisk is "using proxy inputs because we do not have per-basin data." Reviewer 2 will read the methods section, find the proxy, and write three paragraphs about why the calibrated AUC is an upper bound. The raw basin AUC of 0.526 is what the model actually achieves on real data.

2. **No sensitivity analysis on the deviations.** I asked for this in the first review. What happens to performance when you replace the 60 mm/hr default with actual MRMS rainfall? What is the AUC with pixel-level dNBR versus basin-averaged? What is the geographic breakdown? These are not optional analyses — they are the core contribution of a model evaluation paper.

3. **No independent co-author.** An editor at EMS will look at the author list, see a startup founder and a PM, and assign the paper to reviewers who will scrutinize it twice as hard. A USGS or university co-author does not just add credibility — it signals to the editor that someone with domain knowledge has reviewed the implementation.

4. **The compound risk finding ($133B, Zone X) needs its own paper.** Mixing model validation with a policy finding about FEMA flood zones dilutes both arguments. The validation paper should be: "We applied Staley M1 to 10,785 fires, found it systematically overconfident, recalibrated it, and here are the metrics." The Zone X paper should be: "Post-fire debris flow risk concentrates in areas excluded from federal flood mapping." Two papers. Two different audiences.

### Why it is not a 1/10:

The underlying work is real. The validation corpus is large. The transparency is extraordinary. The Platt scaling is methodologically sound. The honesty about limitations is publication-quality — most submitted manuscripts have worse limitation sections than TORRENT's internal documentation. If the team executes items 1-4 from the first review's critical path (MRMS, pixel dNBR, regional CV, co-author), this paper publishes.

---

## 3. What Gets Each Rating to 10/10

### Scientific Rigor (6 -> 10):

1. **Integrate MRMS rainfall for all validation fires.** Replace the 60 mm/hr default with observed storm data. Recompute all metrics. This is the single highest-impact improvement. Estimated effort: 1-2 weeks.

2. **Per-basin slope and severity in the calibrated model.** The calibrated AUC of 0.849 uses fire-level proxies. Feed actual per-basin predictors into the Platt-scaled model and report the true calibrated basin AUC. If it drops to 0.72, that is still a contribution — the honest number is what matters.

3. **Leave-one-region-out cross-validation.** Stratify fires by EPA Level II ecoregion (or USGS hydrologic unit). Report AUC by region. Identify where the model fails. This transforms "we applied a model" into "we evaluated geographic transferability."

4. **Expand volume validation to 15+ fires.** Dig through USGS OFRs for every fire with measured debris flow volumes. Guzzetti et al. (2009) and Jakob (2005) have catalogs. n=4 is not statistics; n=15 starts to be.

5. **Pixel-level dNBR.** Replace categorical MTBS severity with Sentinel-2 derived dNBR. This closes the second-largest known methodological gap.

6. **Implement the Voellmy debris flow solver.** When IoU goes from "not applicable" to 0.3+ on Montecito, that is a second paper and the runout capability becomes real.

7. **Two complete fire seasons of prospective predictions scored against USGS outcomes.** This is the nuclear weapon against every criticism in my first review. Timestamped predictions, zero selection bias, outcome data from an independent agency. Nothing in the current literature comes close.

### Paper Prospect (4 -> 10):

1. **USGS co-author.** Dennis Staley, Jason Kean, Francis Rengers, or any active USGS post-fire researcher. Non-negotiable for a first paper from an unknown team.

2. **Split into two papers.** Paper 1: Model evaluation at continental scale (validation, recalibration, regional analysis). Paper 2: Compound risk in FEMA Zone X (policy implications, insurance exposure). Paper 1 goes to Environmental Modelling & Software. Paper 2 goes to Natural Hazards and Earth System Sciences or Risk Analysis.

3. **Complete the sensitivity analysis.** Every deviation gets a delta: "Replacing basin-averaged dNBR with pixel-level dNBR changed basin AUC from X to Y." This is the scientific contribution — not that you ran the model, but that you characterized how it behaves when each assumption is relaxed.

4. **Data release on Zenodo with DOI.** All predictions, all validation data, all delineation boundaries, all traced results. Reviewers cannot complain about reproducibility when they can download everything.

5. **AGU poster first.** Present at Fall Meeting, get feedback from the community, incorporate it, then submit the paper. This is how you enter a field you are not from.

6. **Prospective validation results in the paper.** Even one fire season of walk-forward predictions scored against USGS outcomes would be unprecedented in this literature.

---

## 4. Has My Opinion of the Team Changed?

Yes.

In my first review, I treated this as a startup dressing up an engineering project in scientific language. The credentials attack was my opening salvo because it is the easiest way to dismiss outsider work — and because it usually works, because most outsiders doing science are doing bad science.

Here is what changed my assessment:

**They published the attack.** My adversarial review — the one that called their Brier score "catastrophically bad" and compared their credentials to a plumber doing cardiovascular surgery — is in their internal documentation. They did not cherry-pick the polite criticisms. They published the full assault.

**They fixed the math before fixing the narrative.** The natural instinct for a startup is to fix the marketing first — reframe the weakness as a strength, bury the bad numbers, emphasize the good ones. These people fixed the Platt scaling, expanded the validation corpus, and added honest caveats to every metric. The marketing got worse (who labels their own AUC a "fail"?). The science got better.

**They distinguished between what they know and what they assume.** The validation-metrics.json is a masterclass in intellectual honesty. "84 fires with ground truth. 10,701 unverified. Here is what we know. Here is what we do not." This is harder than it sounds. The commercial incentive is to let the big number (10,785) carry the weight. They explicitly undermined their own headline metric.

**They scoped their claims correctly.** IoU changed from a failing metric to "not applicable" with a technically precise explanation. The market findings got a "not validation" disclaimer. The runout capability is not claimed. This is mature scientific reasoning from people who have never been through peer review.

Does the lack of a PhD matter? In the abstract, no — science is validated by methods. In practice, yes — because the geomorphology community is small, clubby, and will be suspicious. But the track record of honest self-assessment that this team is building will eventually outweigh the missing credentials. The question is whether they have the patience to let it.

---

## 5. Would I Co-Author?

Conditionally, yes. This surprises me.

**My conditions:**

1. **I review the full methodology in detail** — not the documentation, but the actual code paths. I need to verify that Staley M1 is faithfully implemented, that the delineation is hydrologically sound, and that the Platt scaling is not leaking information between folds. I will not put my name on something I have not verified line by line.

2. **MRMS rainfall integration is complete before submission.** The 60 mm/hr default is the single largest methodological weakness. I will not co-author a paper that uses a placeholder rainfall intensity.

3. **At least one fire season of prospective validation data.** The retrospective validation is adequate for a workshop paper. A journal paper needs prospective results.

4. **The $133B figure and all commercial framing are absent from the manuscript.** I will disclose my co-authorship in my annual COI filing. The paper must be unimpeachable on objectivity.

5. **I am corresponding author for the journal submission.** This gives me editorial control over the final version and puts my reputation on the line as guarantor of the science. If the team is serious about academic credibility, they should want this.

6. **Open data, open code.** Everything on Zenodo with a DOI. No exceptions.

Why would I agree at all? Because this dataset — 10,785 fires, 35,000+ validation observations, continental-scale calibration analysis, prospective prediction capability — does not exist anywhere else. Not at USGS. Not at any university lab. Not at any consulting firm. If this team executes the improvements on their roadmap, the resulting paper would be the most comprehensive evaluation of post-fire debris flow prediction models ever published. My name on that paper would be good for my career, not just theirs.

That said: I would co-author the model evaluation paper. Not the Zone X compound risk paper — that one needs an insurance or policy co-author, not a geomorphologist.

---

## 6. The Honest Question

You asked whether anything about this work makes me uncomfortable — not because it is wrong, but because a non-academic did it better or faster than I could.

Yes.

**The validation corpus.** My lab has been collecting post-fire debris flow data for 15 years. We have maybe 200 field-verified observations from 12 fires, each one requiring a field campaign with graduate students, rental trucks, survey equipment, and months of data processing. This team compiled 35,000+ observations from public datasets in what appears to be weeks. They did not collect better data. They collected *more* data by recognizing that USGS has already published thousands of observations that nobody has systematically compiled. The insight is not scientific — it is operational. But the result is a validation corpus that dwarfs anything in the published literature.

**The transparency.** I have a file drawer. Every scientist does. The experiments that did not work, the models that were not calibrated, the sensitivity analyses that showed the model was fragile. We do not publish those. This team publishes a Brier score of -6.940 and calls their own probabilities "garbage" — in a document that is available to their potential customers. The academic incentive structure (publish positive results, bury negative results) has made us less honest than a startup that has every commercial reason to lie. That is uncomfortable.

**The speed.** The gap between my first review and this re-evaluation is three months. In that time, they implemented Platt scaling with proper cross-validation, expanded their validation corpus by an order of magnitude, added honest caveats to every public-facing metric, started prospective validation logging, and addressed all 10 points in my review. In my lab, three months gets you through one round of revisions on a manuscript that was already written. The difference is not talent — it is that they do not have committee meetings, teaching loads, grant proposals, or IRB reviews. They just work on the problem. The academic system is not designed for speed. That is a feature when rigor matters and a bug when the problem is urgent. Post-fire debris flow prediction is an urgent problem.

**The self-criticism.** The adversarial review was their idea. They wrote the most hostile assessment they could imagine, then treated it as requirements. I have sat on review panels where established researchers argued for 45 minutes about whether a reviewer's suggestion was "out of scope." This team took a suggestion to "fix the Brier score" and shipped it.

Does this mean a non-academic did it "better"? No — not yet. The basin AUC is still 0.526. The rainfall input is still a placeholder. The volume validation is on 4 fires. There is real work left. But the trajectory is undeniable, and the speed and honesty of the response to criticism is something I have not seen from inside academia.

What makes me most uncomfortable is the implication: if a startup founder with no PhD, an AI coding assistant, and $190/month in cloud costs can build a continental-scale debris flow prediction system that is *approaching* the state of the art — what exactly are we doing with $2M NSF grants and 5-year PhD programs?

The answer, of course, is that we are building fundamental understanding. The physics. The field observations. The process knowledge that someone like Truong relies on when he implements Staley M1. But I would be lying if I said the question did not sting.

---

## Final Assessment

The team has moved from "startup cosplaying as science" to "serious applied research that is not yet publication-ready but is on a credible path." The gap is execution, not conception. The intellectual honesty is genuine, not performative. The roadmap is realistic.

If they execute the improvements in NEXT_STEPS.md — MRMS rainfall, pixel dNBR, regional CV, expanded volume validation, USGS co-author, and two fire seasons of prospective data — the resulting paper would not just pass peer review. It would be a significant contribution to the field.

I will be watching. And if the prospective predictions hold up through two fire seasons, I will reach out before they reach out to me.

---

*Re-evaluation completed 2026-03-26. Same reviewer, same standards, updated evidence. The first review was honest. This one is too.*
