# Contributing Field Observations

TORRENT uses a closed-loop calibration system: your field observations help improve model accuracy for everyone. This document explains how to submit observations and what happens after submission.

## Submitting Field Observations

### API Endpoint

Submit observations to the TORRENT Research API:

```bash
POST https://api.torrentrisk.com/api/v1/research/observations
```

### Authentication

Requires an Academic or Professional tier API key. Apply for academic access at:
https://torrentrisk.com/academic

Include your API key in the request header:
```bash
X-API-Key: trk_ac_<your-key>
```

### Request Schema

```json
{
  "fire_slug": "eaton-2025",
  "lat": 34.1850,
  "lon": -118.0950,
  "event_date": "2025-01-15",
  "occurred": true,
  "observed_volume_m3": 12500.0,
  "notes": "Debris flow deposit at mouth of canyon, ~12m wide, 1.5m deep"
}
```

**Required fields:**
- `fire_slug` — Fire identifier (lowercase, hyphenated; e.g., `thomas-2017`, `camp-2018`)
- `lat` — Latitude (WGS84 decimal degrees, -90 to 90)
- `lon` — Longitude (WGS84 decimal degrees, -180 to 180)
- `event_date` — Date of observation (ISO 8601 format: `YYYY-MM-DD`)
- `occurred` — Boolean: `true` if debris flow occurred, `false` if no flow despite storm

**Optional fields:**
- `observed_volume_m3` — Estimated debris volume in cubic meters
- `sub_watershed_id` — USGS sub-watershed HUC if known
- `notes` — Field notes, site description, measurement methods

### Example Request

```bash
curl -X POST "https://api.torrentrisk.com/api/v1/research/observations" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: trk_ac_yourapikey" \
  -d '{
    "fire_slug": "eaton-2025",
    "lat": 34.1850,
    "lon": -118.0950,
    "event_date": "2025-01-15",
    "occurred": true,
    "observed_volume_m3": 12500.0,
    "notes": "Debris flow deposit at canyon mouth, 12m wide, 1.5m deep"
  }'
```

**Response:**
```json
{
  "observation_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

## Filing Calibration Issues on GitHub

If you have multiple observations or found systematic model errors, file an issue on GitHub:

**Repository:** https://github.com/lannparty/torrent-validation/issues

### Issue Template

```markdown
**Fire Name:** Eaton Fire (2025)
**State:** CA
**Observation Count:** 23
**Finding:** Model under-predicts volume in steep (>35 degree) terrain

## Summary
Field observations from 23 basins in the Eaton Fire burn area show...

## Data
- Observation dates: 2025-01-15 to 2025-01-25
- Storm event: 10-year return period (46.7 mm/hr I15)
- Median observed volume: 15,200 m3
- Median predicted volume: 8,400 m3
- Ratio: 1.8x under-prediction

## Hypothesis
Voellmy friction coefficient (mu=0.175) may be too high for granitic terrain...

## Attached Data
CSV file: eaton-observations.csv (lat, lon, occurred, volume_m3, slope_deg)
```

**Label your issue:** `calibration`, `field-data`, or `model-drift`

## What Happens After Submission

### 1. Weekly Calibration Loop

Every week, `calibration_loop.py` runs automatically:
- Pairs field observations with model predictions (within 25 km, 72 hours)
- Computes prediction error: `error = observed - predicted`
- Checks for parameter drift (threshold: >5% change)

### 2. Drift Detection Triggers Recalibration

If drift exceeds 5%, the system recalibrates:

**Parameters adjusted:**
- **Platt B coefficient** — Shifts probability calibration curve left/right to reduce mean error
- **Voellmy mu (friction)** — Reduced if flows travel farther than predicted; increased if shorter
- **Manning's n** — Adjusted for burned vs. unburned terrain if systematic flow velocity errors

**Parameters NOT changed:**
- Staley M1 coefficients (fixed per USGS 2017 publication)
- Gartner/Santi volume equations (fixed per literature)
- DEM resolution, soil data sources

### 3. Validation Metrics Update

After recalibration, updated metrics are published to:
```
https://torrentrisk.com/validation-metrics.json
```

This file is deployed to CloudFront and powers the live validation dashboard at:
https://torrentrisk.com/validation

### 4. Credit and Attribution

When calibration is triggered by GitHub issues:

**Commit messages cite the issue:**
```
feat(calibration): adjust Voellmy mu=0.168 for granitic terrain

Reduces under-prediction in steep basins per field observations.

Closes #42 (Eaton Fire volume under-prediction)
Co-Authored-By: Dr. Jane Smith <jane.smith@university.edu>
```

**Validation page credits contributors:**
- GitHub username or institutional affiliation
- Observation count and fires validated

Example: "CA validation includes 23 obs from Dr. Jane Smith (Stanford), Eaton Fire"

## Data Format Requirements

### CSV Upload Format

If submitting bulk observations via GitHub, use this CSV schema:

```csv
fire_slug,lat,lon,event_date,occurred,observed_volume_m3,notes
eaton-2025,34.1850,-118.0950,2025-01-15,true,12500,"Canyon mouth deposit"
eaton-2025,34.1920,-118.1020,2025-01-15,false,,"No flow despite storm"
eaton-2025,34.1780,-118.0880,2025-01-16,true,8200,"Highway 2 closure"
```

**Required columns:** `fire_slug`, `lat`, `lon`, `event_date`, `occurred`

**Optional columns:** `observed_volume_m3`, `sub_watershed_id`, `notes`

### Quality Requirements

- GPS accuracy within 50m (consumer GPS acceptable)
- Date accuracy within 24 hours
- Volume estimates ±50% acceptable
- **Negative observations required** — basins without debris flow prevent over-prediction

## Calibration Transparency

All calibration events are logged to S3 (`calibration/events/YYYY-MM-DD.json`) with parameters before/after, observation count, accuracy, and recompute triggers.

Weekly summaries: https://github.com/lannparty/torrent-validation/tree/main/calibration

## Privacy and Data Use

GPS coordinates are public (validation dataset). Personal identifiers optional. Email addresses never published. Academic use only.

## Questions

API issues: https://github.com/lannparty/torrent-validation/issues | Academic access: academic@torrentrisk.com

## License

All contributed observations are released under CC0 1.0 Universal (public domain).
By submitting observations, you affirm that you have the right to contribute the data and agree to the CC0 license.
