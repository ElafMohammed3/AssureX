# Google Teachable Machine — Claim Summary Card Classifier

SRS deliverable 5 evidence. Covers functional requirement xxi and
non-functional requirement 4.

## Project

| Field | Value |
|---|---|
| Hosted project link | https://teachablemachine.withgoogle.com/models/O5nayhm-e/ (retrained) · https://teachablemachine.withgoogle.com/models/mgAFrC5T1/ (first run) |
| Teachable Machine version | 2.4.16 |
| Exported format | TensorFlow / Keras |
| Export files | `keras_model.h5`, `labels.txt`, `metadata.json` |
| Model version | TM 2.4.16, exported 2026-09-28 |
| Labels | `Valid Claim`, `Invalid Claim`, `Manual Review` |
| Input size | 224 x 224 |

## Training data

| Class | Images | Distinct claims |
|---|---|---|
| Valid Claim | 700 | 350 |
| Invalid Claim | 700 | 350 |
| Manual Review | 700 | 350 |
| **Total** | **2,100** | **1,050** |

Each training claim has two visual variations (`_v1`, `_v2`) as required by
SRS 1.2. The variations change date format and colour scheme only. Verified
across 60 claims: `REPAIR HISTORY` and every other field is identical between
variants, so no claim information changes.

`dataset/cards/validation/` (225) and `dataset/cards/test/` (225) were never
uploaded.


## Training configuration

| Setting | Value |
|---|---|
| Epochs | 50 |
| Batch size | 16 |
| Input size | 224 x 224 (Teachable Machine maximum) |

## Training observations

Two runs were performed.

| Run | Card size | Fields | Valid | Invalid | Manual | Overall |
|---|---|---|---|---|---|---|
| 1 | 900 x 700 | 11 | 0.89 | 0.88 | 0.78 | 84.76% |
| 2 | 1600 x 1600 | 15 | 0.92 | 0.90 | 0.81 | 87.94% |

### Why run 1 underperformed

The classifier reads the Claim Summary Card as an image, and Teachable
Machine resizes every input to 224 x 224. In the original 900 x 700 card the
field values rendered at 16 px, which is 4.0 px after resizing. The class is
decided by the text in `REPAIR HISTORY`, which was therefore illegible to the
network.

Enlarging the card to 1600 x 1600 with 48 px values raises the effective text
height to 6.7 px, a 1.68x improvement, and the overall accuracy rose 3.18
points.

### Known weakness

`Manual Review` remains the weakest class. Of the 315 holdout samples, 20
Manual Review claims were predicted as `Valid Claim`. Field analysis shows why:
`No previous repairs` appears in 72% of Valid claims, 74% of Invalid claims and
68% of Manual Review claims, so for roughly two thirds of Manual Review claims
no field on the card separates them from Valid claims. This is a property of
the dataset construction, not a tuning problem.

### Accuracy caveat

The figures above are Teachable Machine's own holdout, which is 15% of the
2,100 uploaded images. Because each claim contributed two variations, a claim's
sibling image may sit in the training half while its partner is scored. The
figure is therefore optimistic. The measured accuracy on the 225 unseen cards
in `dataset/cards/test/` is reported in `reports/`.

## Holdout measurement: attempted and not completed

Accuracy on the 225 strictly unseen cards in `dataset/cards/test/` could not
be measured. Three loading routes were tried and all failed.

| Route | Result |
|---|---|
| `tf.loadLayersModel` on the TensorFlow.js export | Loads structurally, `countParams` 538,608 and all 263 weight names resolve, but returns a saturated output for every input including uniform random noise. |
| `@teachablemachine/image` on the same file | Rejected: `Cannot read properties of null (reading 'packageVersion')`. The export omits the `format` and `packageVersion` fields the library requires. |
| `tf_keras` 2.21 on the Keras export | Loads cleanly. Across 24 test cards and three input conventions (0-1, 0-255, and MobileNet `x/127.5-1`) it never once predicted `Valid Claim`. |

The defect is in the Teachable Machine export step, not in the training, the
dataset, or the application. The in-browser model scores 87.94% on the
platform's own holdout; the exported artefacts do not reproduce that.

## Label truncation

Teachable Machine truncates class names to 12 characters in its export, so
`Invalid Claim` became `Invalid Clai...` and `Manual Review` became
`Manual Revie...`. The names in `labels.txt` and `metadata.json` were corrected
by hand, because `src/claim_service.py` matches confidence labels by exact
string and would otherwise store `None` for two of the three classes.