# AI Usage Declaration

This file records the AI-assisted development work required by the AssureX Claim Engine SRS.

## Tool

- **Tool name:** OpenAI Codex coding assistant, used through the OpenCode environment
- **Purpose:** SRS analysis, dataset-design review, Python code generation, debugging, validation-script review and documentation drafting
- **Type of assistance:** SRS-driven implementation guidance, code generation, command-line troubleshooting and repository inspection

## Modules affected

- `dataset/dataset_generator_final.py`
- Dataset CSV and Claim Summary Card generation workflow
- `dataset/validation_report.json`
- `dataset/scenarios.json`
- `dataset/feature_manifest.json`
- `README.md` and supporting documentation

## Changes made by the team

The team must complete this section after reviewing the generated code:

- [ ] Team members read the complete generator.
- [ ] Team members explain the scenario, split, card and validation functions.
- [ ] Team members modified or simplified generated code where necessary.
- [ ] Team members checked that Claim IDs are randomized.
- [ ] Team members checked that duplicate groups do not cross splits.
- [ ] Team members checked calendar-month warranty calculations.
- [ ] Team members checked that cards contain no prediction, confidence or final decision.
- [ ] Team members ran the validation report and recorded the result.

## Testing performed

The following checks were run during development preparation:

- Python syntax compilation of `dataset/dataset_generator_final.py`
- 1,500-record generation check
- 500-per-class balance check
- 1,050/225/225 split check
- 2,100/225/225 card-count check
- 2,550 mapping-row check
- zero missing mapped-image check
- duplicate-group split-isolation check
- dataset validation report with status `PASS`

The team must repeat or extend these checks after any modification.

## Team verification

- **Verified by:** `[enter team member name]`
- **Date:** `[enter date]`
- **Notes:** `[record any changes made to AI-generated code]`

## Final-decision rule

No external generative-AI API may make the final warranty-claim decision. The future decision must be produced by the team's Python model, image model, deterministic rule engine and application logic.

This declaration must be updated if another AI tool is used.
