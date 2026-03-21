"""
train_overload_model.py — Novel Genesis System Phase J.2: Model Training

Offline tool.  Reads ngs_ml_dataset.csv (produced by ngs_ml_extractor.py)
and trains two independent predictors:

  Path A — Cognitive Overload Classifier
      sklearn RandomForestClassifier predicting y1_cognitive_load.
      Output: cognitive_overload_model.pkl (consumed at runtime by the pipeline).

  Path B — Engagement Correlation Engine
      Pearson correlation + high/low group comparison between NSE mutation
      delta features and y2_beta_score.  Output: terminal report only.

Usage
-----
    python train_overload_model.py
    python train_overload_model.py --csv ngs_ml_dataset.csv
    python train_overload_model.py --csv ngs_ml_dataset.csv --log-dir novel_output

Requirements
------------
    scikit-learn >= 1.3
    pandas       >= 2.0
    joblib       (bundled with scikit-learn)

Acceptance criteria
-------------------
AC-T1  Runs without error on the generated CSV.
AC-T2  cognitive_overload_model.pkl produced in the project root (or --pkl-out).
AC-T3  classification_report printed to stdout.
AC-T4  Engagement correlation report printed, ranked by Pearson r.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Guard: scikit-learn / pandas are optional offline dependencies
# ---------------------------------------------------------------------------
try:
    import pandas as pd
except ImportError:
    sys.exit(
        "ERROR: pandas is required.\n"
        "Install with:  pip install pandas"
    )

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    import joblib
except ImportError:
    sys.exit(
        "ERROR: scikit-learn is required.\n"
        "Install with:  pip install scikit-learn"
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FEATURES = [
    "start_active_characters",
    "start_unresolved_secrets",
    "start_avg_tension",
    "start_avg_trust",
    "start_pending_events",
]

DELTA_MUTATION_TYPES = {
    "delta_reveals":       "REVEAL_INFORMATION",
    "delta_concealments":  "CONCEAL_INFORMATION",
    "delta_rel_shifts":    "SHIFT_RELATIONSHIP",
    "delta_new_nodes":     "ADD_NODE",
    "delta_updates":       "UPDATE_NODE",
}
DELTA_COLS = list(DELTA_MUTATION_TYPES.keys())

MIN_BETA_SCENES_FOR_CORRELATION = 10


# ---------------------------------------------------------------------------
# Path A — Cognitive Overload Classifier
# ---------------------------------------------------------------------------

def train_overload_classifier(df: pd.DataFrame, pkl_out: Path) -> None:
    """Train a Random Forest classifier for y1_cognitive_load.

    Prints classification_report and confusion matrix to stdout, then saves
    the fitted model to *pkl_out*.
    """
    clf_df = df.dropna(subset=["y1_cognitive_load"]).copy()
    if clf_df.empty:
        print("[train] WARNING: No rows with y1_cognitive_load — skipping classifier.")
        return

    X = clf_df[FEATURES]
    y = clf_df["y1_cognitive_load"].astype(int)

    unique_classes = y.unique()
    if len(unique_classes) < 2:
        print(
            f"[train] WARNING: y1_cognitive_load has only one class "
            f"({unique_classes[0]}) — skipping classifier training.\n"
            "        Generate more scenes that require revisions to produce a "
            "meaningful binary dataset."
        )
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=0.2,
        stratify=y,
        random_state=42,
    )

    model = RandomForestClassifier(
        n_estimators=100,
        class_weight="balanced",
        random_state=42,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)

    print("=" * 60)
    print("COGNITIVE OVERLOAD CLASSIFIER — Evaluation")
    print("=" * 60)
    print(classification_report(y_test, y_pred, target_names=["clean_pass", "revision_required"]))
    print("Confusion matrix (rows=actual, cols=predicted):")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  {'':>20}  predicted_0  predicted_1")
    labels = ["actual_0 (clean)", "actual_1 (overload)"]
    for label, row in zip(labels, cm):
        print(f"  {label:<20}  {row[0]:>11}  {row[1]:>11}")
    print()

    # Feature importances
    print("Feature importances:")
    importances = sorted(
        zip(FEATURES, model.feature_importances_),
        key=lambda x: x[1],
        reverse=True,
    )
    for feat, imp in importances:
        bar = "█" * int(imp * 40)
        print(f"  {feat:<30} {imp:.4f}  {bar}")
    print()

    joblib.dump(model, pkl_out)
    print(f"[train] Model saved → {pkl_out}")


# ---------------------------------------------------------------------------
# Path B — Engagement Correlation Engine
# ---------------------------------------------------------------------------

def _load_mutation_counts(log_path: Path, scene_num: int) -> dict[str, int]:
    """Count mutations by type for *scene_num* in *log_path*.

    Returns a dict keyed by mutation_type (e.g. 'REVEAL_INFORMATION').
    """
    counts: dict[str, int] = {}
    if not log_path.exists():
        return counts
    try:
        with log_path.open(encoding="utf-8") as fh:
            for raw_line in fh:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    m = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if m.get("scene_num") == scene_num:
                    mt = m.get("mutation_type", "UNKNOWN")
                    counts[mt] = counts.get(mt, 0) + 1
    except OSError:
        pass
    return counts


def run_engagement_analysis(
    df: pd.DataFrame,
    log_dir: Path,
) -> None:
    """Compute Pearson correlations between NSE mutation deltas and beta scores.

    Prints a ranked 'Anatomy of a High-Engagement Scene' report.

    Parameters
    ----------
    df:
        Full dataset DataFrame (must contain y2_beta_score and scene_num).
    log_dir:
        Directory that contains nse/mutation_log.jsonl (usually novel_output/).
    """
    beta_df = df.dropna(subset=["y2_beta_score"]).copy()
    n_beta = len(beta_df)

    if n_beta < MIN_BETA_SCENES_FOR_CORRELATION:
        print(
            f"[engagement] WARNING: Only {n_beta} beta scenes found "
            f"(minimum required: {MIN_BETA_SCENES_FOR_CORRELATION}).\n"
            "        Reduce beta_interval in ngs_config.toml and regenerate "
            "more scenes before running the engagement analyser."
        )
        return

    log_path = log_dir / "nse" / "mutation_log.jsonl"

    # Build delta feature columns
    for col in DELTA_COLS:
        beta_df[col] = 0

    for idx, row in beta_df.iterrows():
        scene_num = int(row["scene_num"])
        counts = _load_mutation_counts(log_path, scene_num)
        for delta_col, mutation_type in DELTA_MUTATION_TYPES.items():
            beta_df.at[idx, delta_col] = counts.get(mutation_type, 0)

    # Pearson correlations
    corr = (
        beta_df[DELTA_COLS + ["y2_beta_score"]]
        .corr()["y2_beta_score"]
        .drop("y2_beta_score")
        .sort_values(ascending=False)
    )

    # High / low engagement groups
    high_df = beta_df[beta_df["y2_beta_score"] >= 7]
    low_df  = beta_df[beta_df["y2_beta_score"] <= 4]

    print("=" * 60)
    print("ENGAGEMENT ANALYSER — Anatomy of a High-Engagement Scene")
    print("=" * 60)
    print(f"  Beta scenes analysed : {n_beta}")
    print(f"  High engagement (≥7) : {len(high_df)} scenes")
    print(f"  Low  engagement (≤4) : {len(low_df)} scenes")
    print()
    print(f"{'Mutation category':<28}  {'Pearson r':>9}  "
          f"{'High μ':>7}  {'Low μ':>7}  {'Δ (high-low)':>12}")
    print("-" * 70)
    for delta_col in corr.index:
        r_val = corr[delta_col]
        high_mean = high_df[delta_col].mean() if not high_df.empty else float("nan")
        low_mean  = low_df[delta_col].mean()  if not low_df.empty  else float("nan")
        delta     = high_mean - low_mean
        direction = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
        label = delta_col.replace("delta_", "")
        print(
            f"  {label:<26}  {r_val:>+9.4f}  "
            f"{high_mean:>7.2f}  {low_mean:>7.2f}  "
            f"{direction} {abs(delta):>9.2f}"
        )
    print()

    top = corr.idxmax()
    print(f"  Strongest positive correlation: {top} (r={corr[top]:+.4f})")
    print(
        "  Interpretation: scenes with more of this mutation type tend to "
        "score higher on desire-to-continue."
    )
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NGS Phase J.2 — Model Trainer\n"
            "Trains the Cognitive Overload Classifier and prints the\n"
            "Engagement Correlation report."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--csv",
        default="ngs_ml_dataset.csv",
        metavar="FILE",
        help="Input CSV produced by ngs_ml_extractor.py (default: ngs_ml_dataset.csv)",
    )
    parser.add_argument(
        "--pkl-out",
        default="cognitive_overload_model.pkl",
        metavar="FILE",
        help="Output path for trained model (default: cognitive_overload_model.pkl)",
    )
    parser.add_argument(
        "--log-dir",
        default="novel_output",
        metavar="DIR",
        help=(
            "novel_output/ root directory; used to locate "
            "nse/mutation_log.jsonl for the engagement analyser "
            "(default: novel_output)"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    csv_path = Path(args.csv)
    pkl_out  = Path(args.pkl_out)
    log_dir  = Path(args.log_dir)

    if not csv_path.exists():
        sys.exit(
            f"ERROR: CSV file not found: {csv_path}\n"
            "Run ngs_ml_extractor.py first to generate the dataset."
        )

    df = pd.read_csv(csv_path)

    required_cols = set(FEATURES) | {"y1_cognitive_load", "y2_beta_score", "scene_num"}
    missing = required_cols - set(df.columns)
    if missing:
        sys.exit(
            f"ERROR: CSV is missing required columns: {sorted(missing)}\n"
            "Re-run ngs_ml_extractor.py to regenerate the dataset."
        )

    print(f"[train] Loaded {len(df)} rows from {csv_path}")
    print()

    # Path A: classifier
    train_overload_classifier(df, pkl_out)

    # Path B: engagement analysis
    run_engagement_analysis(df, log_dir)


if __name__ == "__main__":
    main()
