import os
import random
import csv
import json
from datetime import datetime, timedelta
from PIL import Image, ImageDraw

# ---------------------------------------------------------
# CONFIGURATION & CONSTANTS
# ---------------------------------------------------------
SEED = 42
random.seed(SEED)

BASE_DIR = 'dataset'
CSV_DIR = os.path.join(BASE_DIR, 'csv')
CARDS_DIR = os.path.join(BASE_DIR, 'cards')
POLICIES_DIR = 'policies'

for split in ['train', 'validation', 'test']:
    for cls in ['valid', 'invalid', 'manual_review']:
        os.makedirs(os.path.join(CARDS_DIR, split, cls), exist_ok=True)
os.makedirs(CSV_DIR, exist_ok=True)
os.makedirs(POLICIES_DIR, exist_ok=True)

# ---------------------------------------------------------
# FULL SRS-COMPLIANT WARRANTY POLICIES DEFINITIONS
# ---------------------------------------------------------
POLICIES = {
    'Smartphone': {
        "product_category": "Smartphone",
        "coverage_duration_months": 12,
        "warranty_start_conditions": ["Valid purchase receipt from authorized seller", "Original serial number intact"],
        "covered_faults": {
            "Manufacturing Defect": "Internal motherboard defect causing bootloop.",
            "Screen Defect (Non-Impact)": "Touch failure or dead pixels with no physical drop.",
            "Battery Manufacturing Defect": "Battery swelling or sudden degradation.",
            "Charging Port Failure": "Charging connector failure under normal usage."
        },
        "exclusions": {
            "Physical Damage": "Cracked screen or casing from impact.",
            "Liquid Damage": "Liquid contact indicator triggered.",
            "Unauthorized Repair": "Device opened by third-party technician."
        },
        "claim_reporting_period_days": 30,
        "repair_conditions": ["Authorized service centre inspection mandatory"],
        "authorized_service_centre_required": True,
        "replacement_conditions": {"eligible_after_repairs": 2, "unrepairable_covered_fault": True},
        "grace_period_days": 7,
        "mandatory_documents": ["Purchase Receipt", "Warranty Card", "Serial Number Photo"],
        "hard_fail_rules": ["Warranty expired", "Liquid damage present", "Unauthorized repair detected"],
        "warning_rules": ["Claim submitted within grace period", "Minor cosmetic wear"],
        "manual_review_rules": ["Receipt serial mismatch", "Inconsistent claim date", "Duplicate claim detected"],
        "brands": ['TechCorp', 'MobileX', 'ApexPhone'],
        "models": ['SP-100', 'SP-200', 'SP-X']
    },
    'Laptop': {
        "product_category": "Laptop",
        "coverage_duration_months": 24,
        "warranty_start_conditions": ["Valid purchase receipt from authorized seller"],
        "covered_faults": {
            "Motherboard Defect": "Component failure on main board.",
            "Keyboard Failure": "Multiple keys non-functional.",
            "Display Failure": "Backlight failure without screen crack.",
            "Factory SSD Failure": "Primary storage failure."
        },
        "exclusions": {
            "Physical Damage": "Hinge broken or chassis damage.",
            "Liquid Damage": "Liquid spill marks internal.",
            "Unauthorized Modification": "RAM/SSD force modification damage."
        },
        "claim_reporting_period_days": 45,
        "repair_conditions": ["Manufacturer original parts required"],
        "authorized_service_centre_required": True,
        "replacement_conditions": {"eligible_after_repairs": 3, "unrepairable_covered_fault": True},
        "grace_period_days": 14,
        "mandatory_documents": ["Purchase Receipt", "Serial Number Photo", "Technical Diagnostic Report"],
        "hard_fail_rules": ["Warranty expired", "Liquid damage", "Unauthorized modification"],
        "warning_rules": ["Battery health degradation under 80%"],
        "manual_review_rules": ["Hardware modification status unclear", "Conflicting repair records"],
        "brands": ['ProBook', 'UltraTech', 'OmniLap'],
        "models": ['LP-500', 'LP-900', 'LP-Pro']
    },
    'Television': {
        "product_category": "Television",
        "coverage_duration_months": 18,
        "warranty_start_conditions": ["Authorized retailer purchase receipt"],
        "covered_faults": {
            "Display Panel Defect": "Internal panel line defect.",
            "Power Supply Failure": "Internal power board failure.",
            "Main Board Defect": "Smart hub system failure."
        },
        "exclusions": {
            "Cracked Screen": "External screen crack from impact.",
            "Electrical Surge": "High voltage power surge damage.",
            "Liquid Damage": "Liquid intrusion."
        },
        "claim_reporting_period_days": 30,
        "repair_conditions": ["On-site inspection by authorized technician"],
        "authorized_service_centre_required": True,
        "replacement_conditions": {"eligible_after_repairs": 2, "unrepairable_covered_fault": True},
        "grace_period_days": 10,
        "mandatory_documents": ["Purchase Receipt", "Product ID Tag Photo"],
        "hard_fail_rules": ["Warranty expired", "Cracked screen", "Electrical surge"],
        "warning_rules": ["Claim reported near expiry date"],
        "manual_review_rules": ["Surge evidence inconclusive", "Serial mismatch"],
        "brands": ['VisionMax', 'ViewOptics', 'CineDisplay'],
        "models": ['TV-43U', 'TV-55OLED', 'TV-65Q']
    }
}

# Export full Policies to JSON
for cat, policy in POLICIES.items():
    file_path = os.path.join(POLICIES_DIR, f"{cat.lower()}_warranty_policy.json")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(policy, f, indent=2)

# ---------------------------------------------------------
# CLAIM DATA GENERATOR (V2 STRICT LOGIC)
# ---------------------------------------------------------
def generate_all_claims():
    categories = ['Smartphone', 'Laptop', 'Television']
    classes = ['Valid Claim', 'Invalid Claim', 'Manual Review']
    counts = {
        'Smartphone': {'Valid Claim': 167, 'Invalid Claim': 167, 'Manual Review': 166},
        'Laptop':     {'Valid Claim': 167, 'Invalid Claim': 167, 'Manual Review': 166},
        'Television': {'Valid Claim': 166, 'Invalid Claim': 166, 'Manual Review': 168}
    }

    claims = []
    claim_counter = 1
    generated_serials = {}  # for duplicate control

    for cat in categories:
        policy = POLICIES[cat]
        for cls in classes:
            num_claims = counts[cat][cls]
            for i in range(num_claims):
                cid = f"CLM-{claim_counter:04d}"
                pid = f"PRD-{claim_counter:05d}"
                sn = f"SN-{cat[0]}-{claim_counter:06d}"
                receipt_sn = sn

                brand = random.choice(policy['brands'])
                model = random.choice(policy['models'])
                base_purchase = datetime(2025, 1, 1) + timedelta(days=random.randint(0, 150))
                warranty_months = policy['coverage_duration_months']

                # Defaults
                physical_damage = False
                liquid_damage = False
                unauthorized_repair = False
                receipt_available = True
                receipt_valid = True
                purchase_information_consistent = True
                supporting_evidence_available = True
                evidence_consistency = True
                duplicate_claim = False
                contradiction_detected = False
                authorized_service_center = True
                repair_history = 'No previous repairs'
                previous_repair_count = 0
                last_repair_date = 'N/A'
                previous_replacement = False
                previous_replacement_count = 0
                previous_replacement_date = 'N/A'
                missing_documents = []

                # Target-Specific Scenario Assignment
                if cls == 'Valid Claim':
                    warranty_status = 'Active'
                    fault_category, fault_description = random.choice(list(policy['covered_faults'].items()))
                   
                    # Boundary date scenarios (10% of valid claims)
                    if i % 10 == 0:
                        fault_date = base_purchase + timedelta(days=(warranty_months * 30) - 1)
                        claim_date = fault_date + timedelta(days=policy['claim_reporting_period_days'])
                    else:
                        fault_date = base_purchase + timedelta(days=random.randint(20, 100))
                        claim_date = fault_date + timedelta(days=random.randint(1, 15))

                    if i % 4 == 0:
                        repair_history = 'One authorized repair'
                        previous_repair_count = 1
                        last_repair_date = (fault_date - timedelta(days=30)).strftime('%Y-%m-%d')

                    replacement_requested = random.choice([True, False])

                elif cls == 'Invalid Claim':
                    invalid_type = random.choice(['expired', 'exclusion', 'invalid_receipt', 'contradiction'])
                   
                    if invalid_type == 'expired':
                        warranty_status = 'Expired'
                        fault_category, fault_description = random.choice(list(policy['covered_faults'].items()))
                        fault_date = base_purchase + timedelta(days=(warranty_months * 30) + random.randint(5, 40))
                        claim_date = fault_date + timedelta(days=5)
                    elif invalid_type == 'exclusion':
                        warranty_status = 'Active'
                        exclusion_type = random.choice(list(policy['exclusions'].keys()))
                        fault_category = exclusion_type
                        fault_description = policy['exclusions'][exclusion_type]
                        fault_date = base_purchase + timedelta(days=30)
                        claim_date = fault_date + timedelta(days=5)
                        if 'Physical' in exclusion_type: physical_damage = True
                        elif 'Liquid' in exclusion_type: liquid_damage = True
                        else: unauthorized_repair = True
                    elif invalid_type == 'invalid_receipt':
                        warranty_status = 'Active'
                        fault_category, fault_description = random.choice(list(policy['covered_faults'].items()))
                        fault_date = base_purchase + timedelta(days=30)
                        claim_date = fault_date + timedelta(days=5)
                        receipt_valid = False
                        purchase_information_consistent = False
                        missing_documents.append("Valid Purchase Receipt")
                    else: # Contradiction (e.g. Fault before purchase date)
                        warranty_status = 'Active'
                        fault_category, fault_description = random.choice(list(policy['covered_faults'].items()))
                        fault_date = base_purchase - timedelta(days=10)
                        claim_date = base_purchase + timedelta(days=5)
                        contradiction_detected = True

                    replacement_requested = False

                else: # Manual Review
                    warranty_status = 'Active'
                    fault_category, fault_description = random.choice(list(policy['covered_faults'].items()))
                    fault_date = base_purchase + timedelta(days=40)
                    claim_date = fault_date + timedelta(days=5)

                    review_type = random.choice(['missing_docs', 'serial_mismatch', 'duplicate', 'repair_conflict'])
                    if review_type == 'missing_docs':
                        missing_documents = ["Warranty Card", "Diagnostic Report"]
                        supporting_evidence_available = False
                    elif review_type == 'serial_mismatch':
                        receipt_sn = f"SN-{cat[0]}-999999"
                        evidence_consistency = False
                    elif review_type == 'duplicate':
                        duplicate_claim = True
                    else:
                        repair_history = 'Unauthorized repair attempt reported'
                        previous_repair_count = 1
                        last_repair_date = (fault_date - timedelta(days=5)).strftime('%Y-%m-%d')
                        authorized_service_center = False

                    replacement_requested = random.choice([True, False])

                # Calculations
                product_age_days = (claim_date - base_purchase).days
                warranty_expiry_date = base_purchase + timedelta(days=warranty_months * 30)
                warranty_remaining_days = max(0, (warranty_expiry_date - claim_date).days)
                reporting_period_days = (claim_date - fault_date).days
                claim_reporting_within_period = reporting_period_days <= policy['claim_reporting_period_days']
                serial_number_status = 'Matched' if sn == receipt_sn else 'Mismatch'

                # RULE ENGINE EVALUATION (Calculated indicators, separated from ML Raw Facts)
                hard_fail = (
                    warranty_status == 'Expired' or physical_damage or liquid_damage or
                    unauthorized_repair or not receipt_valid or contradiction_detected
                )
                warning = (
                    reporting_period_days == policy['claim_reporting_period_days'] or
                    warranty_remaining_days <= 7
                )
                manual_review = (
                    len(missing_documents) > 0 or serial_number_status == 'Mismatch' or
                    duplicate_claim or not authorized_service_center
                )
                replacement_eligible = (
                    replacement_requested and not hard_fail and warranty_status == 'Active' and previous_repair_count >= 1
                )

                claims.append({
                    # RAW FACTS (ML Features)
                    'claim_id': cid,
                    'product_id': pid,
                    'product_category': cat,
                    'brand': brand,
                    'model': model,
                    'serial_number': sn,
                    'receipt_serial_number': receipt_sn,
                    'serial_number_status': serial_number_status,
                    'purchase_date': base_purchase.strftime('%Y-%m-%d'),
                    'fault_date': fault_date.strftime('%Y-%m-%d'),
                    'claim_date': claim_date.strftime('%Y-%m-%d'),
                    'product_age_days': product_age_days,
                    'warranty_duration_months': warranty_months,
                    'warranty_remaining_days': warranty_remaining_days,
                    'warranty_status': warranty_status,
                    'fault_category': fault_category,
                    'fault_description': fault_description,
                    'physical_damage': physical_damage,
                    'liquid_damage': liquid_damage,
                    'unauthorized_repair': unauthorized_repair,
                    'repair_history': repair_history,
                    'previous_repair_count': previous_repair_count,
                    'last_repair_date': last_repair_date,
                    'previous_replacement': previous_replacement,
                    'previous_replacement_count': previous_replacement_count,
                    'previous_replacement_date': previous_replacement_date,
                    'authorized_service_center': authorized_service_center,
                    'receipt_available': receipt_available,
                    'receipt_valid': receipt_valid,
                    'purchase_information_consistent': purchase_information_consistent,
                    'missing_documents': "|".join(missing_documents) if missing_documents else "None",
                    'missing_documents_count': len(missing_documents),
                    'supporting_evidence_available': supporting_evidence_available,
                    'evidence_consistency': evidence_consistency,
                    'duplicate_claim': duplicate_claim,
                    'contradiction_detected': contradiction_detected,
                    'claim_reporting_within_period': claim_reporting_within_period,
                    'replacement_requested': replacement_requested,

                    # RULE ENGINE OUTPUTS (Separated from direct ML Input)
                    'replacement_eligible': replacement_eligible,
                    'hard_fail_detected': hard_fail,
                    'warning_detected': warning,
                    'manual_review_trigger': manual_review,

                    # TARGET CLASS
                    'claim_class': cls
                })
                claim_counter += 1

    return claims

# ---------------------------------------------------------
# CARD GENERATOR (RICH FACTS, NO PREDICTIONS)
# ---------------------------------------------------------
def generate_claim_card_image(claim_data, output_path, variant=1):
    width, height = 700, 500
    bg = (255, 255, 255) if variant == 1 else (242, 246, 250)
    header_fill = (20, 50, 90) if variant == 1 else (30, 70, 110)
   
    img = Image.new('RGB', (width, height), color=bg)
    draw = ImageDraw.Draw(img)
   
    draw.rectangle([(0, 0), (width, 45)], fill=header_fill)
    draw.text((15, 12), f"ASSUREX CLAIM CARD - ID: {claim_data['claim_id']} [{claim_data['product_category']}]", fill=(255, 255, 255))
   
    facts = [
        f"Product: {claim_data['brand']} {claim_data['model']} | Age: {claim_data['product_age_days']} days",
        f"Serial SN: {claim_data['serial_number']} | Receipt SN: {claim_data['receipt_serial_number']} ({claim_data['serial_number_status']})",
        f"Dates: Purchased {claim_data['purchase_date']} | Fault {claim_data['fault_date']} | Claimed {claim_data['claim_date']}",
        f"Warranty Status: {claim_data['warranty_status']} ({claim_data['warranty_remaining_days']} days remaining)",
        f"Fault Claimed: {claim_data['fault_category']}",
        f"Description: {claim_data['fault_description'][:60]}...",
        f"Flags: Phys Damage={claim_data['physical_damage']} | Liq Damage={claim_data['liquid_damage']} | Unauth Repair={claim_data['unauthorized_repair']}",
        f"Repair History: {claim_data['repair_history']} (Prev Repairs: {claim_data['previous_repair_count']})",
        f"Receipt Valid: {claim_data['receipt_valid']} | Missing Docs: {claim_data['missing_documents']}",
        f"Contradiction: {claim_data['contradiction_detected']} | Duplicate Flag: {claim_data['duplicate_claim']}"
    ]
   
    y = 60
    for text in facts:
        draw.text((20, y), text, fill=(25, 25, 25))
        y += 42
       
    img.save(output_path)

# ---------------------------------------------------------
# VERIFICATION SUITE
# ---------------------------------------------------------
def verify_dataset(claims_pool, splits, mapping_rows):
    print("\n--- RUNNING STRICT ASSUREX VERIFICATION SUITE ---")
   
    # 1. Total & Uniqueness Checks
    assert len(claims_pool) == 1500, f"Error: Total claims count is {len(claims_pool)}, expected 1500."
    unique_cids = set(c['claim_id'] for c in claims_pool)
    assert len(unique_cids) == 1500, "Error: Duplicate Claim IDs detected!"

    # 2. Stratified Split Counts Check
    assert len(splits['train']) == 1050, f"Train count error: {len(splits['train'])}"
    assert len(splits['validation']) == 225, f"Validation count error: {len(splits['validation'])}"
    assert len(splits['test']) == 225, f"Test count error: {len(splits['test'])}"

    # 3. Data Leakage (No ID across splits)
    train_ids = set(c['claim_id'] for c in splits['train'])
    val_ids = set(c['claim_id'] for c in splits['validation'])
    test_ids = set(c['claim_id'] for c in splits['test'])
    assert train_ids.isdisjoint(val_ids), "LEAKAGE DETECTED: Train & Validation overlap!"
    assert train_ids.isdisjoint(test_ids), "LEAKAGE DETECTED: Train & Test overlap!"
    assert val_ids.isdisjoint(test_ids), "LEAKAGE DETECTED: Validation & Test overlap!"

    # 4. Policy File Checks
    for cat in ['smartphone', 'laptop', 'television']:
        policy_path = os.path.join(POLICIES_DIR, f"{cat}_warranty_policy.json")
        assert os.path.exists(policy_path), f"Missing policy file: {policy_path}"
        with open(policy_path, 'r', encoding='utf-8') as f:
            pdata = json.load(f)
            required_keys = [
                "product_category", "coverage_duration_months", "warranty_start_conditions",
                "covered_faults", "exclusions", "claim_reporting_period_days", "repair_conditions",
                "authorized_service_centre_required", "replacement_conditions", "grace_period_days",
                "mandatory_documents", "hard_fail_rules", "warning_rules", "manual_review_rules"
            ]
            for key in required_keys:
                assert key in pdata, f"Policy {cat} missing SRS required field: {key}"

    # 5. Card Image Variations Count
    train_cards = [m for m in mapping_rows if m['split'] == 'train']
    val_cards = [m for m in mapping_rows if m['split'] == 'validation']
    test_cards = [m for m in mapping_rows if m['split'] == 'test']
   
    assert len(train_cards) == 2100, f"Training cards count error: {len(train_cards)}, expected 2100."
    assert len(val_cards) == 225, f"Validation cards count error: {len(val_cards)}, expected 225."
    assert len(test_cards) == 225, f"Test cards count error: {len(test_cards)}, expected 225."

    print("[ALL VERIFICATION CHECKS PASSED SUCCESSFULLY]")

# ---------------------------------------------------------
# MAIN EXECUTION
# ---------------------------------------------------------
def main():
    print("Generating Fully Compliant AssureX Dataset V2...")
    claims_pool = generate_all_claims()
    random.shuffle(claims_pool)

    # Stratified Split
    stratified = {'Valid Claim': [], 'Invalid Claim': [], 'Manual Review': []}
    for c in claims_pool:
        stratified[c['claim_class']].append(c)

    splits = {'train': [], 'validation': [], 'test': []}
    for cls, records in stratified.items():
        splits['train'].extend(records[:350])
        splits['validation'].extend(records[350:425])
        splits['test'].extend(records[425:])

    mapping_rows = []

    for split_name, records in splits.items():
        csv_path = os.path.join(CSV_DIR, f"{split_name}.csv")
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

        for claim in records:
            cls_dir = claim['claim_class'].lower().replace(' ', '_')
            if cls_dir == 'valid_claim': cls_dir = 'valid'
            elif cls_dir == 'invalid_claim': cls_dir = 'invalid'

            variations = 2 if split_name == 'train' else 1
            for v in range(1, variations + 1):
                img_name = f"{claim['claim_id']}_v{v}.png" if split_name == 'train' else f"{claim['claim_id']}.png"
                img_path = os.path.join(CARDS_DIR, split_name, cls_dir, img_name)

                generate_claim_card_image(claim, img_path, variant=v)

                mapping_rows.append({
                    'claim_id': claim['claim_id'],
                    'split': split_name,
                    'claim_class': claim['claim_class'],
                    'image_filename': img_name,
                    'image_path': img_path
                })

    # Save Mapping CSV
    with open(os.path.join(BASE_DIR, 'claim_image_mapping.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['claim_id', 'split', 'claim_class', 'image_filename', 'image_path'])
        writer.writeheader()
        writer.writerows(mapping_rows)

    # Run Strict Verification
    verify_dataset(claims_pool, splits, mapping_rows)

if __name__ == '__main__':
    main()