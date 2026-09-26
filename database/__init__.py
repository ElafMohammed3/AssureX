"""
Database package for the AssureX Claim Engine.

Re-exports the SQLAlchemy extension and every model so application code can
use a single import:

    from database import db, User, Claim

The models themselves live in `database/database.py`, which is also
importable as `database.database`.
"""

from .database import (  # noqa: F401
    DATABASE_URL,
    DB_HOST,
    DB_NAME,
    DB_PASSWORD,
    DB_PORT,
    DB_USER,
    IS_SQLITE,
    SERVER_DATABASE_URL,
    Claim,
    Document,
    Evaluation,
    Product,
    RepairHistory,
    ReviewAction,
    User,
    Warranty,
    WarrantyPolicy,
    app,
    create_database,
    create_tables,
    db,
    initialize_database,
    seed_default_policies,
)

__all__ = [
    "DATABASE_URL",
    "DB_HOST",
    "DB_NAME",
    "DB_PASSWORD",
    "DB_PORT",
    "DB_USER",
    "IS_SQLITE",
    "SERVER_DATABASE_URL",
    "Claim",
    "Document",
    "Evaluation",
    "Product",
    "RepairHistory",
    "ReviewAction",
    "User",
    "Warranty",
    "WarrantyPolicy",
    "app",
    "create_database",
    "create_tables",
    "db",
    "initialize_database",
    "seed_default_policies",
]
