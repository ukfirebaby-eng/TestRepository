"""
ngs_ml_extractor.py — Novel Genesis System Phase J.2: Feature Extraction

Offline tool.  Iterates a completed (or partially completed) novel_output/
directory and produces ngs_ml_dataset.csv, the training dataset consumed by
train_overload_model.py.

Usage
-----
    python ngs_ml_extractor.py
    python ngs_ml_extractor.py --output-dir path/to/novel_output
    python ngs_ml_extractor.py --output-dir novel_output --beta-interval 5

Output
------
    ngs_ml_dataset.csv   (written to the current working directory)

CSV schema (8 columns)
-----------------------
    scene_num               int     scene index (1-based)
    start_active_characters int     characters present at start of scene
    start_unresolved_secrets int    InformationNodes with revealed_at_scene=None
    start_avg_tension       float   mean tension_level across RelationshipNodes
    start_avg_trust         float   mean trust_level  across RelationshipNodes
    start_pending_events    int     EventNodes where occurred=False
    y1_cognitive_load       int     1 if the scene required ≥1 revision, else 0
    y2_beta_score           float   desire-to-continue (0–10) or NaN

Notes
-----
* Scene 1 uses reconstruct_nse_at_scene(target_scene=0) — the foundation graph.
* Y2 is populated only for scenes where scene_num % beta_interval == 0.
* Requires ≥ 20 scenes to satisfy acceptance criterion AC-E1.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Optional

# ---------------------------------------------------------------------------
# Guard: pandas is an optional offline dependency
# ---------------------------------------------------------------------------
try:
    import pandas as pd
except ImportError:
    sys.exit(
        "ERROR: pandas is required for ngs_ml_extractor.py.\n"
        "Install it with:  pip install pandas"
    )

from nse_graph import reconstruct_nse_at_scene


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def get_revision_count(output_dir: Path, scene_num: int) -> int:
    """Return the number of revision passes for *scene_num*.

    Counts files matching audits/scene_{NN}_v*.md.  v0 is the initial audit;
    v1 and above are revision audits.  Returns max(0, count - 1).
    """
    pattern = str(output_dir / f"audits/scene_{scene_num:02d}_v*.md")
    audit_files = glob.glob(pattern)
    return max(0, len(audit_files) - 1)


def extract_beta_score(output_dir: Path, scene_num: int) -> Optional[int]:
    """Parse the desire-to-continue score from a Beta Reader report.

    Returns an int in [0, 10] if the report exists and the field can be
    parsed; returns None otherwise.
    """
    path = output_dir / f"audits/beta_report_scene_{scene_num:02d}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(r"desire.to.continue[^\d]*(\d+)", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

def extract_features_for_scene(
    initial_path: Path,
    log_path: Path,
    scene_num: int,
) -> dict:
    """Return the five topological features for *scene_num*.

    The graph state is measured at the end of scene ``scene_num - 1`` (i.e.
    the complexity that exists when prose generation for scene_num begins).
    """
    graph = reconstruct_nse_at_scene(
        initial_path=initial_path,
        log_path=log_path,
        target_scene=scene_num - 1,
    )

    rels = list(graph.relationships.values())

    return {
        "scene_num": scene_num,
        "start_active_characters": len(graph.characters),
        "start_unresolved_secrets": sum(
            1 for i in graph.information.values()
            if i.revealed_at_scene is None
        ),
        "start_avg_tension": (
            mean([r.tension_level for r in rels]) if rels else 0.0
        ),
        "start_avg_trust": (
            mean([r.trust_level for r in rels]) if rels else 0.0
        ),
        "start_pending_events": sum(
            1 for e in graph.events.values() if not e.occurred
        ),
    }


# ---------------------------------------------------------------------------
# Scene discovery
# ---------------------------------------------------------------------------

def discover_scene_numbers(output_dir: Path) -> list[int]:
    """Return a sorted list of scene numbers found in output_dir/scenes/.

    Looks for files matching scenes/scene_NN.md (two-digit zero-padded index).
    """
    pattern = str(output_dir / "scenes" / "scene_*.md")
    scene_files = sorted(glob.glob(pattern))
    numbers: list[int] = []
    for fpath in scene_files:
        m = re.search(r"scene_(\d+)\.md$", fpath)
        if m:
            numbers.append(int(m.group(1)))
    return sorted(numbers)


# ---------------------------------------------------------------------------
# Main extraction routine
# ---------------------------------------------------------------------------

def run_extraction(output_dir: Path, beta_interval: int) -> pd.DataFrame:
    """Build and return the full feature/label DataFrame.

    Parameters
    ----------
    output_dir:
        Root novel_output/ directory.
    beta_interval:
        Every Nth scene has a Beta Reader report (matching ngs_config.toml).
    """
    initial_path = output_dir / "nse" / "nse_graph.json"
    log_path = output_dir / "nse" / "mutation_log.jsonl"

    scene_numbers = discover_scene_numbers(output_dir)
    if not scene_numbers:
        sys.exit(
            f"ERROR: No scene files found in {output_dir / 'scenes'}.\n"
            "Ensure the novel_output/ directory contains at least one "
            "scenes/scene_NN.md file."
        )

    rows: list[dict] = []
    for n in scene_numbers:
        row = extract_features_for_scene(initial_path, log_path, scene_num=n)

        # Y1 — cognitive load label
        row["y1_cognitive_load"] = (
            1 if get_revision_count(output_dir, n) > 0 else 0
        )

        # Y2 — beta score (NaN for non-beta scenes)
        if n % beta_interval == 0:
            score = extract_beta_score(output_dir, n)
            row["y2_beta_score"] = float(score) if score is not None else float("nan")
        else:
            row["y2_beta_score"] = float("nan")

        rows.append(row)

    column_order = [
        "scene_num",
        "start_active_characters",
        "start_unresolved_secrets",
        "start_avg_tension",
        "start_avg_trust",
        "start_pending_events",
        "y1_cognitive_load",
        "y2_beta_score",
    ]
    return pd.DataFrame(rows, columns=column_order)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NGS Phase J.2 — Feature Extractor\n"
            "Produces ngs_ml_dataset.csv from a novel_output/ directory."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--output-dir",
        default="novel_output",
        metavar="DIR",
        help="Path to the novel_output/ directory (default: novel_output)",
    )
    parser.add_argument(
        "--beta-interval",
        type=int,
        default=10,
        metavar="N",
        help="Scenes between Beta Reader reports (default: 10)",
    )
    parser.add_argument(
        "--csv-out",
        default="ngs_ml_dataset.csv",
        metavar="FILE",
        help="Output CSV path (default: ngs_ml_dataset.csv)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir)

    if not output_dir.exists():
        sys.exit(f"ERROR: output directory not found: {output_dir}")

    print(f"[ngs_ml_extractor] Scanning {output_dir} …")
    df = run_extraction(output_dir, beta_interval=args.beta_interval)

    csv_path = Path(args.csv_out)
    df.to_csv(csv_path, index=False)

    beta_count = int(df["y2_beta_score"].notna().sum())
    print(
        f"[ngs_ml_extractor] Wrote {len(df)} scenes → {csv_path}\n"
        f"  Columns       : {list(df.columns)}\n"
        f"  Cognitive load: {int(df['y1_cognitive_load'].sum())} scenes "
        f"required revision\n"
        f"  Beta scores   : {beta_count} scenes have a beta report"
    )

    if len(df) < 20:
        print(
            f"  WARNING: Only {len(df)} scenes extracted. "
            "Acceptance criterion requires ≥ 20 scenes for reliable training."
        )

    if beta_count < 10:
        print(
            f"  WARNING: Only {beta_count} beta scenes found. "
            "The engagement correlator requires ≥ 10 beta reports. "
            f"Consider reducing beta_interval (current: {args.beta_interval}) "
            "in ngs_config.toml."
        )


if __name__ == "__main__":
    main()
