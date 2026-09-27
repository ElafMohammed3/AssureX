from flask import Flask, render_template, request, jsonify
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from urllib.parse import quote_plus
import os


# ============================================================
# FLASK CONFIGURATION
# ============================================================

app = Flask(__name__)

app.config["JSON_SORT_KEYS"] = False


# ============================================================
# DATABASE CONFIGURATION
# ============================================================
#
# OPTION 1:
# Put your MySQL connection values here.
#
# OPTION 2:
# Use environment variables.
#
# Example:
# DB_USER=root
# DB_PASSWORD=1234
# DB_HOST=localhost
# DB_PORT=3306
# DB_NAME=assurex
#

DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "assurex")


DATABASE_URL = (
    f"mysql+pymysql://"
    f"{quote_plus(DB_USER)}:"
    f"{quote_plus(DB_PASSWORD)}@"
    f"{DB_HOST}:{DB_PORT}/"
    f"{DB_NAME}"
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600
)


# ============================================================
# DATABASE TABLE NAMES
# ============================================================
#
# IMPORTANT:
# Change these ONLY if your datapy uses different names.
#

CLAIMS_TABLE = "claims"
PRODUCTS_TABLE = "products"
USERS_TABLE = "users"
PREDICTIONS_TABLE = "predictions"


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def query_database(query, params=None):
    """
    Execute a SELECT query and return rows as dictionaries.
    """

    try:
        with engine.connect() as connection:

            result = connection.execute(
                text(query),
                params or {}
            )

            return [
                dict(row._mapping)
                for row in result
            ]

    except SQLAlchemyError as error:

        print("DATABASE ERROR:")
        print(error)

        return []


def execute_database(query, params=None):
    """
    Execute INSERT / UPDATE / DELETE queries.
    """

    try:

        with engine.begin() as connection:

            result = connection.execute(
                text(query),
                params or {}
            )

            return result.rowcount

    except SQLAlchemyError as error:

        print("DATABASE ERROR:")
        print(error)

        return 0


# ============================================================
# STATUS CLASSIFICATION
# ============================================================

def status_class(status):

    if not status:
        return "badge-review"

    status = str(status).lower()

    if "valid" in status and "invalid" not in status:
        return "badge-valid"

    if "invalid" in status:
        return "badge-invalid"

    return "badge-review"


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route("/")
def home():

    return dashboard()


@app.route("/admin/dashboard")
def dashboard():

    # --------------------------------------------------------
    # BASIC CLAIM COUNTS
    # --------------------------------------------------------

    total_claims = query_database(
        f"""
        SELECT COUNT(*) AS total
        FROM {CLAIMS_TABLE}
        """
    )

    valid_claims = query_database(
        f"""
        SELECT COUNT(*) AS total
        FROM {CLAIMS_TABLE}
        WHERE LOWER(final_status) IN
        ('likely valid', 'valid claim', 'approved')
        """
    )

    invalid_claims = query_database(
        f"""
        SELECT COUNT(*) AS total
        FROM {CLAIMS_TABLE}
        WHERE LOWER(final_status) IN
        ('likely invalid', 'invalid claim', 'rejected')
        """
    )

    manual_review = query_database(
        f"""
        SELECT COUNT(*) AS total
        FROM {CLAIMS_TABLE}
        WHERE LOWER(final_status) IN
        (
            'manual review',
            'manual review required'
        )
        """
    )


    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    duplicate_alerts = query_database(
        f"""
        SELECT COUNT(*) AS total
        FROM {CLAIMS_TABLE}
        WHERE duplicate_indicator = 1
        """
    )


    # --------------------------------------------------------
    # MODEL DISAGREEMENTS
    # --------------------------------------------------------

    model_disagreements = query_database(
        f"""
        SELECT COUNT(*) AS total
        FROM {CLAIMS_TABLE}
        WHERE LOWER(model_consistency_status)
        IN ('model disagreement', 'disagreement')
        """
    )


    # --------------------------------------------------------
    # AVERAGE PYTHON CONFIDENCE
    # --------------------------------------------------------

    python_confidence = query_database(
        f"""
        SELECT AVG(python_confidence) AS average
        FROM {CLAIMS_TABLE}
        """
    )


    # --------------------------------------------------------
    # AVERAGE TEACHABLE MACHINE CONFIDENCE
    # --------------------------------------------------------

    tm_confidence = query_database(
        f"""
        SELECT AVG(teachable_machine_confidence) AS average
        FROM {CLAIMS_TABLE}
        """
    )


    # --------------------------------------------------------
    # LATEST CLAIMS
    # --------------------------------------------------------

    latest_claims = query_database(
        f"""
        SELECT
            claim_id,
            product_id,
            python_prediction,
            python_confidence,
            teachable_machine_prediction,
            teachable_machine_confidence,
            confidence_difference,
            rule_engine_result,
            final_status

        FROM {CLAIMS_TABLE}

        ORDER BY claim_id DESC

        LIMIT 10
        """
    )


    # --------------------------------------------------------
    # BUILD STATISTICS OBJECT
    # --------------------------------------------------------

    stats = {

        "total_claims":
            total_claims[0]["total"]
            if total_claims else 0,

        "valid_claims":
            valid_claims[0]["total"]
            if valid_claims else 0,

        "invalid_claims":
            invalid_claims[0]["total"]
            if invalid_claims else 0,

        "manual_review":
            manual_review[0]["total"]
            if manual_review else 0,

        "duplicate_alerts":
            duplicate_alerts[0]["total"]
            if duplicate_alerts else 0,

        "model_disagreements":
            model_disagreements[0]["total"]
            if model_disagreements else 0,

        "python_confidence":
            round(
                float(python_confidence[0]["average"] or 0) * 100,
                1
            )
            if python_confidence else 0,

        "tm_confidence":
            round(
                float(tm_confidence[0]["average"] or 0) * 100,
                1
            )
            if tm_confidence else 0
    }


    return render_template(
        "admin_dashboard.html",
        stats=stats,
        claims=latest_claims
    )


# ============================================================
# ALL CLAIMS QUEUE
# ============================================================

@app.route("/admin/claims")
def all_claims():
    search = request.args.get( "search", "").strip()

    category = request.args.get("category","" ).strip()

    status = request.args.get("status", "" ).strip()


    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = f"""
        SELECT

            c.claim_id,

            c.product_id,

            c.submission_date,

            c.python_prediction,

            c.python_confidence,

            c.teachable_machine_prediction,

            c.teachable_machine_confidence,

            c.final_status,

            u.user_id,

            u.name AS claimant_name,

            p.product_name,

            p.category,

            p.serial_number

        FROM {CLAIMS_TABLE} c

        LEFT JOIN {USERS_TABLE} u
            ON c.user_id = u.user_id

        LEFT JOIN {PRODUCTS_TABLE} p
            ON c.product_id = p.product_id

        WHERE 1=1
    """


    params = {}


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        query += """

            AND (
                c.claim_id LIKE :search
                OR c.product_id LIKE :search
                OR p.serial_number LIKE :search
                OR u.user_id LIKE :search
                OR u.name LIKE :search
            )

        """

        params["search"] = f"%{search}%"


    # --------------------------------------------------------
    # CATEGORY FILTER
    # --------------------------------------------------------

    if category:

        query += """

            AND LOWER(p.category) = LOWER(:category)

        """

        params["category"] = category


    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status == "valid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely valid', 'valid claim')

        """

    elif status == "invalid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely invalid', 'invalid claim')

        """

    elif status == "review":

        query += """

            AND LOWER(c.final_status)
            IN
            ('manual review', 'manual review required')

        """


    query += """

        ORDER BY c.claim_id DESC

    """


    claims = query_database(
        query,
        params
    )


    return render_template(
        "all_claims_queue.html",
        claims=claims,
        search=search,
        category=category,
        status=status
    )


# ============================================================
# CLAIM DETAILS API
# ============================================================

@app.route("/api/claims/<claim_id>")
def claim_details(claim_id):

    result = query_database(
        f"""
        SELECT *
        FROM {CLAIMS_TABLE}
        WHERE claim_id = :claim_id
        LIMIT 1
        """,
        {
            "claim_id": claim_id
        }
    )

    if not result:

        return jsonify({
            "success": False,
            "message": "Claim not found"
        }), 404


    return jsonify({
        "success": True,
        "claim": result[0]
    })


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    try:

        with engine.connect() as connection:

            connection.execute(
                text("SELECT 1")
            )

        return jsonify({
            "status": "OK",
            "database": "connected"
        })

    except Exception as error:

        return jsonify({
            "status": "ERROR",
            "database": "not connected",
            "message": str(error)
        }), 500
# ============================================================
# 
# ============================================================

@app.route("/admin/manual")
def manual_review():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()


    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = f"""
        SELECT

            c.claim_id,

            c.product_id,

            c.submission_date,

            c.python_prediction,

            c.python_confidence,

            c.teachable_machine_prediction,

            c.teachable_machine_confidence,

            c.final_status,

            u.user_id,

            u.name AS claimant_name,

            p.product_name,

            p.category,

            p.serial_number

        FROM {CLAIMS_TABLE} c

        LEFT JOIN {USERS_TABLE} u
            ON c.user_id = u.user_id

        LEFT JOIN {PRODUCTS_TABLE} p
            ON c.product_id = p.product_id

        WHERE 1=1
    """


    params = {}


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        query += """

            AND (
                c.claim_id LIKE :search
                OR c.product_id LIKE :search
                OR p.serial_number LIKE :search
                OR u.user_id LIKE :search
                OR u.name LIKE :search
            )

        """

        params["search"] = f"%{search}%"


    # --------------------------------------------------------
    # CATEGORY FILTER
    # --------------------------------------------------------

    if category:

        query += """

            AND LOWER(p.category) = LOWER(:category)

        """

        params["category"] = category


    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status == "valid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely valid', 'valid claim')

        """

    elif status == "invalid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely invalid', 'invalid claim')

        """

    elif status == "review":

        query += """

            AND LOWER(c.final_status)
            IN
            ('manual review', 'manual review required')

        """


    query += """

        ORDER BY c.claim_id DESC

    """


    claims = query_database(
        query,
        params
    )


    return render_template(
        "manual_review_queue.html",
        claims=claims,
        search=search,
        category=category,
        status=status
    )

# ============================================================
# 
# ============================================================
@app.route("/admin/warranty_rules")
def warranty_rules():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()


    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = f"""
        SELECT

            c.claim_id,

            c.product_id,

            c.submission_date,

            c.python_prediction,

            c.python_confidence,

            c.teachable_machine_prediction,

            c.teachable_machine_confidence,

            c.final_status,

            u.user_id,

            u.name AS claimant_name,

            p.product_name,

            p.category,

            p.serial_number

        FROM {CLAIMS_TABLE} c

        LEFT JOIN {USERS_TABLE} u
            ON c.user_id = u.user_id

        LEFT JOIN {PRODUCTS_TABLE} p
            ON c.product_id = p.product_id

        WHERE 1=1
    """


    params = {}


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        query += """

            AND (
                c.claim_id LIKE :search
                OR c.product_id LIKE :search
                OR p.serial_number LIKE :search
                OR u.user_id LIKE :search
                OR u.name LIKE :search
            )

        """

        params["search"] = f"%{search}%"


    # --------------------------------------------------------
    # CATEGORY FILTER
    # --------------------------------------------------------

    if category:

        query += """

            AND LOWER(p.category) = LOWER(:category)

        """

        params["category"] = category


    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status == "valid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely valid', 'valid claim')

        """

    elif status == "invalid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely invalid', 'invalid claim')

        """

    elif status == "review":

        query += """

            AND LOWER(c.final_status)
            IN
            ('manual review', 'manual review required')

        """


    query += """

        ORDER BY c.claim_id DESC

    """


    claims = query_database(
        query,
        params
    )


    return render_template(
        "warranty_rules_config.html",
        claims=claims,
        search=search,
        category=category,
        status=status
    )


# ============================================================
# 
# ============================================================
@app.route("/admin/analytics")
def analytics():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()


    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = f"""
        SELECT

            c.claim_id,

            c.product_id,

            c.submission_date,

            c.python_prediction,

            c.python_confidence,

            c.teachable_machine_prediction,

            c.teachable_machine_confidence,

            c.final_status,

            u.user_id,

            u.name AS claimant_name,

            p.product_name,

            p.category,

            p.serial_number

        FROM {CLAIMS_TABLE} c

        LEFT JOIN {USERS_TABLE} u
            ON c.user_id = u.user_id

        LEFT JOIN {PRODUCTS_TABLE} p
            ON c.product_id = p.product_id

        WHERE 1=1
    """


    params = {}


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        query += """

            AND (
                c.claim_id LIKE :search
                OR c.product_id LIKE :search
                OR p.serial_number LIKE :search
                OR u.user_id LIKE :search
                OR u.name LIKE :search
            )

        """

        params["search"] = f"%{search}%"


    # --------------------------------------------------------
    # CATEGORY FILTER
    # --------------------------------------------------------

    if category:

        query += """

            AND LOWER(p.category) = LOWER(:category)

        """

        params["category"] = category


    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status == "valid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely valid', 'valid claim')

        """

    elif status == "invalid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely invalid', 'invalid claim')

        """

    elif status == "review":

        query += """

            AND LOWER(c.final_status)
            IN
            ('manual review', 'manual review required')

        """


    query += """

        ORDER BY c.claim_id DESC

    """


    claims = query_database(
        query,
        params
    )


    return render_template(
        "analytics_reports.html",
        claims=claims,
        search=search,
        category=category,
        status=status
    )


# ============================================================
# 
# ============================================================
@app.route("/admin/audit_logs")
def audit_logs():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()


    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = f"""
        SELECT

            c.claim_id,

            c.product_id,

            c.submission_date,

            c.python_prediction,

            c.python_confidence,

            c.teachable_machine_prediction,

            c.teachable_machine_confidence,

            c.final_status,

            u.user_id,

            u.name AS claimant_name,

            p.product_name,

            p.category,

            p.serial_number

        FROM {CLAIMS_TABLE} c

        LEFT JOIN {USERS_TABLE} u
            ON c.user_id = u.user_id

        LEFT JOIN {PRODUCTS_TABLE} p
            ON c.product_id = p.product_id

        WHERE 1=1
    """


    params = {}


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        query += """

            AND (
                c.claim_id LIKE :search
                OR c.product_id LIKE :search
                OR p.serial_number LIKE :search
                OR u.user_id LIKE :search
                OR u.name LIKE :search
            )

        """

        params["search"] = f"%{search}%"


    # --------------------------------------------------------
    # CATEGORY FILTER
    # --------------------------------------------------------

    if category:

        query += """

            AND LOWER(p.category) = LOWER(:category)

        """

        params["category"] = category


    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status == "valid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely valid', 'valid claim')

        """

    elif status == "invalid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely invalid', 'invalid claim')

        """

    elif status == "review":

        query += """

            AND LOWER(c.final_status)
            IN
            ('manual review', 'manual review required')

        """


    query += """

        ORDER BY c.claim_id DESC

    """


    claims = query_database(
        query,
        params
    )


    return render_template(
        "audit_logs.html",
        claims=claims,
        search=search,
        category=category,
        status=status
    )


# ============================================================
# 
# ============================================================
@app.route("/admin/user_management")
def user_management():

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    status = request.args.get(
        "status",
        ""
    ).strip()


    # --------------------------------------------------------
    # BASE QUERY
    # --------------------------------------------------------

    query = f"""
        SELECT

            c.claim_id,

            c.product_id,

            c.submission_date,

            c.python_prediction,

            c.python_confidence,

            c.teachable_machine_prediction,

            c.teachable_machine_confidence,

            c.final_status,

            u.user_id,

            u.name AS claimant_name,

            p.product_name,

            p.category,

            p.serial_number

        FROM {CLAIMS_TABLE} c

        LEFT JOIN {USERS_TABLE} u
            ON c.user_id = u.user_id

        LEFT JOIN {PRODUCTS_TABLE} p
            ON c.product_id = p.product_id

        WHERE 1=1
    """


    params = {}


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    if search:

        query += """

            AND (
                c.claim_id LIKE :search
                OR c.product_id LIKE :search
                OR p.serial_number LIKE :search
                OR u.user_id LIKE :search
                OR u.name LIKE :search
            )

        """

        params["search"] = f"%{search}%"


    # --------------------------------------------------------
    # CATEGORY FILTER
    # --------------------------------------------------------

    if category:

        query += """

            AND LOWER(p.category) = LOWER(:category)

        """

        params["category"] = category


    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    if status == "valid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely valid', 'valid claim')

        """

    elif status == "invalid":

        query += """

            AND LOWER(c.final_status)
            IN ('likely invalid', 'invalid claim')

        """

    elif status == "review":

        query += """

            AND LOWER(c.final_status)
            IN
            ('manual review', 'manual review required')

        """


    query += """

        ORDER BY c.claim_id DESC

    """


    claims = query_database(
        query,
        params
    )


    return render_template( "user_management.html",
                           claims=claims,search=search,category=category, status=status)


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
"""
Flask entry point for the AssureX Claim Engine.

Run it with:

    py -3 app.py

By default this targets MySQL using the DB_* environment variables. To run
with no database server installed, use SQLite:

    set ASSUREX_DATABASE_URL=sqlite:///assurex.db
    py -3 app.py

SRS coverage provided by this module:
    i, ii     registration, login, logout, role-based access
    xl, xli   customer and administrator dashboards
    xlii      search and filtering entry points
    xviii, xix  Python model prediction and three-class confidence
    xxv       warranty rule validation
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from database import (  # noqa: E402
    Claim,
    Evaluation,
    Product,
    ReviewAction,
    User,
    Warranty,
    db,
    initialize_database,
)
from claim_service import derive_claim_features, persist_submission  # noqa: E402
from decision_engine import decide_from_evaluation  # noqa: E402

# The database module created its own Flask instance, so point it at the
# repository-level template and static folders rather than database/.
from database.database import app  # noqa: E402

app.template_folder = str(PROJECT_ROOT / "templates")
app.static_folder = str(PROJECT_ROOT / "static")
app.secret_key = os.getenv("ASSUREX_SECRET_KEY", "dev-secret-change-me")

DATASET_ROOT = PROJECT_ROOT / "dataset"
POLICY_DIR = DATASET_ROOT / "policies"
ARTIFACT_DIR = PROJECT_ROOT / "models" / "tabular"


# SRS xlviii requires every prediction to record which model version produced
# it. Read it from the trained metrics rather than duplicating a literal, so
# retraining updates the recorded version automatically.
def _read_model_version() -> str:
    metrics = ARTIFACT_DIR / "metrics.json"

    if not metrics.is_file():
        return "unknown"

    try:
        payload = json.loads(metrics.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "unknown"

    return str(payload.get("model_version", "unknown"))


MODEL_VERSION = _read_model_version()

# These must match the SQLAlchemy Enum values declared in database/database.py.
# Storing anything else raises LookupError on commit.
ROLE_CUSTOMER = "Customer"
ROLE_SERVICE_CENTER = "Service-center employee"
ROLE_REVIEWER = "Claim reviewer"
ROLE_ADMIN = "Administrator"

ROLES = (ROLE_CUSTOMER, ROLE_SERVICE_CENTER, ROLE_REVIEWER, ROLE_ADMIN)
REVIEW_ROLES = (ROLE_REVIEWER, ROLE_ADMIN)

ACTION_APPROVE = "Approve"
ACTION_REJECT = "Reject"
ACTION_REQUEST_INFO = "Request Additional Information"
ACTION_OVERRIDE = "Override"

_pipeline_cache: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Model and rule engine loading (SRS xviii, xix, xxv)
# ---------------------------------------------------------------------------


def get_pipeline():
    """Load the trained pipeline once, lazily."""
    if "pipeline" not in _pipeline_cache:
        import joblib

        path = ARTIFACT_DIR / "final_pipeline.joblib"
        if not path.is_file():
            raise FileNotFoundError(
                f"Trained model not found at {path}. "
                "Run: py -3 src/train_model.py"
            )
        _pipeline_cache["pipeline"] = joblib.load(path)
        _pipeline_cache["features"] = joblib.load(
            ARTIFACT_DIR / "feature_names.joblib"
        )
    return _pipeline_cache["pipeline"]


def get_policies() -> dict:
    if "policies" not in _pipeline_cache:
        from rule_engine import load_policies

        _pipeline_cache["policies"] = load_policies(POLICY_DIR)
    return _pipeline_cache["policies"]


def evaluate_submission(form: dict) -> dict:
    """
    Run the Python model and the rule engine over one submitted claim.

    SRS xix requires a confidence score for all three classes. SRS xxv requires
    independent rule validation. Neither depends on the other.
    """
    from rule_engine import evaluate_claim

    claim = {
        "claim_id": form.get("claim_id") or "PENDING",
        "product_category": form.get("product_category", ""),
        "brand": form.get("brand", ""),
        "model": form.get("model", ""),
        "retailer": form.get("retailer", ""),
        "purchase_date": form.get("purchase_date", ""),
        "purchase_price": float(form.get("purchase_price") or 0),
        "purchase_information_consistent": form.get("purchase_consistent") == "on",
        "serial_number": form.get("serial_number", ""),
        "receipt_serial_number": form.get("receipt_serial_number", ""),
        "warranty_card_serial_number": form.get("warranty_card_serial_number", ""),
        "product_image_serial_number": form.get("product_image_serial_number", ""),
        "repair_record_serial_number": form.get("repair_record_serial_number", ""),
        "receipt_model": form.get("model", ""),
        "warranty_card_model": form.get("model", ""),
        "product_image_model": form.get("model", ""),
        "repair_record_model": form.get("model", ""),
        "warranty_provider": form.get("warranty_provider", ""),
        "warranty_start_date": form.get("purchase_date", ""),
        "warranty_expiry_date": form.get("warranty_expiry_date", ""),
        "warranty_duration_months": int(form.get("warranty_duration_months") or 12),
        "extended_warranty": form.get("extended_warranty") == "on",
        "fault_date": form.get("fault_date", ""),
        "claim_date": form.get("claim_date", ""),
        "last_repair_date": form.get("last_repair_date") or None,
        "fault_category": form.get("fault_category", ""),
        "fault_description": form.get("fault_description", ""),
        "damage_type": form.get("damage_type", ""),
        "physical_damage": form.get("physical_damage") == "on",
        "liquid_damage": form.get("liquid_damage") == "on",
        "unauthorized_repair": form.get("unauthorized_repair") == "on",
        "authorized_service_center": form.get("authorized_service_center") == "on",
        "previous_repair_count": int(form.get("previous_repair_count") or 0),
        "previous_replacement": form.get("previous_replacement") == "on",
        "previous_replacement_count": int(form.get("previous_replacement_count") or 0),
        "replacement_requested": form.get("replacement_requested") == "on",
        "receipt_available": form.get("receipt_available") == "on",
        "receipt_valid": form.get("receipt_valid") == "on",
        "warranty_card_available": form.get("warranty_card_available") == "on",
        "product_image_available": form.get("product_image_available") == "on",
        "serial_evidence_available": form.get("serial_evidence_available") == "on",
        "fault_evidence_available": form.get("fault_evidence_available") == "on",
        "repair_report_available": form.get("repair_report_available") == "on",
    }

    # SRS xvi: derived fields must exist BEFORE classification. Without them the
    # numeric imputer receives empty strings, and `repair_history` -- the model's
    # strongest feature -- arrives blank, which collapses predictions towards
    # the majority class.
    policy = get_policies().get(claim.get("product_category"))
    claim.update(derive_claim_features(claim, policy))

    pipeline = get_pipeline()
    features = _pipeline_cache["features"]

    from preprocessing import prepare_features

    frame = prepare_features(
        _as_frame(claim, features), list(features)
    )
    probabilities = pipeline.predict_proba(frame)[0]
    classes = list(pipeline.named_steps["model"].classes_)

    prediction = {
        "python_predicted_class": classes[int(probabilities.argmax())],
        "python_confidence": {
            name: round(float(p), 4) for name, p in zip(classes, probabilities)
        },
    }

    rule_result = evaluate_claim(claim, get_policies())
    prediction["rule_outcome"] = rule_result.outcome
    prediction["rule_result"] = rule_result.as_dict()
    prediction["derived_facts"] = {
        key: claim[key]
        for key in (
            "product_age_days",
            "reporting_days",
            "warranty_remaining_days",
            "warranty_status",
            "days_since_last_repair",
            "missing_documents_count",
            "missing_documents",
            "repair_history",
            "supporting_evidence_available",
        )
    }

    return prediction


def _as_frame(claim: dict, features: list[str]):
    import pandas as pd

    row = {name: claim.get(name, "") for name in features}
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# Authentication (SRS i, ii)
# ---------------------------------------------------------------------------


def current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def login_required(view):
    def wrapper(*args, **kwargs):
        if current_user() is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    wrapper.__name__ = view.__name__
    return wrapper


def role_required(*roles):
    def decorator(view):
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return redirect(url_for("login"))
            if user.role not in roles:
                flash("You do not have permission to view that page.", "danger")
                return redirect(url_for("customer_dashboard"))
            return view(*args, **kwargs)

        wrapper.__name__ = view.__name__
        return wrapper

    return decorator


@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "ROLES": ROLES,
        "policy_categories": sorted(get_policies()),
        "now": datetime.utcnow,
    }


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Landing page. Signed-in users go straight to their dashboard."""
    user = current_user()

    if user is None:
        return render_template("index.html")

    if user.role == ROLE_ADMIN:
        return redirect(url_for("admin_dashboard"))

    return redirect(url_for("customer_dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            flash(f"Signed in as {user.full_name}.", "success")
            return redirect(url_for("index"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", ROLE_CUSTOMER)

        if role not in ROLES:
            role = ROLE_CUSTOMER

        if not full_name or not email or len(password) < 8:
            flash("Name, email and a password of at least 8 characters are required.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
        else:
            user = User(
                user_id=f"USR-{abs(hash(email)) % 900000 + 100000}",
                full_name=full_name,
                email=email,
                password_hash=generate_password_hash(password),
                role=role,
            )
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            flash("Account created. Welcome to AssureX.", "success")
            return redirect(url_for("index"))

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Signed out.", "info")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = current_user()

    if request.method == "POST":
        user.full_name = request.form.get("full_name", user.full_name)
        user.phone = request.form.get("phone", user.phone)
        user.address = request.form.get("address", user.address)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=user)


# ---------------------------------------------------------------------------
# Dashboards (SRS xl, xli)
# ---------------------------------------------------------------------------


@app.route("/dashboard")
@login_required
def customer_dashboard():
    user = current_user()
    products = Product.query.filter_by(user_id=user.user_id).all()

    product_ids = [product.id for product in products]
    warranties = (
        Warranty.query.filter(Warranty.product_id.in_(product_ids)).all()
        if product_ids
        else []
    )

    claims = Claim.query.filter_by(user_id=user.user_id).all()

    return render_template(
        "CustomerDashbourd.html",
        products=products,
        warranties=warranties,
        claims=claims,
        stats={
            "products": len(products),
            "active_warranties": sum(1 for w in warranties if w.status == "Active"),
            "claims": len(claims),
            "pending": sum(1 for c in claims if c.status in {"Submitted", "Under Evaluation"}),
        },
    )


@app.route("/admin/dashboard")
@role_required(ROLE_ADMIN)
def admin_dashboard():
    claims = Claim.query.all()
    evaluations = Evaluation.query.all()

    by_class: dict[str, int] = {}
    for evaluation in evaluations:
        key = evaluation.final_decision or evaluation.python_predicted_class or "Undecided"
        by_class[key] = by_class.get(key, 0) + 1

    return render_template(
        "admin_dashboard.html",
        stats={
            "total_claims": len(claims),
            "pending": sum(1 for c in claims if c.status in {"Submitted", "Under Evaluation"}),
            "manual_review": by_class.get("Manual Review Required", 0),
            "likely_valid": by_class.get("Likely Valid", 0),
            "likely_invalid": by_class.get("Likely Invalid", 0),
            "evaluations": len(evaluations),
        },
        claims=claims,
        by_class=by_class,
    )


# ---------------------------------------------------------------------------
# Claims (SRS x, xi, xxxiv)
# ---------------------------------------------------------------------------


@app.route("/claims")
@login_required
def claims_queue():
    query = Claim.query

    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)

    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(Claim.claim_id.like(f"%{search}%"))

    return render_template("all_claims_queue.html", claims=query.all(), filters={"status": status, "q": search})


@app.route("/claims/new", methods=["GET", "POST"])
@login_required
def create_claim():
    if request.method == "POST":
        form = request.form.to_dict()

        try:
            result = evaluate_submission(form)
        except FileNotFoundError as error:
            flash(str(error), "danger")
            return render_template("create-claim.html", form=form)
        except Exception as error:  # noqa: BLE001 - surfaced to the user
            flash(f"Could not evaluate the claim: {error}", "danger")
            return render_template("create-claim.html", form=form)

        # SRS xxxiv: combine the model result with the rule result.
        decision = decide_from_evaluation(result, result.get("rule_result"))
        result["final_decision"] = decision.final_decision
        result["decision"] = decision.as_dict()
        result["explanation"] = decision.explanation()

        saved = None
        try:
            claim, evaluation = persist_submission(
                current_user(),
                form,
                result,
                decision,
                MODEL_VERSION,
            )
            saved = claim
        except Exception as error:  # noqa: BLE001 - never lose the evaluation
            flash(
                "The claim was evaluated but could not be saved: "
                f"{error}",
                "warning",
            )

        if saved is not None:
            flash(
                f"Claim {saved.claim_id} saved with decision "
                f"{decision.final_decision}.",
                "success",
            )
            return redirect(url_for("claim_details", claim_id=saved.claim_id))

        return render_template(
            "claim_result.html",
            result=result,
            form=form,
        )

    return render_template("create-claim.html", form={})


@app.route("/claims/<claim_id>")
@login_required
def claim_details(claim_id: str):
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()
    return render_template(
        "claim-details.html",
        claim=claim,
        evaluations=Evaluation.query.filter_by(claim_id=claim_id).all(),
        reviews=ReviewAction.query.filter_by(claim_id=claim_id).all(),
    )


@app.route("/claims/<claim_id>/review", methods=["POST"])
@role_required(*REVIEW_ROLES)
def review_claim(claim_id: str):
    claim = Claim.query.filter_by(claim_id=claim_id).first_or_404()

    requested = request.form.get("action", ACTION_REQUEST_INFO)
    action_value = requested if requested in (
        ACTION_APPROVE,
        ACTION_REJECT,
        ACTION_REQUEST_INFO,
        ACTION_OVERRIDE,
    ) else ACTION_REQUEST_INFO

    record = ReviewAction(
        action_id=f"ACT-{abs(hash((claim_id, action_value))) % 900000 + 100000}",
        claim_id=claim.id,
        reviewer_id=current_user().id,
        action=action_value,
        comments=request.form.get("comments", ""),
        created_at=datetime.utcnow(),
    )
    db.session.add(record)
    db.session.commit()

    if action_value == ACTION_APPROVE:
        claim.status = "Approved"
        db.session.commit()
        flash(f"Claim {claim_id} approved.", "success")
    elif action_value == ACTION_REJECT:
        claim.status = "Rejected"
        db.session.commit()
        flash(f"Claim {claim_id} rejected.", "success")
    else:
        flash("Reviewer action recorded.", "info")

    return redirect(url_for("claim_details", claim_id=claim_id))


@app.route("/manual-review")
@role_required(*REVIEW_ROLES)
def manual_review_queue():
    evaluations = Evaluation.query.filter_by(final_decision="Manual Review Required").all()
    return render_template("manual_review_queue.html", evaluations=evaluations)


# ---------------------------------------------------------------------------
# Supporting pages
# ---------------------------------------------------------------------------


@app.route("/products")
@login_required
def my_products():
    return render_template(
        "my_products.html",
        products=Product.query.filter_by(user_id=current_user().user_id).all(),
    )


@app.route("/documents")
@login_required
def receipt_vault():
    return render_template("receipt_vault.html", claim_id=request.args.get("claim_id", ""))


@app.route("/claims/status")
@login_required
def claim_status():
    return render_template(
        "claim_status.html",
        claims=Claim.query.filter_by(user_id=current_user().user_id).all(),    )


@app.route("/claims/submit")
@login_required
def submit_claim():
    return render_template(
        "submit_claim.html",
        products=Product.query.filter_by(
            user_id=current_user().user_id
        ).all(),
    )


@app.route("/analytics")
@role_required(*REVIEW_ROLES)
def analytics_reports():
    return render_template("analytics_reports.html", stats={})


@app.route("/audit")
@role_required(ROLE_ADMIN)
def audit_logs():
    return render_template(
        "audit_logs.html",
        actions=ReviewAction.query.order_by(ReviewAction.created_at.desc()).all(),
    )


@app.route("/users")
@role_required(ROLE_ADMIN)
def user_management():
    return render_template("user_management.html", users=User.query.all())


@app.route("/warranty-rules")
@role_required(*REVIEW_ROLES)
def warranty_rules_config():
    from rule_engine import load_policies

    return render_template("warranty_rules_config.html", policies=load_policies(POLICY_DIR))


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "database": str(db.engine.url).split("://")[0],
            "model_loaded": "pipeline" in _pipeline_cache,
            "policy_categories": sorted(get_policies()),
        }
    )


@app.errorhandler(404)
def not_found(error):  # noqa: ARG001
    return render_template("error.html", code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(error):  # noqa: ARG001
    return render_template("error.html", code=500, message="Unexpected server error."), 500


def bootstrap() -> None:
    """Create the schema and seed the default policies."""
    with app.app_context():
        initialize_database(seed_policies=True)


if __name__ == "__main__":
    bootstrap()
    port = int(os.getenv("PORT", "5000"))
    print(f"AssureX Claim Engine running on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False)
