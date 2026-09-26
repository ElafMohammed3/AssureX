#!/usr/bin/env python
# coding: utf-8

# The libraries used in preprocessing

# In[2]:


from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder,StandardScaler 


# All the features in dataset

# In[3]:


DATE_COLUMNS = [
    "purchase_date",
    "warranty_start_date",
    "warranty_expiry_date",
    "fault_date",
    "claim_date",
    "last_repair_date",
    "previous_replacement_date",
]

NUMERIC_COLUMNS = [
    "purchase_price",
    "warranty_duration_months",
    "warranty_remaining_days",
    "product_age_days",
    "reporting_days",
    "previous_repair_count",
    "previous_replacement_count",
    "missing_documents_count",
]
BOOLEAN_COLUMNS = [
    "purchase_information_consistent",
    "extended_warranty",
    "physical_damage",
    "liquid_damage",
    "unauthorized_repair",
    "authorized_service_center",
    "previous_replacement",
    "replacement_requested",
    "receipt_available",
    "receipt_valid",
    "warranty_card_available",
    "product_image_available",
    "serial_evidence_available",
    "fault_evidence_available",
    "repair_report_available",
    "supporting_evidence_available",
]

CATEGORICAL_COLUMNS = [
    "product_category",
    "brand",
    "model",
    "retailer",
    "warranty_provider",
    "fault_category",
    "damage_type",
]

TEXT_COLUMNS = [
    "fault_description",
    "repair_history",
    "missing_documents",
]

ALL_KNOWN_FEATURES = set(
    DATE_COLUMNS
    + NUMERIC_COLUMNS
    + BOOLEAN_COLUMNS
    + CATEGORICAL_COLUMNS
    + TEXT_COLUMNS
)
DATE_ORIGIN = pd.Timestamp("2020-01-01")



# validation and safe loading of model inputs

# In[4]:


def load_feature_manifest(path: str | Path ) -> list[str]:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("feature_manifest.json does not contain a valid features list.")
    unknown = set(features) - ALL_KNOWN_FEATURES
    if unknown:
        raise ValueError(f"Unknown feature columns: {sorted(unknown)}")

    return features


# Translates Dates &
# Filters Unused Dates &
# Standardizes Feature Naming

# In[5]:


def date_feature_names(feature_names:list[str]):
    derived:list[str] = []
    for column in DATE_COLUMNS:
        if column in feature_names:
            derived.extend(
                [
                    f"{column}_year",
                    f"{column}_month",
                    f"{column}_day",
                    f"{column}_ordinal",
                ]
            )
    return derived



# Feature Transformation (Turning Raw Data into Numbers) & Missing Value Management (Handling NaNs) & Pipeline Standardization & Safety

# In[6]:


def prepare_features(
    dataframe: pd.DataFrame,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    Prepare raw claim columns for the scikit-learn pipeline.

    This function contains no target column and no prediction logic.
    It performs deterministic date conversion and type normalization only.
    """
    missing_columns = [
    column for column in feature_names if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing dataset columns: {missing_columns}"
        )

    X = dataframe[feature_names].copy()
    # Convert dates into numeric calendar features.
    for column in DATE_COLUMNS:
        if column not in X.columns:
            continue

        parsed = pd.to_datetime(X[column], errors="coerce")

        X[f"{column}_year"] = parsed.dt.year
        X[f"{column}_month"] = parsed.dt.month
        X[f"{column}_day"] = parsed.dt.day
        X[f"{column}_ordinal"] = (parsed - DATE_ORIGIN).dt.days
    # Remove raw date strings after creating numeric date features.
    raw_dates = [column for column in DATE_COLUMNS if column in X.columns]
    X = X.drop(columns=raw_dates)

    # Normalize Boolean values.
    boolean_map = {
        "true": 1.0,
        "false": 0.0,
        "1": 1.0,
        "0": 0.0,
        "yes": 1.0,
        "no": 0.0,
    }

    for column in BOOLEAN_COLUMNS:
        if column in X.columns:
            X[column] = (
                X[column]
                .astype("string")
                .str.strip()
                .str.lower()
                .map(boolean_map)
            )

    # Keep categorical values as strings for one-hot encoding.
    for column in CATEGORICAL_COLUMNS:
        if column in X.columns:
            X[column] = X[column].fillna("Missing").astype(str)

    # Text fields are encoded categorically for the minimum compliant model.
    for column in TEXT_COLUMNS:
        if column in X.columns:
            if column == "missing_documents":
                X[column] = X[column].fillna("None").astype(str)
            else:
                X[column] = X[column].fillna("").astype(str)

    return X      


# eparates Columns into Two Groups & Applies Custom Processing to Each Group in Parallel &  Combines Everything Together

# In[7]:


def build_preprocessor(
    feature_names:list[str],
)-> ColumnTransformer:
    """Create the reusable, train-fitted preprocessing pipeline."""
    unknown = set(feature_names) - ALL_KNOWN_FEATURES
    if unknown:
        raise ValueError(f"Unknown feature columns: {sorted(unknown)}")

    numeric_features = [
        column
        for column in NUMERIC_COLUMNS + BOOLEAN_COLUMNS
        if column in feature_names
    ]

    numeric_features.extend(date_feature_names(feature_names))

    categorical_features = [
        column
        for column in CATEGORICAL_COLUMNS + TEXT_COLUMNS
        if column in feature_names
    ]

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "encoder",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, numeric_features),
            ("categorical", categorical_pipeline, categorical_features),
        ],
        remainder="drop",
    )

