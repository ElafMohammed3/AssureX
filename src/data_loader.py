#!/usr/bin/env python
# coding: utf-8

# The Libraries

# In[9]:


from __future__ import annotations
import json
from pathlib import Path 
import pandas as pd


# Defines the standard dataset partitions

# In[10]:


SPLITS = ("train", "validation", "test")
TARGET_COLUMN = "claim_class"
def find_dataset_root() -> Path:
    """Find the dataset folder by searching the current folder and its parents."""
    here = Path.cwd().resolve()

    for folder in [here, *here.parents]:
        candidates = [
            folder / "dataset",
            folder / "AssureX" / "dataset",
        ]

        for candidate in candidates:
            if (candidate / "feature_manifest.json").is_file():
                return candidate

    raise FileNotFoundError(
        "Could not find dataset/feature_manifest.json. "
        "Run Jupyter from the AssureX project folder."
    )


# In[11]:


def load_feature_manifest(
    dataset_root: str | Path,
) -> list[str]:
    """Load the model-input column names."""
    root = Path(dataset_root)
    manifest_path = root / "feature_manifest.json"

    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Feature manifest not found: {manifest_path}"
        )

    payload = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )

    features = payload.get("features")

    if not isinstance(features, list) or not features:
        raise ValueError(
            "feature_manifest.json must contain a non-empty features list."
        )

    if TARGET_COLUMN in features:
        raise ValueError(
            "The target column must not be included in model features."
        )

    return features


# In[12]:


def read_split(
    dataset_root: str | Path,
    split: str,
) -> pd.DataFrame:
    """Read one CSV split from dataset/csv."""
    root = Path(dataset_root)
    csv_path = root / "csv" / f"{split}.csv"

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Dataset file not found: {csv_path}"
        )

    return pd.read_csv(csv_path)


# In[13]:


def validate_split(
    split: str,
    dataframe: pd.DataFrame,
    feature_names: list[str],
) -> None:
    """Validate the basic structure of one split."""
    if dataframe.empty:
        raise ValueError(f"{split}.csv is empty.")

    required_columns = set(feature_names) | {
        TARGET_COLUMN,
        "claim_id",
    }

    missing_columns = required_columns - set(dataframe.columns)

    if missing_columns:
        raise ValueError(
            f"{split}.csv is missing columns: "
            f"{sorted(missing_columns)}"
        )

    if dataframe[TARGET_COLUMN].isna().any():
        raise ValueError(
            f"{split}.csv contains missing target values."
        )

    if dataframe["claim_id"].isna().any():
        raise ValueError(
            f"{split}.csv contains missing Claim IDs."
        )

    if dataframe["claim_id"].duplicated().any():
        raise ValueError(
            f"{split}.csv contains duplicate Claim IDs."
        )

    if "split" in dataframe.columns:
        actual_splits = set(dataframe["split"].dropna().unique())

        if actual_splits != {split}:
            raise ValueError(
                f"{split}.csv contains incorrect split values: "
                f"{actual_splits}"
            )


# In[14]:


def load_datasets(
    dataset_root: str | Path | None = None,
):
    """
    Load train, validation and test data.

    Returns:
        train_df, validation_df, test_df, feature_names
    """
    root = (
        Path(dataset_root)
        if dataset_root is not None
        else find_dataset_root()
    )

    feature_names = load_feature_manifest(root)

    dataframes = {
        split: read_split(root, split)
        for split in SPLITS
    }

    for split, dataframe in dataframes.items():
        validate_split(split, dataframe, feature_names)

    id_sets = {
        split: set(dataframe["claim_id"])
        for split, dataframe in dataframes.items()
    }

    for index, left_split in enumerate(SPLITS):
        for right_split in SPLITS[index + 1:]:
            overlap = id_sets[left_split] & id_sets[right_split]

            if overlap:
                raise ValueError(
                    f"Claim IDs cross splits: "
                    f"{left_split} and {right_split}"
                )

    return (
        dataframes["train"],
        dataframes["validation"],
        dataframes["test"],
        feature_names,
    )


# In[15]:


if __name__ == "__main__":
    train_df, validation_df, test_df, features = load_datasets()

    print("Dataset loaded successfully.")
    print(f"Train shape:      {train_df.shape}")
    print(f"Validation shape: {validation_df.shape}")
    print(f"Test shape:       {test_df.shape}")
    print(f"Model features:   {len(features)}")
    print("Train classes:   ", train_df["claim_class"].value_counts().to_dict())
    print("Validation classes:", validation_df["claim_class"].value_counts().to_dict())
    print("Test classes:    ", test_df["claim_class"].value_counts().to_dict())

