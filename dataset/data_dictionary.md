# AssureX Dataset Data Dictionary

Generated according to SRS section 1.2.

| Column | Type | Description | Python model input |
|---|---|---|---|
| `claim_id` | string | Unique random claim identifier. | No |
| `claimant_id` | string | Synthetic claimant identifier. | No |
| `product_id` | string | Random product identifier; duplicate claims share it. | No |
| `invoice_number` | string | Synthetic invoice number for duplicate checks. | No |
| `duplicate_group_id` | string | Links real duplicate records; blank otherwise. | No |
| `scenario` | string | Audit-only scenario definition name. | No |
| `split` | string | train, validation or test. | No |
| `claim_class` | string | Ground truth target. | No |
| `product_category` | category | Smartphone, Laptop or Television. | Yes |
| `brand` | category | Product brand. | Yes |
| `model` | category | Product model number. | Yes |
| `retailer` | category | Purchase retailer. | Yes |
| `purchase_date` | date | Product purchase date. | Yes |
| `purchase_price` | number | Synthetic purchase amount. | Yes |
| `purchase_information_consistent` | boolean | Whether purchase information is consistent. | Yes |
| `serial_number` | string | Serial stored on the product record. | No |
| `receipt_serial_number` | string | Serial extracted from receipt. | No |
| `warranty_card_serial_number` | string | Serial extracted from warranty card. | No |
| `product_image_serial_number` | string | Serial extracted from product evidence. | No |
| `repair_record_serial_number` | string | Serial extracted from repair records. | No |
| `serial_number_status` | category | Derived serial comparison result. | No |
| `receipt_model` | category | Model found on receipt. | No |
| `warranty_card_model` | category | Model found on warranty card. | No |
| `product_image_model` | category | Model found in product evidence. | No |
| `repair_record_model` | category | Model found in repair records. | No |
| `warranty_provider` | string | Warranty provider. | Yes |
| `warranty_start_date` | date | Warranty start date. | Yes |
| `warranty_expiry_date` | date | Warranty expiry date. | Yes |
| `warranty_duration_months` | number | Configured duration in calendar months. | Yes |
| `warranty_remaining_days` | number | Expiry minus claim date; negative when expired. | Yes |
| `warranty_status` | category | Derived warranty status at claim date. | No |
| `warranty_status_at_fault` | category | Derived warranty status at fault date. | No |
| `extended_warranty` | boolean | Whether extended warranty is recorded. | Yes |
| `fault_date` | date | Reported fault date. | Yes |
| `claim_date` | date | Claim submission date. | Yes |
| `last_repair_date` | date | Most recent repair date, if any. | Yes |
| `previous_replacement_date` | date | Most recent replacement date, if any. | Yes |
| `product_age_days` | number | Claim date minus purchase date. | Yes |
| `reporting_days` | number | Claim date minus fault date. | Yes |
| `fault_category` | category | Reported fault type. | Yes |
| `fault_description` | text | Fault description. | Yes |
| `damage_type` | category | Type of damage reported. | Yes |
| `physical_damage` | boolean | Physical damage flag. | Yes |
| `liquid_damage` | boolean | Liquid damage flag. | Yes |
| `unauthorized_repair` | boolean | Unauthorized repair flag. | Yes |
| `authorized_service_center` | boolean | Whether service center was authorized. | Yes |
| `repair_history` | text | Previous repair history. | Yes |
| `previous_repair_count` | number | Number of previous repairs. | Yes |
| `previous_replacement` | boolean | Previous replacement flag. | Yes |
| `previous_replacement_count` | number | Number of previous replacements. | Yes |
| `replacement_requested` | boolean | Whether replacement is requested. | Yes |
| `receipt_available` | boolean | Whether purchase receipt is available. | Yes |
| `receipt_valid` | boolean | Whether purchase receipt is valid. | Yes |
| `warranty_card_available` | boolean | Whether warranty card is available. | Yes |
| `product_image_available` | boolean | Whether product image is available. | Yes |
| `serial_evidence_available` | boolean | Whether serial evidence is available. | Yes |
| `fault_evidence_available` | boolean | Whether fault evidence is available. | Yes |
| `repair_report_available` | boolean | Whether repair report is available. | Yes |
| `missing_documents` | text | Pipe-separated missing mandatory documents. | Yes |
| `missing_documents_count` | number | Number of missing mandatory documents. | Yes |
| `supporting_evidence_available` | boolean | Whether supporting evidence is usable. | Yes |
| `evidence_consistency` | boolean | Whether evidence agrees with entered data. | No |
| `claim_reporting_within_period` | boolean | Derived reporting-period result. | No |
| `duplicate_claim` | boolean | Whether record belongs to a real duplicate group. | No |
| `contradiction_detected` | boolean | Deterministic contradiction result. | No |
| `contradiction_details` | text | Contradiction descriptions. | No |
| `replacement_eligible` | boolean | Derived replacement result; audit only. | No |
| `hard_fail_detected` | boolean | Derived hard-fail result; audit only. | No |
| `warning_detected` | boolean | Derived warning result; audit only. | No |
| `manual_review_trigger` | boolean | Derived manual-review result; audit only. | No |

`claim_class`, policy/rule outputs, identifiers and duplicate audit fields
are retained for traceability but are not classifier inputs.
