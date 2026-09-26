# AssureX SRS Compliance Status

This document records the current honest status against the AssureX Claim Engine SRS v1.0. It must be updated after every implementation task.

## Status legend

- **PASS** — implemented and verified with evidence
- **PARTIAL** — some supporting work exists, but the requirement is not complete
- **FAIL** — required implementation is missing
- **BLOCKED** — cannot be completed until a dependency or decision is available

## Dataset and model inputs

| SRS requirement | Status | Evidence / next action |
|---|---|---|
| Create own common dataset | PASS | `dataset/dataset_generator_final.py`; no external dataset is downloaded |
| At least 1,500 unique claims | PASS | 1,500 CSV records |
| 500 Valid / 500 Invalid / 500 Manual Review | PASS | `dataset/statistics.json` |
| 70/15/15 stratified split | PASS | 1,050 / 225 / 225 |
| Same records in CSV and card form | PASS | `dataset/claim_image_mapping.csv` |
| Two training card variations | PASS | 2,100 training cards |
| Validation/test cards not used for training | PASS | Separate directories and split metadata |
| No Claim ID crosses splits | PASS | Validation report and independent audit |
| No duplicate group crosses splits | PASS | Split isolation check |
| Configurable warranty policies | PASS | `dataset/policies/*.json` |
| Claim scenarios documented | PASS | `dataset/scenarios.json` |
| Data dictionary and statistics | PASS | `dataset/data_dictionary.md`, `dataset/statistics.json` |
| Model inputs separated from audit outputs | PASS | `dataset/feature_manifest.json` |
| Document manifest and SHA-256 hashes | PARTIAL | Synthetic manifest exists; real uploaded files are not implemented |

## Machine learning

| SRS requirement | Status | Evidence / next action |
|---|---|---|
| At least three classification algorithms | FAIL | Train and compare three scikit-learn models |
| Accuracy, precision, recall and F1 | FAIL | Produce unseen-test metrics |
| Confusion matrix and class-wise results | FAIL | Produce evaluation artefacts |
| Three-class confidence output | FAIL | Save pipeline with `predict_proba` |
| Saved preprocessing/model files | FAIL | Implement the Python model task |
| At least 85% unseen-test accuracy | NOT VERIFIED | Measure honestly after training |

## Claim cards and image model

| SRS requirement | Status | Evidence / next action |
|---|---|---|
| Reusable Claim Summary Card generator | PASS | `generate_claim_card()` in the final generator |
| Cards contain facts, not decisions | PASS | No class/prediction/confidence fields are rendered |
| Google Teachable Machine training | FAIL | Train and export the three-class image model |
| Unseen image evaluation | FAIL | Evaluate the 225 test cards |
| 30-claim model comparison report | FAIL | Produce after both models exist |

## Rules and decision engine

| SRS requirement | Status | Evidence / next action |
|---|---|---|
| Configurable warranty rule engine | FAIL | Implement a separate runtime engine |
| Serial verification | PARTIAL | Generator detects mismatch; runtime evidence comparison remains |
| Contradiction detection | PARTIAL | Dataset checks exist; runtime service remains |
| Missing-document detection | PARTIAL | Dataset manifest exists; upload workflow remains |
| Duplicate claim/document detection | PARTIAL | Dataset hashes exist; runtime database detection remains |
| Final three-class decision | FAIL | Implement the decision engine |
| Decision explanation | FAIL | Generate deterministic supporting/failing reasons |

## Web application and storage

| SRS requirement | Status |
|---|---|
| Flask application | FAIL |
| MySQL/SQLAlchemy storage | FAIL |
| Registration, login and four roles | FAIL |
| Product and warranty records | FAIL |
| Claim workflow and statuses | FAIL |
| PDF/JPG/JPEG/PNG upload | FAIL |
| OCR and extracted-data correction | FAIL |
| Customer and administrator dashboards | FAIL |
| Search, filtering and downloadable reports | FAIL |
| Manual-review queue and override | FAIL |
| Error handling and security controls | FAIL |

## Competition deliverables

| Deliverable | Status |
|---|---|
| Public GitHub repository | PARTIAL — repository exists; final push still needs completion |
| README | PASS — installation, dataset and current limitations documented |
| AI_USAGE.md | PASS — declaration template created; team must complete verification fields |
| requirements.txt | PASS — dependency list created |
| LICENSE | FAIL — team must select and add an approved license |
| Project report | FAIL |
| Demonstration video | FAIL |
| Technical blog | FAIL |
| Deployment URL or local demo instructions | PARTIAL |
| Test scripts and results | PARTIAL — dataset validation exists; application tests remain |
| Team contribution record | PASS — `CONTRIBUTORS.md` created; names must be filled in |

## Acceptance gate

The project is not ready for final submission until the FAIL items are implemented and the complete flow is demonstrated:

```text
Register/Login
 -> Product
 -> Warranty
 -> Claim
 -> Document upload
 -> OCR and correction
 -> Python model
 -> Claim card
 -> Image model
 -> Model comparison
 -> Rule validation
 -> Final decision and explanation
 -> Manual review or closure
```
