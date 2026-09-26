"""Train, compare and evaluate the AssureX claim classification models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_loader import load_datasets
from preprocessing import build_preprocessor, prepare_features

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = PROJECT_ROOT / "dataset"
ARTIFACT_DIR = PROJECT_ROOT / "models" / "tabular"

RANDOM_STATE = 42
TARGET_COLUMN = "claim_class"
MODEL_VERSION = "1.0.0"



def candidate_models() -> dict:
    """Return the three classifiers ."""
    return {
        "logistic_regression": LogisticRegression(
            max_iter=3000,
            random_state=RANDOM_STATE,
        ),
        "decision_tree": DecisionTreeClassifier(
            random_state=RANDOM_STATE,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=300,
            random_state=RANDOM_STATE,
            n_jobs=-1
        ),
    }


def make_pipeline(model, feature_names: list[str]) -> Pipeline:
    """Attach the shared preprocessing pipeline in front of a model."""
    return Pipeline(
        steps=[
            ("preprocessor", build_preprocessor(feature_names)),
            ("model", model),
        ]
    )


def score_predictions(y_true, y_pred) -> dict:
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro")), 4),
        "f1_weighted": round(
            float(f1_score(y_true, y_pred, average="weighted")), 4
        ),
    }







def aggregate_importance(
    preprocessor,
    importances: np.ndarray,
    feature_names: list[str],
) -> pd.DataFrame:
    """
    Roll 161 transformed columns up to the 41 declared model inputs.

    ColumnTransformer names look like 'numeric__purchase_price' or
    'categorical__brand_Acme'. Longest-prefix matching maps every
    transformed column back to exactly one declared input.
    """
    transformed = list(preprocessor.get_feature_names_out())

    if len(transformed) != len(importances):
        raise ValueError(
            f"Length mismatch: {len(transformed)} columns vs "
            f"{len(importances)} importances"
        )

    ordered = sorted(feature_names, key=len, reverse=True)
    totals = {name: 0.0 for name in ordered}
    unassigned = 0.0

    for column, value in zip(transformed, importances):
        _, _, remainder = column.partition("__")

        for name in ordered:
            if remainder == name or remainder.startswith(f"{name}_"):
                totals[name] += float(value)
                break
        else:
            unassigned += float(value)

    frame = pd.DataFrame(
        {
            "feature": list(totals.keys()),
            "importance": list(totals.values()),
        }
    )
    frame = frame.sort_values("importance", ascending=False)
    frame = frame.reset_index(drop=True)
    frame["cumulative_importance"] = frame["importance"].cumsum()

    if unassigned > 1e-9:
        print(f"WARNING: {unassigned:.6f} importance could not be mapped")

    return frame

def json_safe(value):
    """Convert numpy values so json.dumps never fails."""
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if hasattr(value, "item"):
        return value.item()

    return value


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    train_df, validation_df, test_df, feature_names = load_datasets(
        DATASET_ROOT
    )

    X_train = prepare_features(train_df, feature_names)
    X_validation = prepare_features(validation_df, feature_names)
    X_test = prepare_features(test_df, feature_names)

    y_train = train_df[TARGET_COLUMN]
    y_validation = validation_df[TARGET_COLUMN]
    y_test = test_df[TARGET_COLUMN]

    print("=" * 64)
    print("STEP 1  Train the three candidate models")
    print("=" * 64)

    validation_results: dict[str, dict] = {}
    fitted_pipelines: dict[str, Pipeline] = {}

    for name, model in candidate_models().items():
        pipeline = make_pipeline(model, feature_names)
        pipeline.fit(X_train, y_train)
        fitted_pipelines[name] = pipeline

        predictions = pipeline.predict(X_validation)
        validation_results[name] = score_predictions(y_validation, predictions)

        print(f"\n{name}")
        print(f"  validation accuracy    : {validation_results[name]['accuracy']}")
        print(f"  validation f1 macro    : {validation_results[name]['f1_macro']}")
        print(f"  validation f1 weighted : {validation_results[name]['f1_weighted']}")
        print()
        print(classification_report(y_validation, predictions, zero_division=0))

    print("=" * 64)
    print("STEP 2  Select the model using the validation set")
    print("=" * 64)

    best_name = max(
        validation_results,
        key=lambda key: validation_results[key]["f1_macro"],
    )
    best_pipeline = fitted_pipelines[best_name]

    print(f"Selection rule : highest validation macro F1")
    print(f"Selected model : {best_name}")

    print()
    print("=" * 64)
    print("STEP 3  Five-fold cross validation on training data only")
    print("=" * 64)

    cross_validation = cross_val_score(
        make_pipeline(candidate_models()[best_name], feature_names),
        X_train,
        y_train,
        cv=StratifiedKFold(
            n_splits=5,
            shuffle=True,
            random_state=RANDOM_STATE,
        ),
        scoring="f1_macro",
        n_jobs=-1,
    )

    print(f"CV f1 macro mean  : {cross_validation.mean():.4f}")
    print(f"CV f1 macro std   : {cross_validation.std():.4f}")
    print(f"CV f1 macro folds : {[round(float(v), 4) for v in cross_validation]}")

    print()
    print("=" * 64)
    print("STEP 4  Final evaluation on the test set (performed once)")
    print("=" * 64)

    test_predictions = best_pipeline.predict(X_test)
    test_results = score_predictions(y_test, test_predictions)
    test_report = classification_report(
        y_test,
        test_predictions,
        zero_division=0,
        output_dict=True,
    )

    print(f"test accuracy    : {test_results['accuracy']}")
    print(f"test f1 macro    : {test_results['f1_macro']}")
    print(f"test f1 weighted : {test_results['f1_weighted']}")
    print()
    print(classification_report(y_test, test_predictions, zero_division=0))

    labels = list(best_pipeline.named_steps["model"].classes_)
    matrix = confusion_matrix(y_test, test_predictions, labels=labels)

    print("Confusion matrix (rows = actual, columns = predicted)")
    print(pd.DataFrame(matrix, index=labels, columns=labels))
    print()

    print("=" * 64)
    print("STEP 5  Evidence: feature importance and sample predictions")
    print("=" * 64)

    fitted_preprocessor = best_pipeline.named_steps["preprocessor"]
    fitted_model = best_pipeline.named_steps["model"]

    importance_frame = aggregate_importance(
        fitted_preprocessor,
        fitted_model.feature_importances_,
        feature_names,
    )
    importance_frame.to_csv(
        ARTIFACT_DIR / "feature_importance.csv", index=False
    )

    top_features = importance_frame.head(15)

    plt.figure(figsize=(10, 7))
    plt.barh(
        top_features["feature"][::-1],
        top_features["importance"][::-1],
        color="#3b6ea5",
    )
    plt.xlabel("Aggregated feature importance")
    plt.title(f"Feature importance - {best_name}")
    plt.tight_layout()
    plt.savefig(ARTIFACT_DIR / "feature_importance.png", dpi=150)
    plt.close()

    print(
        "Importance mapped to declared inputs : "
        f"{importance_frame['importance'].sum():.4f}"
    )
    print()
    print(importance_frame.head(15).to_string(index=False))

    class_names = list(fitted_model.classes_)
    probability_columns = [
        f"probability_{name}" for name in class_names
    ]

    probabilities = best_pipeline.predict_proba(X_test)

    prediction_frame = pd.DataFrame(
        probabilities, columns=probability_columns
    )
    prediction_frame.insert(0, "claim_id", test_df["claim_id"].to_numpy())
    prediction_frame.insert(
        1, "actual_class", test_df["claim_class"].to_numpy()
    )
    prediction_frame.insert(2, "predicted_class", test_predictions)
    prediction_frame["top_class"] = prediction_frame[
        probability_columns
    ].idxmax(axis=1).str.replace("probability_", "", regex=False)
    prediction_frame["top_confidence"] = prediction_frame[
        probability_columns
    ].max(axis=1).round(4)
    prediction_frame["is_correct"] = (
        prediction_frame["actual_class"]
        == prediction_frame["predicted_class"]
    )
    prediction_frame["model_version"] = MODEL_VERSION

    sample_predictions = pd.concat(
        [
            group.sample(n=10, random_state=RANDOM_STATE)
            for _, group in prediction_frame.groupby("actual_class")
        ]
    ).sort_values("claim_id").reset_index(drop=True)

    sample_predictions.to_csv(
        ARTIFACT_DIR / "sample_test_predictions.csv", index=False
    )

    print()
    print(
        f"Sample predictions : {len(sample_predictions)} unseen test claims "
        f"({int(sample_predictions['is_correct'].sum())} correct, "
        f"{int((~sample_predictions['is_correct']).sum())} incorrect)"
    )

    transformed_width = fitted_preprocessor.transform(X_train).shape[1]

    joblib.dump(best_pipeline, ARTIFACT_DIR / "final_pipeline.joblib", compress=3)
    joblib.dump(feature_names, ARTIFACT_DIR / "feature_names.joblib")
    joblib.dump(
        best_pipeline.named_steps["preprocessor"],
        ARTIFACT_DIR / "preprocessor.joblib",
    )

    plt.figure(figsize=(8, 6))
    sns.heatmap(
        matrix,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=labels,
        yticklabels=labels,
    )
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.title(f"Test Confusion Matrix - {best_name}")
    plt.tight_layout()
    plt.savefig(ARTIFACT_DIR / "confusion_matrix.png", dpi=150)
    plt.close()

    metrics = {
        "generated_by": "ml/train_model.py",
        "model_version": MODEL_VERSION,
        "random_state": RANDOM_STATE,
        "hyperparameters": json_safe(fitted_model.get_params()),
        "dataset": {
            "train_rows": int(len(train_df)),
            "validation_rows": int(len(validation_df)),
            "test_rows": int(len(test_df)),
            "model_features": len(feature_names),
            "transformed_features": int(transformed_width),
        },
        "selection_rule": "highest validation macro F1",
        "selected_model": best_name,
        "validation_results": validation_results,
        "cross_validation_f1_macro": {
            "mean": round(float(cross_validation.mean()), 4),
            "std": round(float(cross_validation.std()), 4),
            "folds": [round(float(v), 4) for v in cross_validation],
        },
                "test_results": test_results,
        "test_per_class": test_report,
        "feature_importance": {
            "mapped_total": round(
                float(importance_frame["importance"].sum()), 6
            ),
            "top_15": json_safe(
                importance_frame.head(15).to_dict(orient="records")
            ),
        },
        "sample_predictions": {
            "file": "models/tabular/sample_test_predictions.csv",
            "rows": int(len(sample_predictions)),
            "correct": int(sample_predictions["is_correct"].sum()),
        },
    
        
    }

    (ARTIFACT_DIR / "metrics.json").write_text(
        json.dumps(json_safe(metrics), indent=2),
        encoding="utf-8",
    )

    (ARTIFACT_DIR / "classification_report.txt").write_text(
        classification_report(y_test, test_predictions, zero_division=0),
        encoding="utf-8",
    )

    print("=" * 64)
    print("SAVED ARTIFACTS")
    print("=" * 64)

    for path in sorted(ARTIFACT_DIR.iterdir()):
        print(f"  {path.name:32s} {path.stat().st_size:>10,d} bytes")

        print()
    print(f"Model version : {MODEL_VERSION}")
    print(f"Test accuracy : {test_results['accuracy']:.2%}")
    print(f"Test macro F1 : {test_results['f1_macro']:.2%}")

if __name__ == "__main__":
    main()