# Development Log

This log follows the SRS requirement to record work completed, problems encountered, model failures, changes made and tests performed.

## 2026-09-25 — Initial dataset and cards

### Work completed

- Reviewed the AssureX SRS and the minimum implementation prompt.
- Inspected the existing generated dataset, CSV files, policies, cards and preprocessing notebook.
- Confirmed the original nominal counts: 1,500 claims and 2,550 card images.
- Reviewed the three warranty policies for Smartphone, Laptop and Television.

### Problems encountered

- The original generator used working-directory-relative paths.
- Claim IDs were generated in class-ordered ranges, creating a leakage risk for the image model.
- The original dataset contained semantic inconsistencies around expiry dates, repair dates, category-specific documents and duplicate claims.
- The original preprocessing notebook stopped before training and model persistence.

### Changes made

- Planned a self-generated SRS-compliant dataset with predefined scenarios.
- Separated model inputs from audit and rule outputs.
- Added real duplicate claim groups, document hashes, mapping files, feature manifest, scenarios file and validation report.

### Tests performed

- Inspected CSV and card counts.
- Checked Claim ID uniqueness and split membership.
- Reviewed the SRS dataset split requirement.

## 2026-09-26 — Generator hardening and recovery

### Work completed

- Created `dataset/dataset_generator_final.py` as the authoritative generator.
- Added calendar-month warranty calculations.
- Added deterministic contradiction detection.
- Added category-specific mandatory documents and policy-driven replacement thresholds.
- Added randomized Claim IDs and Product IDs after scenario generation.
- Added split assignment that keeps duplicate groups together.
- Added `scenarios.json`, `feature_manifest.json`, `statistics.json`, `data_dictionary.md`, `documents.csv` and `validation_report.json`.
- Added a validation report covering class counts, split counts, card counts, mapping paths and duplicate hashes.

### Problems encountered

- A Windows file-lock error occurred while trying to replace an open CSV file.
- A copy operation created nested `cards/cards`, `csv/csv` and `policies/policies` folders.
- An interrupted card-generation run left extra untracked images.
- A push was rejected because the GitHub remote contained three commits that were not present locally.

### Changes made

- Used isolated `final_run` folders for test generation.
- Removed only untracked extra card files after previewing them with `git clean -nd`.
- Restored the correct top-level dataset structure and verified all mapping paths.
- Corrected negative wording in PASS validation messages.
- Added a `.gitignore` for caches and temporary run folders.
- Created a local backup branch before integrating remote commits.

### Tests performed

```text
Total claims:              1500
Class balance:             500 / 500 / 500
Training split:            1050
Validation split:           225
Test split:                 225
Training cards:            2100
Validation cards:           225
Test cards:                 225
Mapping rows:              2550
Missing mapped images:     0
Duplicate group crossings:  0
Validation status:          PASS
```

## Current status

The dataset foundation is complete. The Flask/MySQL application, trained Python model, Google Teachable Machine model, OCR, rule engine, decision engine, dashboards and manual-review workflow remain to be implemented.

## Next entry

Record the next task here, including:

- Task name
- Team member responsible
- Files changed
- Tests run
- Failures and fixes
- SRS requirements affected
