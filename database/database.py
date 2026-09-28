import os
import json
from datetime import date, datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from werkzeug.security import generate_password_hash

app = Flask(__name__)

DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "assurex")

# MySQL is the primary datastore. ASSUREX_DATABASE_URL overrides it, which lets
# an evaluator run the application with no database server installed, for
# example:  ASSUREX_DATABASE_URL=sqlite:///assurex.db  py -3 app.py
DATABASE_URL = os.getenv("ASSUREX_DATABASE_URL") or "sqlite:///assurex.db"

SERVER_DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/?charset=utf8mb4"
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.Enum(
            "Customer",
            "Service-center employee",
            "Claim reviewer",
            "Administrator",
            name="user_roles",
        ),
        nullable=False,
        default="Customer",
    )
    phone = db.Column(db.String(30), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    products = db.relationship("Product", back_populates="owner", cascade="all, delete-orphan")
    claims = db.relationship("Claim", back_populates="user")
    review_actions = db.relationship("ReviewAction", back_populates="reviewer")


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False, index=True)
    brand = db.Column(db.String(100), nullable=False)
    model_number = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(150), nullable=False, index=True)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_price = db.Column(db.Numeric(12, 2), nullable=False)
    retailer = db.Column(db.String(150), nullable=False)
    warranty_duration_months = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    owner = db.relationship("User", back_populates="products")
    warranties = db.relationship("Warranty", back_populates="product", cascade="all, delete-orphan")
    claims = db.relationship("Claim", back_populates="product")


class WarrantyPolicy(db.Model):
    __tablename__ = "warranty_policies"

    id = db.Column(db.Integer, primary_key=True)
    policy_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    policy_name = db.Column(db.String(150), nullable=False)
    product_category = db.Column(db.String(100), nullable=False, index=True)
    coverage_duration_months = db.Column(db.Integer, nullable=False)
    warranty_start_conditions = db.Column(db.JSON, nullable=False)
    covered_faults = db.Column(db.JSON, nullable=False)
    exclusions = db.Column(db.JSON, nullable=False)
    claim_reporting_period_days = db.Column(db.Integer, nullable=False)
    repair_conditions = db.Column(db.JSON, nullable=False)
    authorized_service_center_requirements = db.Column(db.JSON, nullable=False)
    replacement_conditions = db.Column(db.JSON, nullable=False)
    grace_period_days = db.Column(db.Integer, nullable=False, default=0)
    mandatory_documents = db.Column(db.JSON, nullable=False)
    hard_fail_rules = db.Column(db.JSON, nullable=False)
    warning_rules = db.Column(db.JSON, nullable=False)
    manual_review_rules = db.Column(db.JSON, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    warranties = db.relationship("Warranty", back_populates="policy")


class Warranty(db.Model):
    __tablename__ = "warranties"

    id = db.Column(db.Integer, primary_key=True)
    warranty_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    policy_id = db.Column(db.Integer, db.ForeignKey("warranty_policies.id"), nullable=False)
    provider = db.Column(db.String(150), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    coverage_conditions = db.Column(db.JSON, nullable=False)
    exclusions = db.Column(db.JSON, nullable=False)
    service_center_information = db.Column(db.JSON, nullable=False)
    status = db.Column(
        db.Enum("Active", "Expired", "Approaching Expiry", name="warranty_statuses"),
        nullable=False,
        default="Active",
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    product = db.relationship("Product", back_populates="warranties")
    policy = db.relationship("WarrantyPolicy", back_populates="warranties")
    claims = db.relationship("Claim", back_populates="warranty")


class Claim(db.Model):
    __tablename__ = "claims"

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False, index=True)
    warranty_id = db.Column(db.Integer, db.ForeignKey("warranties.id"), nullable=False)
    product_age_days = db.Column(db.Integer, nullable=True)
    purchase_details = db.Column(db.JSON, nullable=True)
    fault_occurrence_date = db.Column(db.Date, nullable=False)
    fault_description = db.Column(db.Text, nullable=False)
    damage_type = db.Column(db.String(100), nullable=False)
    warranty_conditions = db.Column(db.JSON, nullable=True)
    service_history = db.Column(db.JSON, nullable=True)
    previous_replacement_information = db.Column(db.JSON, nullable=True)
    submission_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(
        db.Enum(
            "Draft",
            "Submitted",
            "Under Evaluation",
            "Additional Information Required",
            "Manual Review",
            "Approved",
            "Rejected",
            "Closed",
            name="claim_statuses",
        ),
        nullable=False,
        default="Draft",
        index=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user = db.relationship("User", back_populates="claims")
    product = db.relationship("Product", back_populates="claims")
    warranty = db.relationship("Warranty", back_populates="claims")
    documents = db.relationship("Document", back_populates="claim", cascade="all, delete-orphan")
    repair_history = db.relationship(
        "RepairHistory", back_populates="claim", cascade="all, delete-orphan"
    )
    evaluations = db.relationship(
        "Evaluation", back_populates="claim", cascade="all, delete-orphan"
    )
    review_actions = db.relationship(
        "ReviewAction", back_populates="claim", cascade="all, delete-orphan"
    )


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True, index=True)
    document_type = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(500), nullable=False)
    file_extension = db.Column(db.String(10), nullable=False)
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    secure_file_hash = db.Column(db.String(128), nullable=False, index=True)
    ocr_text = db.Column(db.Text, nullable=True)
    extracted_fields = db.Column(db.JSON, nullable=True)
    verified_by_user = db.Column(db.Boolean, nullable=False, default=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    claim = db.relationship("Claim", back_populates="documents")


class RepairHistory(db.Model):
    __tablename__ = "repair_history"

    id = db.Column(db.Integer, primary_key=True)
    repair_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id"), nullable=False, index=True)
    repair_date = db.Column(db.Date, nullable=False)
    service_center_name = db.Column(db.String(150), nullable=True)
    authorized_service_center = db.Column(db.Boolean, nullable=False, default=False)
    repair_description = db.Column(db.Text, nullable=True)
    parts_replaced = db.Column(db.JSON, nullable=True)
    repair_cost = db.Column(db.Numeric(12, 2), nullable=True)
    repair_document_id = db.Column(db.Integer, db.ForeignKey("documents.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    claim = db.relationship("Claim", back_populates="repair_history")


class Evaluation(db.Model):
    __tablename__ = "evaluations"

    id = db.Column(db.Integer, primary_key=True)
    evaluation_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id"), nullable=False, index=True)

    python_prediction = db.Column(
        db.Enum("Valid Claim", "Invalid Claim", "Manual Review", name="model_predictions"),
        nullable=True,
    )
    python_valid_confidence = db.Column(db.Float, nullable=True)
    python_invalid_confidence = db.Column(db.Float, nullable=True)
    python_manual_review_confidence = db.Column(db.Float, nullable=True)

    teachable_prediction = db.Column(
        db.Enum("Valid Claim", "Invalid Claim", "Manual Review", name="tm_predictions"),
        nullable=True,
    )
    teachable_valid_confidence = db.Column(db.Float, nullable=True)
    teachable_invalid_confidence = db.Column(db.Float, nullable=True)
    teachable_manual_review_confidence = db.Column(db.Float, nullable=True)

    prediction_match = db.Column(db.Boolean, nullable=True)
    confidence_difference = db.Column(db.Float, nullable=True)
    model_consistency = db.Column(
        db.Enum("Consistent", "Inconsistent", "Uncertain", name="model_consistency"),
        nullable=True,
    )

    warranty_result = db.Column(db.String(100), nullable=True)
    missing_documents = db.Column(db.JSON, nullable=True)
    contradictions = db.Column(db.JSON, nullable=True)
    duplicate_indicator = db.Column(db.Boolean, nullable=True)
    rule_result = db.Column(db.String(100), nullable=True)

    final_decision = db.Column(
        db.Enum(
            "Likely Valid",
            "Likely Invalid",
            "Manual Review Required",
            name="final_decisions",
        ),
        nullable=True,
    )
    explanation = db.Column(db.Text, nullable=True)
    reviewer_comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    claim = db.relationship("Claim", back_populates="evaluations")


class ReviewAction(db.Model):
    __tablename__ = "review_actions"

    id = db.Column(db.Integer, primary_key=True)
    action_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("claims.id"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(
        db.Enum(
            "Approve",
            "Reject",
            "Request Additional Information",
            "Override",
            name="review_actions",
        ),
        nullable=False,
    )
    comments = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    claim = db.relationship("Claim", back_populates="review_actions")
    reviewer = db.relationship("User", back_populates="review_actions")


def create_database():
    """Create the MySQL schema. A no-op when running on SQLite."""
    if IS_SQLITE:
        return

    import pymysql

    connection = pymysql.connect(
        host=DB_HOST,
        port=int(DB_PORT),
        user=DB_USER,
        password=DB_PASSWORD,
        charset="utf8mb4",
        autocommit=True,
    )

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        connection.close()


def create_tables():
    with app.app_context():
        db.create_all()


def seed_default_policies():
    policies = [
        {
            "policy_id": "POL-001",
            "policy_name": "Electronics Standard Warranty",
            "product_category": "Electronics",
            "coverage_duration_months": 12,
            "warranty_start_conditions": {
                "start": "purchase_date",
                "activation_required": False,
            },
            "covered_faults": ["manufacturing defect", "hardware failure"],
            "exclusions": ["accidental damage", "liquid damage", "unauthorized repair"],
            "claim_reporting_period_days": 30,
            "repair_conditions": {
                "repair_allowed": True,
                "authorized_service_center_required": True,
            },
            "authorized_service_center_requirements": {
                "required": True
            },
            "replacement_conditions": {
                "allowed_when_repair_is_not_viable": True
            },
            "grace_period_days": 7,
            "mandatory_documents": ["receipt", "warranty_card", "serial_number_evidence"],
            "hard_fail_rules": ["serial_mismatch", "unauthorized_repair"],
            "warning_rules": ["missing_optional_evidence"],
            "manual_review_rules": ["contradictory_information", "uncertain_model_result"],
        },
        {
            "policy_id": "POL-002",
            "policy_name": "Home Appliance Standard Warranty",
            "product_category": "Home Appliances",
            "coverage_duration_months": 24,
            "warranty_start_conditions": {
                "start": "purchase_date",
                "activation_required": False,
            },
            "covered_faults": ["manufacturing defect", "electrical failure", "mechanical failure"],
            "exclusions": ["physical abuse", "liquid damage", "unauthorized modification"],
            "claim_reporting_period_days": 30,
            "repair_conditions": {
                "repair_allowed": True,
                "authorized_service_center_required": True,
            },
            "authorized_service_center_requirements": {
                "required": True
            },
            "replacement_conditions": {
                "allowed_after_repeated_failed_repairs": True
            },
            "grace_period_days": 14,
            "mandatory_documents": ["receipt", "warranty_card"],
            "hard_fail_rules": ["serial_mismatch", "unauthorized_repair"],
            "warning_rules": ["missing_repair_record"],
            "manual_review_rules": ["contradictory_information", "boundary_date"],
        },
        {
            "policy_id": "POL-003",
            "policy_name": "Mobile Device Standard Warranty",
            "product_category": "Mobile Devices",
            "coverage_duration_months": 12,
            "warranty_start_conditions": {
                "start": "purchase_date",
                "activation_required": True,
            },
            "covered_faults": ["manufacturing defect", "hardware failure"],
            "exclusions": ["screen_damage", "liquid_damage", "unauthorized_repair"],
            "claim_reporting_period_days": 14,
            "repair_conditions": {
                "repair_allowed": True,
                "authorized_service_center_required": True,
            },
            "authorized_service_center_requirements": {
                "required": True
            },
            "replacement_conditions": {
                "allowed_when_repair_is_not_viable": True
            },
            "grace_period_days": 7,
            "mandatory_documents": ["receipt", "serial_number_evidence"],
            "hard_fail_rules": ["serial_mismatch", "unauthorized_repair"],
            "warning_rules": ["missing_optional_evidence"],
            "manual_review_rules": ["contradictory_information", "uncertain_model_result"],
        },
    ]

    with app.app_context():
        for data in policies:
            existing = WarrantyPolicy.query.filter_by(policy_id=data["policy_id"]).first()
            if existing is None:
                db.session.add(WarrantyPolicy(**data))

        db.session.commit()


def initialize_database(seed_policies=True):
    create_database()
    create_tables()

    if seed_policies:
        seed_default_policies()


if __name__ == "__main__":
    initialize_database(seed_policies=True)
    print(f"AssureX MySQL database '{DB_NAME}' and required tables are ready.")
    print("Three configurable warranty policies were inserted if they did not already exist.")
