#!/usr/bin/env python3
"""Filter obvious outliers and split TLEs into per-cluster files.

Designed for the outputs produced by divide_constellation_shells.py.

Inputs:
  - Original 3-line-per-satellite TLE file (e.g., tles.txt)
  - Clustering CSV (e.g., shells_5km_01deg.csv)

Outlier filtering (defaults are conservative and adjustable):
  1) Drop entire clusters (shells) smaller than --min-shell-size (default: 5)
  2) Within each remaining shell, drop satellites with robust z-score (MAD-based)
     beyond thresholds in altitude or inclination.

Outputs:
  - A directory containing one TLE file per shell: shell_<id>.tle
  - outliers.tle containing removed satellites
  - summary.json and summary.csv describing what was kept/removed

Example:
  python filter_outliers_and_split_tles.py \
    --tles tles.txt \
    --clusters shells_5km_01deg.csv \
    --out-dir clusters_5km_01deg_filtered \
    --min-shell-size 5 \
    --alt-mad-z 6.0 \
    --inc-mad-z 6.0
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np


@dataclass(frozen=True)
class TleRecord:
    name: str
    line1: str
    line2: str


def read_3line_tle_file(path: Path) -> Dict[str, TleRecord]:
    """Read a 3-line-per-satellite TLE file into a dict keyed by stripped name."""
    records: Dict[str, TleRecord] = {}
    lines = path.read_text().splitlines()

    i = 0
    while i < len(lines):
        # Skip blank lines
        if not lines[i].strip():
            i += 1
            continue
        if i + 2 >= len(lines):
            break

        name = lines[i].strip()
        line1 = lines[i + 1].rstrip("\n")
        line2 = lines[i + 2].rstrip("\n")

        # Basic sanity: line1 starts with '1', line2 starts with '2'
        # Don’t be too strict to avoid dropping data.
        if not line1.lstrip().startswith("1") or not line2.lstrip().startswith("2"):
            # If file has unexpected formatting, try advancing by 1.
            i += 1
            continue

        records[name] = TleRecord(name=name, line1=line1, line2=line2)
        i += 3

    return records


def read_cluster_csv(path: Path) -> List[dict]:
    """Read clustering CSV rows."""
    rows: List[dict] = []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Normalize types
            row["shell_id"] = int(row["shell_id"])
            row["satellite_name"] = row["satellite_name"].strip()
            row["altitude_km"] = float(row["altitude_km"])
            row["inclination_deg"] = float(row["inclination_deg"])
            # optional fields exist; keep as strings
            rows.append(row)
    return rows


def mad(arr: np.ndarray) -> float:
    """Median absolute deviation (MAD)."""
    med = np.median(arr)
    return float(np.median(np.abs(arr - med)))


def robust_z_scores(arr: np.ndarray) -> np.ndarray:
    """Return robust z-scores using MAD: z = 0.6745 * (x - median) / MAD.

    If MAD == 0, returns zeros.
    """
    med = np.median(arr)
    scale = mad(arr)
    if scale == 0 or not np.isfinite(scale):
        return np.zeros_like(arr, dtype=float)
    return 0.6745 * (arr - med) / scale


def filter_outliers(
    rows: List[dict],
    min_shell_size: int,
    alt_mad_z: float,
    inc_mad_z: float,
) -> Tuple[List[dict], List[dict], dict]:
    """Filter outliers from clustering rows.

    Returns: (kept_rows, removed_rows, summary)
    """
    by_shell: Dict[int, List[dict]] = defaultdict(list)
    for r in rows:
        by_shell[r["shell_id"]].append(r)

    removed: List[dict] = []
    kept: List[dict] = []

    shell_summaries = {}

    for shell_id, shell_rows in sorted(by_shell.items(), key=lambda x: x[0]):
        shell_size = len(shell_rows)

        if shell_size < min_shell_size:
            for r in shell_rows:
                rr = dict(r)
                rr["outlier_reason"] = f"shell_size<{min_shell_size}"
                removed.append(rr)
            shell_summaries[str(shell_id)] = {
                "shell_size": shell_size,
                "kept": 0,
                "removed": shell_size,
                "rule": "min_shell_size",
            }
            continue

        alt = np.array([r["altitude_km"] for r in shell_rows], dtype=float)
        inc = np.array([r["inclination_deg"] for r in shell_rows], dtype=float)

        alt_z = np.abs(robust_z_scores(alt))
        inc_z = np.abs(robust_z_scores(inc))

        shell_kept = 0
        shell_removed = 0

        for r, az, iz in zip(shell_rows, alt_z, inc_z):
            if (alt_mad_z is not None and az > alt_mad_z) or (inc_mad_z is not None and iz > inc_mad_z):
                rr = dict(r)
                reasons = []
                if alt_mad_z is not None and az > alt_mad_z:
                    reasons.append(f"alt_mad_z>{alt_mad_z} (z={az:.2f})")
                if inc_mad_z is not None and iz > inc_mad_z:
                    reasons.append(f"inc_mad_z>{inc_mad_z} (z={iz:.2f})")
                rr["outlier_reason"] = "; ".join(reasons)
                removed.append(rr)
                shell_removed += 1
            else:
                kept.append(r)
                shell_kept += 1

        shell_summaries[str(shell_id)] = {
            "shell_size": shell_size,
            "kept": shell_kept,
            "removed": shell_removed,
            "rule": "mad_z",
            "alt_median": float(np.median(alt)),
            "alt_mad": float(mad(alt)),
            "inc_median": float(np.median(inc)),
            "inc_mad": float(mad(inc)),
        }

    summary = {
        "input_total": len(rows),
        "kept_total": len(kept),
        "removed_total": len(removed),
        "params": {
            "min_shell_size": min_shell_size,
            "alt_mad_z": alt_mad_z,
            "inc_mad_z": inc_mad_z,
        },
        "shells": shell_summaries,
    }

    return kept, removed, summary


def write_tles_by_shell(
    tles: Dict[str, TleRecord],
    kept_rows: List[dict],
    removed_rows: List[dict],
    out_dir: Path,
    outliers_filename: str = "outliers.tle",
) -> dict:
    """Write per-shell TLE files for kept satellites and one outliers file."""
    out_dir.mkdir(parents=True, exist_ok=True)

    by_shell_names: Dict[int, List[str]] = defaultdict(list)
    for r in kept_rows:
        by_shell_names[r["shell_id"]].append(r["satellite_name"])

    missing_in_tles = []

    # Write each shell
    for shell_id, names in sorted(by_shell_names.items(), key=lambda x: x[0]):
        out_path = out_dir / f"shell_{shell_id:03d}.tle"
        with out_path.open("w") as f:
            for name in names:
                rec = tles.get(name)
                if rec is None:
                    missing_in_tles.append(name)
                    continue
                f.write(rec.name + "\n")
                f.write(rec.line1 + "\n")
                f.write(rec.line2 + "\n")

    # Write outliers
    outliers_path = out_dir / outliers_filename
    with outliers_path.open("w") as f:
        for r in removed_rows:
            name = r["satellite_name"]
            rec = tles.get(name)
            if rec is None:
                missing_in_tles.append(name)
                continue
            f.write(rec.name + "\n")
            f.write(rec.line1 + "\n")
            f.write(rec.line2 + "\n")

    return {
        "shell_files": len(by_shell_names),
        "outliers_file": str(outliers_path),
        "missing_in_tles_count": len(set(missing_in_tles)),
        "missing_in_tles_samples": sorted(set(missing_in_tles))[:20],
    }


def write_summary_files(out_dir: Path, kept_rows: List[dict], removed_rows: List[dict], summary: dict) -> None:
    # summary.json
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    # summary.csv (one line per satellite)
    csv_path = out_dir / "summary.csv"
    fieldnames = [
        "satellite_name",
        "shell_id",
        "altitude_km",
        "inclination_deg",
        "kept",
        "outlier_reason",
    ]
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in kept_rows:
            writer.writerow(
                {
                    "satellite_name": r["satellite_name"],
                    "shell_id": r["shell_id"],
                    "altitude_km": r["altitude_km"],
                    "inclination_deg": r["inclination_deg"],
                    "kept": 1,
                    "outlier_reason": "",
                }
            )
        for r in removed_rows:
            writer.writerow(
                {
                    "satellite_name": r["satellite_name"],
                    "shell_id": r["shell_id"],
                    "altitude_km": r["altitude_km"],
                    "inclination_deg": r["inclination_deg"],
                    "kept": 0,
                    "outlier_reason": r.get("outlier_reason", ""),
                }
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="Remove obvious outliers and split clustered TLEs into separate files.")
    ap.add_argument("--tles", type=str, required=True, help="Original 3-line-per-satellite TLE file")
    ap.add_argument("--clusters", type=str, required=True, help="Clustering CSV (shells_*.csv)")
    ap.add_argument("--out-dir", type=str, required=True, help="Output directory")
    ap.add_argument("--min-shell-size", type=int, default=5, help="Drop shells smaller than this (default: 5)")
    ap.add_argument(
        "--alt-mad-z",
        type=float,
        default=6.0,
        help="Altitude MAD z-score threshold for outliers (default: 6.0; higher=less aggressive)",
    )
    ap.add_argument(
        "--inc-mad-z",
        type=float,
        default=6.0,
        help="Inclination MAD z-score threshold for outliers (default: 6.0; higher=less aggressive)",
    )
    args = ap.parse_args()

    tles_path = Path(args.tles)
    clusters_path = Path(args.clusters)
    out_dir = Path(args.out_dir)

    tles = read_3line_tle_file(tles_path)
    rows = read_cluster_csv(clusters_path)

    kept_rows, removed_rows, summary = filter_outliers(
        rows,
        min_shell_size=args.min_shell_size,
        alt_mad_z=args.alt_mad_z,
        inc_mad_z=args.inc_mad_z,
    )

    split_info = write_tles_by_shell(tles, kept_rows, removed_rows, out_dir)
    summary["split"] = split_info

    write_summary_files(out_dir, kept_rows, removed_rows, summary)

    print(f"Input satellites (from clusters csv): {summary['input_total']}")
    print(f"Kept: {summary['kept_total']}  Removed: {summary['removed_total']}")
    print(f"Shell files written: {split_info['shell_files']}")
    print(f"Outliers TLE: {split_info['outliers_file']}")
    if split_info["missing_in_tles_count"]:
        print(f"WARNING: {split_info['missing_in_tles_count']} satellites missing in TLE file")
        print(f"Samples: {split_info['missing_in_tles_samples']}")


if __name__ == "__main__":
    main()
