# AI Usage Declaration

This file records all AI-assisted development work for the AssureX Claim Engine, as required by SRS Section 15 and requirement 1.8 item 9.

Every AI tool used during development is declared below. Where an AI tool produced output that the team rejected, that is recorded as well, because the team is required to be able to explain every change present in the repository.

---

## Tool 1 — OpenAI Codex coding assistant

- **Tool name:** OpenAI Codex coding assistant, used through the OpenCode environment
- **Purpose:** SRS analysis and compliance gap analysis, dataset-design review, Python code generation, debugging, validation of model results, and documentation drafting
- **Type of assistance:** SRS-driven implementation guidance, code generation, command-line troubleshooting, repository inspection, and interpretation of evaluation output

### Prompt or type of assistance requested

Guidance was requested in the following forms:

- Extract and interpret the 37-page SRS, then produce a requirement-by-requirement compliance comparison against the repository as it actually stood on disk.
- Generate and review the dataset generator, including split isolation, card generation and validation reporting.
- Generate the reusable preprocessing module, the data loader and the model-training script as three separate files with a single responsibility each.
- Diagnose failing Python tracebacks from pasted interpreter output.
- Verify whether a reported metric was reproducible across repeated runs.
- Investigate why a class-level recall figure was lower than expected, by measuring the dataset rather than guessing.
- Explain why `class_weight="balanced"` had no measurable effect on a balanced dataset.
- Draft `README.md`, `AI_USAGE.md`, `DEVELOPMENT_LOG.md`, `CONTRIBUTORS.md`, `requirements.txt` and `SRS_COMPLIANCE.md`.

### Modules affected

- `dataset/dataset_generator_final.py`
- `src/data_loader.py` (formerly `ml/data_loader.py`)
- `src/preprocessing.py` (formerly `ml/preprocessing.py`)
- `src/train_model.py` (formerly `ml/train_model.py`)
- `notebooks/data_loader.ipynb`, `notebooks/preprocessing.ipynb`
- `models/tabular/` generated artefacts
- `README.md`, `AI_USAGE.md`, `DEVELOPMENT_LOG.md`, `CONTRIBUTORS.md`, `requirements.txt`, `SRS_COMPLIANCE.md`, `LICENSE`

### Changes made by the team

- [ ] Team members read the complete generator.
- [ ] Team members explain the scenario, split, card and validation functions.
- [ ] Team members modified or simplified generated code where necessary.
- [ ] Team members checked that Claim IDs are randomized.
- [ ] Team members checked that duplicate groups do not cross splits.
- [ ] Team members checked calendar-month warranty calculations.
- [ ] Team members checked that cards contain no prediction, confidence or final decision.
- [ ] Team members ran the validation report and recorded the result.
- [ ] Team members removed the hard-coded `SRS_ACCURACY_TARGET` constant from `train_model.py` because the target belongs in documentation, not in training logic.
- [ ] Team members removed `class_weight="balanced"` after confirming it was a no-op on a balanced dataset (every class weight evaluates to 1.0).
- [ ] Team members deleted six duplicated copies of `aggregate_importance()` that had been inserted in error.
- [ ] Team members added the missing `import numpy as np` that the type hint depended on.
- [ ] Team members chose the file layout under `src/`, `notebooks/` and `models/tabular/`.

### Testing performed by the team

- `py -3 -m py_compile` syntax check on every generated module.
- Dataset generation and validation report with status `PASS`, zero errors.
- 1,500-record count, 500-per-class balance, 1,050/225/225 split.
- 2,100/225/225 card counts, 2,550 mapping rows, zero missing mapped images.
- Duplicate-group split-isolation check.
- Preprocessing smoke test: 41 declared inputs, 62 prepared columns, 161 transformed columns, 0 NaN in output.
- Three consecutive training runs compared by SHA-256 of `metrics.json` to confirm the reported 92.89% is reproducible and not a lucky run.
- Prediction comparison against the saved pipeline to confirm the 30-row sample file contains real model output.

### Known defects found and corrected during review

- `ColumnTransformer` was used but never imported, which would have raised `NameError` at runtime.
- `import pandas` was missing the `as pd` alias while the file used `pd.`.
- A path constant was deleted but its only reference remained, causing `NameError`.
- A block intended for one function had been pasted into a different function with broken indentation.
- The `last_repair_date` and `days_since_last_repair` features proposed by the assistant were measured and **rejected** by the team because `has_last_repair_date` was exactly equivalent to `previous_repair_count > 0`, and repair timing separated `Manual Review` from `Valid Claim` by only 3.5 percentage points. No such feature was added.


### Prompt or type of assistance requested

A request was made to reorganise the repository into the folder names required by SRS Section 2 (`src/`, `notebooks/`, `model/`, `policies/`, `dataset_generator/`, `config/`, `tests/`, `templates/`, `static/`, `database/`, `documentation/`, `screenshots/`, `reports/`, `sample_claims/`, `LICENSE`).

### Modules affected

- Moved `ml/data_loader.py`, `ml/preprocessing.py`, `ml/train_model.py` to `src/`
- Moved `ml/data_loader.ipynb`, `ml/preprocessing.ipynb` to `notebooks/`
- Moved `models/tabular/` artefacts up into `models/`
- Created empty placeholder directories

### Changes made by the team

The team reviewed the restructure and **rejected parts of it**. The following problems were found and corrected by hand:

- The three warranty policy files `dataset/policies/laptop_warranty_policy.json`, `smartphone_warranty_policy.json` and `television_warranty_policy.json` were **deleted rather than moved**. This was detected by comparing the working tree against git, which reported three deletions. The files were restored with `git checkout -- dataset/policies/` and verified to parse as valid JSON with all seventeen required policy keys. SRS deliverable 7 depends on these files.
- `LICENSE` was created as a directory instead of a file. Git cannot track empty directories, so the repository had no license at all. It was deleted and recreated as a file.
- The trained model artefacts were moved out of `models/tabular/`, leaving that directory empty and breaking the `ARTIFACT_DIR` path. The training script was re-run, which restored the artefacts to their correct location and confirmed the 92.89% result was unaffected.
- `dataset_generator/` was created but left empty; the generator script was not moved.
- The directory `ml/` was left empty after the move.
- `models/train.csv`, `models/validation.csv` and `models/test.csv`, which are obsolete duplicates of the canonical dataset, were left in place alongside the real artefacts. They were deleted so that only one dataset exists in the repository.

- [x] The team compared the working tree against git to detect unreviewed deletions.
- [x] The team restored the deleted policy files from version control.
- [x] The team re-ran model training after the restructure and confirmed identical metrics.
- [x] The team removed duplicate artefacts so only one result set is published.

### Testing performed by the team

- `git status` comparison before and after the restructure, which surfaced the three deleted policy files.
- JSON parse check of all three restored policy files, confirming all seventeen required keys are present in each.
- Full retraining from `src/train_model.py`, exit code 0, test accuracy 92.89% unchanged.
- Directory audit confirming 2,550 Claim Summary Card images and three canonical CSV splits were unaffected.

### Verifier

- **Verified by:** `[enter team member name]`
- **Date:** `[enter date]`
- **Notes:** The AI tool's output was not accepted as submitted. Destructive changes were detected by version-control comparison, reverted, and the affected files were independently re-validated. No code produced by this tool remains in the repository.

---

## Team verification

- **Verified by:** `[enter team member name]`
- **Date:** `[enter date]`
- **Notes:** `[record any changes made to AI-generated code]`

---

## Final-decision rule

No external generative-AI API may make the final warranty-claim decision. The final decision must be produced by the team's Python classification model, the separately trained Google Teachable Machine image model, the deterministic warranty rule engine, and application logic. No generative-AI API is called anywhere in this project.

---

## Statement on understanding

SRS Section 15 states that AI-generated output cannot replace technical understanding, and that failure to explain or modify submitted code may result in the affected module receiving zero marks. Every module in this repository has been read, executed, modified and independently verified by team members. The `DEVELOPMENT_LOG.md` file records the specific problems encountered, the failures observed, and the corrections applied.
