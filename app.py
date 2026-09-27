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