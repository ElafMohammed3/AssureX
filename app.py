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

# The database module created its own Flask instance, so point it at the
# repository-level template and static folders rather than database/.
from database.database import app  # noqa: E402

app.template_folder = str(PROJECT_ROOT / "templates")
app.static_folder = str(PROJECT_ROOT / "static")
app.secret_key = os.getenv("ASSUREX_SECRET_KEY", "dev-secret-change-me")

DATASET_ROOT = PROJECT_ROOT / "dataset"
POLICY_DIR = DATASET_ROOT / "policies"
ARTIFACT_DIR = PROJECT_ROOT / "models" / "tabular"

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
        try:
            result = evaluate_submission(request.form.to_dict())
        except FileNotFoundError as error:
            flash(str(error), "danger")
            return render_template("create-claim.html", form=request.form)
        except Exception as error:  # noqa: BLE001 - surfaced to the user
            flash(f"Could not evaluate the claim: {error}", "danger")
            return render_template("create-claim.html", form=request.form)

        return render_template(
            "claim_result.html",
            result=result,
            form=request.form,
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
