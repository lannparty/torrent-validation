# Regional Bias Analysis: Staley M1 Model Across US Fire Regions

**Date:** 2026-03-26
**Dataset:** 10,340 analyzed fires from TORRENT manifest
**Method:** Stratified random sample of 94 fires (20 per major region), 25-yr design storm

## Executive Summary

The Staley M1 debris flow probability model was calibrated primarily on Southern California
and Colorado fires (Staley et al. 2016, USGS OFR 2016-1106). Analysis of TORRENT's 10,785-fire
database reveals **three categories of regional bias**, two of which are data-availability artifacts
rather than model deficiencies:

1. **Data gap bias** (Alaska, Hawaii): NOAA Atlas 14 has no coverage. All fires use a hardcoded
   35.0mm fallback precipitation. This is the dominant source of "bias" in these regions.
2. **Input saturation bias** (Great Plains, Hawaii): dNBR values cluster near 500 and soil Kf
   values are anomalously high, driving probabilities to ~1.0 regardless of terrain.
3. **Genuine model extrapolation risk** (Alaska): Permafrost soils, boreal vegetation, and
   flat tundra terrain are outside the model's training domain. 25% of sampled Alaska fires
   produced 0 sub-watersheds (complete processing failure). 55% of Alaska fires in the manifest
   have 0 acres (missing perimeter data).

The model performs well in its calibration domain (CA, CO) and adjacent regions (Pacific NW,
Rocky Mountain, Southwest). Regional correction factors are warranted for Alaska and should be
investigated for the Great Plains.

## Regional Summary Table (25-yr Design Storm)

| Region | N | Avg Max Prob | Med Max Prob | Avg Total Vol (m3) | Avg Precip (mm) | Avg Sub-WS | Avg Max Depth (m) |
|---|---|---|---|---|---|---|---|
| Pacific Coast | 20 | 0.9647 | 1.0000 | 15,830 | 30.69 | 29.1 | 9.83 |
| Rocky Mountain | 20 | 0.9669 | 0.9998 | 9,170 | 30.16 | 21.6 | 5.59 |
| Southwest | 20 | 0.9998 | 1.0000 | 10,584 | 42.23 | 29.5 | 10.63 |
| Alaska | 20 | 0.7396 | 0.9983 | 4,063 | **35.00** | 17.0 | 3.59 |
| Hawaii | 9 | 0.9912 | 0.9990 | 5,351 | **35.00** | 22.3 | 8.16 |
| Great Plains | 5 | 0.9991 | 1.0000 | 5,035 | 44.85 | 32.4 | 8.64 |

## Finding 1: Precipitation Fallback Problem

**100% of Alaska fires and 100% of Hawaii fires use the 35.0mm hardcoded fallback** instead of
real NOAA Atlas 14 data. This is because Atlas 14 coverage does not extend to these regions.

The fallback is implemented in `the batch processing code`:
```
match return_period {
    2 => 15.0,
    25 => 35.0,
    100 => 50.0,
    _ => 25.0,
}
```

The fallback also affects a significant fraction of CONUS fires:

| Region | Fires Using Fallback (35.0mm) | Fires Using Atlas 14 | Fallback % |
|---|---|---|---|
| Pacific Coast | 11/20 | 9/20 | 55% |
| Rocky Mountain | 8/20 | 12/20 | 40% |
| Southwest | 11/20 | 9/20 | 55% |
| Alaska | 20/20 | 0/20 | **100%** |
| Hawaii | 9/9 | 0/9 | **100%** |
| Great Plains | 1/5 | 4/5 | 20% |

Even in CONUS, ~50% of fires fall back to 35.0mm. This is likely because fires in remote/rural
areas are far from Atlas 14 grid points, or the HDSC API was unavailable during batch processing.

**Impact:** For the Southwest, where real 25-yr storms deliver 42-58mm, the 35.0mm fallback
*under-predicts*. For the Pacific Northwest, where 25-yr storms deliver 20-32mm, 35.0mm
*over-predicts*. This creates artificial inter-regional bias that has nothing to do with the
Staley model itself.

## Finding 2: Input Saturation in Non-Traditional Fire Regions

Per-watershed trace analysis reveals anomalous input values:

| Region (example fire) | Avg dNBR | Avg Soil Kf | Avg Burned Steep Frac | Avg WS Prob |
|---|---|---|---|---|
| Pacific Coast (Dixie, CA) | 280.2 | 0.059 | 0.112 | 0.603 |
| Rocky Mountain (Citadel, WY) | 280.9 | 0.059 | 0.674 | 0.974 |
| Southwest (Ridge, AZ) | 233.0 | 0.080 | 0.027 | 0.819 |
| Hawaii (Kipukanene, HI) | **497.5** | **0.169** | 0.101 | **0.998** |
| Great Plains (Dewey, SD) | **497.6** | **0.318** | 0.020 | **1.000** |

**Hawaii and Great Plains fires have dNBR values clustered near 500** (the maximum of the scale),
with very little variance. This suggests either: (a) burn severity data (MTBS/Sentinel) is
unavailable and a high default is applied, or (b) grassland/shrubland fires in these regions
genuinely produce uniform high-severity burns.

Great Plains soil Kf of 0.32 is 5x higher than CA's 0.059. This is physically plausible (prairie
soils are fine-grained and erodible), but it drives the Staley M1 X3R term (Kf x I15) to extreme
values, saturating probability at 1.0 even with low burned-steep fractions.

**The combination of high dNBR + high Kf + high precipitation overwhelms the model in these regions,
producing probability = 1.0 for every sub-watershed.** The model cannot discriminate risk when
all inputs are at the top of the range.

## Finding 3: Alaska Processing Failures

Alaska stands out for multiple compounding issues:

- **25% of sampled fires (5/20) produced 0 sub-watersheds** -- complete processing failures
- **55% of all Alaska fires in the manifest have 0 acres** -- missing perimeter data from NIFC
- **All fires use fallback precipitation** (35.0mm)
- The fires that *do* process show a bimodal distribution: either prob ~1.0 (steep terrain
  near the Alaska Range) or prob = 0.0 (failed to delineate)

Alaska fires that successfully process show high probabilities (avg 0.99 excluding failures),
which is suspect for flat tundra/boreal terrain. The model has no training data in permafrost
regions and the assumption of mineral soil erodibility may be invalid where organic soils dominate.

## Finding 4: Staley M1 Performs Reasonably in Calibration Domain

For the regions where the model was calibrated and validated (CA, CO, and adjacent states):

| State | N | Avg Max Prob | Med Max Prob | Avg Total Vol (m3) | Avg Precip (mm) |
|---|---|---|---|---|---|
| CA | 16 | 0.956 | 1.000 | 12,557 | 29.61 |
| CO | 2 | 0.729 | 0.729 | 22,472 | 29.55 |
| ID | 10 | 0.989 | 0.996 | 7,204 | 28.29 |
| MT | 3 | 0.998 | 1.000 | 3,406 | 31.17 |
| UT | 2 | 1.000 | 1.000 | 16,643 | 34.15 |
| OR | 2 | 1.000 | 1.000 | 34,815 | 35.00 |
| AZ | 12 | 1.000 | 1.000 | 10,587 | 42.94 |
| NM | 8 | 1.000 | 1.000 | 10,580 | 41.17 |
| WY | 3 | 1.000 | 1.000 | 7,637 | 33.12 |

Colorado shows notably lower average probability (0.729) than neighboring states. With only 2
sampled fires this is not statistically significant, but it is consistent with Colorado's
generally lower burn severity and shorter fire seasons compared to CA.

The Southwest (AZ, NM) consistently produces probability = 1.0 across all sampled fires. This
is driven by high design storm precipitation (42-58mm for fires with Atlas 14 data) combined
with moderate-to-high burn severity. This is physically reasonable -- the monsoon-driven debris
flow risk in post-fire AZ/NM landscapes is well-documented.

## Finding 5: Storm Sensitivity (2-yr vs 25-yr)

| Region | Avg Prob (2yr) | Avg Prob (25yr) | Ratio | Avg Precip 2yr | Avg Precip 25yr |
|---|---|---|---|---|---|
| Pacific Coast | 0.781 | 0.965 | 1.24x | 13.96 | 30.69 |
| Rocky Mountain | 0.737 | 0.967 | 1.31x | 13.15 | 30.16 |
| Southwest | 0.956 | 1.000 | 1.05x | 20.22 | 42.23 |
| Alaska | 0.561 | 0.740 | 1.32x | 15.00 | 35.00 |
| Hawaii | 0.692 | 0.991 | 1.43x | 15.00 | 35.00 |
| Great Plains | 0.904 | 0.999 | 1.10x | 21.45 | 44.85 |

Hawaii shows the highest sensitivity to storm intensity (1.43x), while the Southwest shows
almost none (1.05x) because it is already saturated at the 2-yr level. This saturation in the
Southwest reduces the model's value for risk discrimination -- if every watershed is at P=1.0
for a 2-yr storm, the model cannot tell emergency managers which watersheds to prioritize.

## Normalized Metrics (Volume per Sub-Watershed)

| Region | Avg Vol/WS (m3) | Med Vol/WS (m3) | Avg Sed/WS (tonnes) |
|---|---|---|---|
| Pacific Coast | 765 | 556 | 33,126 |
| Rocky Mountain | 504 | 343 | 12,899 |
| Southwest | 449 | 257 | 16,162 |
| Alaska | 237 | 64 | 12,730 |
| Hawaii | 267 | 234 | 11,109 |
| Great Plains | 136 | 113 | 2,047 |

Volume per watershed tracks terrain relief as expected: Pacific Coast (Sierra Nevada, Cascades)
produces the highest volumes, Great Plains the lowest. This is encouraging -- the Gartner volume
model (which uses relief as an input) is responding appropriately to terrain even where the
probability model may be saturated.

## Recommendations

### Immediate (data quality)
1. **Expand Atlas 14 coverage** -- download and cache the full CONUS Atlas 14 grid locally to
   eliminate the 35.0mm fallback for CONUS fires. The current 50% fallback rate in Pacific Coast
   is unacceptable.
2. **Flag Alaska and Hawaii fires** in the manifest with a data quality warning indicating
   fallback precipitation was used.
3. **Investigate the high dNBR values** in HI and SD -- determine whether these are real
   (grassland fires burn uniformly hot) or a fallback/default.

### Medium-term (model improvement)
4. **Regional precipitation correction** -- for regions where Atlas 14 is unavailable, use PRISM
   or ERA5 reanalysis data as a second-best source rather than a static fallback.
5. **Probability capping for Alaska** -- consider capping debris flow probability at 0.5 for
   Alaska fires until the model can be validated against observed debris flows in permafrost terrain.
6. **Discrimination improvement for Southwest** -- the model is saturated (P=1.0 for all
   sub-watersheds) even at 2-yr storms. Consider reporting the logit value directly rather than
   the sigmoid probability, so users can distinguish "barely 1.0" from "overwhelmingly 1.0."

### Paper implications
7. **Disclose the calibration domain limitation** explicitly. The Staley M1 model was calibrated
   on ~600 post-fire debris flows primarily in CA and CO. TORRENT applies it to 10,340 fires
   across all US states, including regions with fundamentally different soils, vegetation, and
   climate. Regional bias is an honest limitation, not a weakness -- TORRENT's scale makes it
   *discoverable* for the first time.
8. **The 35.0mm fallback is the largest systematic bias source** in the dataset. Fix the data
   pipeline first, then re-run the analysis to isolate genuine model bias from data artifacts.

## Appendix: Sample Fire Details

### Alaska (n=20, 5 failures)
| Fire | Prob | Volume (m3) | Sediment (t) | WS | Precip (mm) |
|---|---|---|---|---|---|
| little-mud-1999 | 1.000 | 483 | 15,863 | 8 | 35.0 |
| long-creek-2002 | 1.000 | 4,794 | 356,154 | 5 | 35.0 |
| mcarthurcreek-1999 | 1.000 | 15,820 | 1,030,204 | 22 | 35.0 |
| kuyukutuk-river-2016 | 1.000 | 12,215 | 486,245 | 16 | 35.0 |
| hot-springs-creek-2-2007 | 1.000 | 8,783 | 338,115 | 23 | 35.0 |
| kilo-2015 | 1.000 | 16,170 | 1,547,714 | 19 | 35.0 |
| berry-creek-2016 | 1.000 | 3,009 | 36,259 | 20 | 35.0 |
| awuna-river-1-2013 | 0.999 | 1,003 | 49,492 | 23 | 35.0 |
| dck-se-40-1986 | 0.999 | 2,762 | 9,132 | 45 | 35.0 |
| siruk-creek-2016 | 0.998 | 2,702 | 3,624 | 51 | 35.0 |
| winter-trail-2009 | 0.998 | 4,071 | 22,986 | 29 | 35.0 |
| dck-ssw-21-1993 | 0.998 | 662 | 7,875 | 10 | 35.0 |
| john-river-2008 | 0.989 | 1,078 | 1,150 | 28 | 35.0 |
| kugruk-river-1-2019 | 0.964 | 3,543 | 11,805 | 28 | 35.0 |
| trail-creek-2019 | 0.847 | 4,166 | 22,511 | 13 | 35.0 |
| moose-crk-1990 | 0.000 | 0 | 0 | 0 | 35.0 |
| dune-lake-1993 | 0.000 | 0 | 0 | 0 | 35.0 |
| discovery-1993 | 0.000 | 0 | 0 | 0 | 35.0 |
| old-grouch-top-2019 | 0.000 | 0 | 0 | 0 | 35.0 |
| birch-hill-1990 | 0.000 | 0 | 0 | 0 | 35.0 |

### Hawaii (n=9, 0 failures)
| Fire | Prob | Volume (m3) | Sediment (t) | WS | Precip (mm) |
|---|---|---|---|---|---|
| uila-1987 | 1.000 | 7,699 | 614,528 | 13 | 35.0 |
| kipukanene-1987 | 1.000 | 5,768 | 58,602 | 30 | 35.0 |
| broomsedge-2000 | 1.000 | 447 | 21,147 | 14 | 35.0 |
| luhi-fire-2003 | 1.000 | 4,181 | 308,257 | 10 | 35.0 |
| central-maui-2019 | 0.999 | 2,577 | 59,774 | 11 | 35.0 |
| napau-2011 | 0.996 | 4,380 | 43,423 | 21 | 35.0 |
| panau-iki-2003 | 0.986 | 6,649 | 94,166 | 26 | 35.0 |
| kupukupu-2002 | 0.986 | 9,666 | 181,574 | 30 | 35.0 |
| keauhou-ranch-brush-fire-2018 | 0.955 | 6,788 | 57,351 | 46 | 35.0 |

### Great Plains (n=5, 0 failures)
| Fire | Prob | Volume (m3) | Sediment (t) | WS | Precip (mm) |
|---|---|---|---|---|---|
| dewey-ii-1991 | 1.000 | 5,532 | 69,555 | 49 | 50.6 |
| hay-bale-1996 | 1.000 | 1,450 | 6,302 | 29 | 45.4 |
| red-point-2003 | 1.000 | 14,535 | 247,719 | 57 | 46.0 |
| coffee-1987 | 0.999 | 1,076 | 30,120 | 12 | 35.0 |
| kinney-2012 | 0.996 | 2,584 | 26,133 | 15 | 47.2 |

---

*Analysis performed on a stratified random sample (seed=42) of 94 fires from the TORRENT manifest.
Summary.json data fetched from S3 for 25-yr and 2-yr design storms. Calculation traces examined for
one representative fire per region. Full manifest (10,340 fires) used for confidence grade and
data completeness statistics.*
