#!/usr/bin/env python3

import argparse
import csv
import json
import math
import os
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


def _to_float(value: str) -> Optional[float]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _to_int(value: str) -> Optional[int]:
    if value is None:
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        try:
            return int(float(v))
        except ValueError:
            return None


def read_kept_satellites(summary_csv_path: str) -> Set[str]:
    kept: Set[str] = set()
    with open(summary_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty CSV: {summary_csv_path}")
        required = {"satellite_name", "kept"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Missing columns in summary CSV {summary_csv_path}: {sorted(missing)}"
            )

        for row in reader:
            if row.get("kept") == "1":
                name = (row.get("satellite_name") or "").strip()
                if name:
                    kept.add(name)
    return kept


@dataclass(frozen=True)
class ClusterRow:
    shell_id: int
    satellite_name: str
    altitude_km: Optional[float]
    inclination_deg: Optional[float]
    eccentricity: Optional[float]
    mean_motion_rev_per_day: Optional[float]


def read_clusters(clusters_csv_path: str) -> List[ClusterRow]:
    rows: List[ClusterRow] = []
    with open(clusters_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"Empty CSV: {clusters_csv_path}")

        # The mean motion column name has changed a few times during iterations.
        fieldnames = set(reader.fieldnames)
        mean_motion_col = None
        for cand in (
            "mean_motion",
            "mean_motion_rev_per_day",
            "mean_motion_revs_per_day",
            "mean_motion_revday",
            "mean_motion_rev_per_day ",
            "mean_motion_rev_per_day\n",
            "mean_motion_rev_per_day\r",
            "mean_motion_rev_per_day\t",
            "mean_motion_rev_per_day\u2028",
            "mean_motion_rev_per_day\u2029",
            "mean_motion",  # duplicated intentionally
            "me_an_motion",  # observed from a wrapped header display
        ):
            if cand in fieldnames:
                mean_motion_col = cand
                break

        required = {"shell_id", "satellite_name", "altitude_km", "inclination_deg"}
        missing = required - fieldnames
        if missing:
            raise ValueError(
                f"Missing columns in clusters CSV {clusters_csv_path}: {sorted(missing)}\n"
                f"Found columns: {sorted(fieldnames)}"
            )

        for row in reader:
            shell_id = _to_int(row.get("shell_id") or "")
            if shell_id is None:
                continue
            name = (row.get("satellite_name") or "").strip()
            if not name:
                continue

            altitude_km = _to_float(row.get("altitude_km") or "")
            inclination_deg = _to_float(row.get("inclination_deg") or "")
            eccentricity = _to_float(row.get("eccentricity") or "") if "eccentricity" in fieldnames else None
            mean_motion = _to_float(row.get(mean_motion_col) or "") if mean_motion_col else None

            rows.append(
                ClusterRow(
                    shell_id=int(shell_id),
                    satellite_name=name,
                    altitude_km=altitude_km,
                    inclination_deg=inclination_deg,
                    eccentricity=eccentricity,
                    mean_motion_rev_per_day=mean_motion,
                )
            )

    return rows


def _safe_stats(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {
            "min": None,
            "max": None,
            "mean": None,
            "std": None,
            "median": None,
        }

    vmin = min(values)
    vmax = max(values)
    mean = statistics.fmean(values)
    median = statistics.median(values)

    # Population stddev is stable for small samples; return 0 when n==1.
    if len(values) == 1:
        std = 0.0
    else:
        std = statistics.pstdev(values)

    return {
        "min": vmin,
        "max": vmax,
        "mean": mean,
        "std": std,
        "median": median,
    }


def summarize_by_shell(rows: Iterable[ClusterRow]) -> Tuple[Dict[int, Dict[str, Any]], Dict[str, Any]]:
    by_shell: Dict[int, Dict[str, List[float]]] = {}
    counts: Dict[int, int] = {}

    def ensure(shell_id: int) -> Dict[str, List[float]]:
        if shell_id not in by_shell:
            by_shell[shell_id] = {
                "altitude_km": [],
                "inclination_deg": [],
                "eccentricity": [],
                "mean_motion_rev_per_day": [],
            }
        return by_shell[shell_id]

    total = 0
    missing_alt = 0
    missing_inc = 0

    for r in rows:
        total += 1
        d = ensure(r.shell_id)
        counts[r.shell_id] = counts.get(r.shell_id, 0) + 1
        if r.altitude_km is not None and math.isfinite(r.altitude_km):
            d["altitude_km"].append(r.altitude_km)
        else:
            missing_alt += 1

        if r.inclination_deg is not None and math.isfinite(r.inclination_deg):
            d["inclination_deg"].append(r.inclination_deg)
        else:
            missing_inc += 1

        if r.eccentricity is not None and math.isfinite(r.eccentricity):
            d["eccentricity"].append(r.eccentricity)

        if r.mean_motion_rev_per_day is not None and math.isfinite(r.mean_motion_rev_per_day):
            d["mean_motion_rev_per_day"].append(r.mean_motion_rev_per_day)

    stats_by_shell: Dict[int, Dict[str, Any]] = {}
    for shell_id, v in by_shell.items():
        stats_by_shell[shell_id] = {
            "shell_id": shell_id,
            "count": counts.get(shell_id, 0),
            "altitude_km": _safe_stats(v["altitude_km"]),
            "inclination_deg": _safe_stats(v["inclination_deg"]),
            "eccentricity": _safe_stats(v["eccentricity"]) if v["eccentricity"] else None,
            "mean_motion_rev_per_day": _safe_stats(v["mean_motion_rev_per_day"]) if v["mean_motion_rev_per_day"] else None,
        }

    overall = {
        "rows_seen": total,
        "shells": len(stats_by_shell),
        "missing_altitude": missing_alt,
        "missing_inclination": missing_inc,
    }

    return stats_by_shell, overall


def write_shell_stats_csv(stats_by_shell: Dict[int, Dict[str, Any]], out_csv_path: str) -> None:
    os.makedirs(os.path.dirname(out_csv_path) or ".", exist_ok=True)

    def get(d: Dict[str, Any], path: str) -> Any:
        cur: Any = d
        for part in path.split("."):
            if cur is None:
                return None
            cur = cur.get(part)
        return cur

    fieldnames = [
        "shell_id",
        "count",
        "altitude_min_km",
        "altitude_max_km",
        "altitude_mean_km",
        "altitude_std_km",
        "altitude_median_km",
        "inclination_min_deg",
        "inclination_max_deg",
        "inclination_mean_deg",
        "inclination_std_deg",
        "inclination_median_deg",
        "eccentricity_mean",
        "eccentricity_std",
        "mean_motion_mean_rev_per_day",
        "mean_motion_std_rev_per_day",
    ]

    with open(out_csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for shell_id in sorted(stats_by_shell.keys()):
            s = stats_by_shell[shell_id]
            row = {
                "shell_id": shell_id,
                "count": s.get("count"),
                "altitude_min_km": get(s, "altitude_km.min"),
                "altitude_max_km": get(s, "altitude_km.max"),
                "altitude_mean_km": get(s, "altitude_km.mean"),
                "altitude_std_km": get(s, "altitude_km.std"),
                "altitude_median_km": get(s, "altitude_km.median"),
                "inclination_min_deg": get(s, "inclination_deg.min"),
                "inclination_max_deg": get(s, "inclination_deg.max"),
                "inclination_mean_deg": get(s, "inclination_deg.mean"),
                "inclination_std_deg": get(s, "inclination_deg.std"),
                "inclination_median_deg": get(s, "inclination_deg.median"),
                "eccentricity_mean": get(s, "eccentricity.mean"),
                "eccentricity_std": get(s, "eccentricity.std"),
                "mean_motion_mean_rev_per_day": get(s, "mean_motion_rev_per_day.mean"),
                "mean_motion_std_rev_per_day": get(s, "mean_motion_rev_per_day.std"),
            }
            w.writerow(row)


def write_shell_stats_json(
    stats_by_shell: Dict[int, Dict[str, Any]], overall: Dict[str, Any], out_json_path: str
) -> None:
    os.makedirs(os.path.dirname(out_json_path) or ".", exist_ok=True)
    payload = {
        "overall": overall,
        "shells": [stats_by_shell[sid] for sid in sorted(stats_by_shell.keys())],
    }
    with open(out_json_path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Summarize per-shell statistics (count, altitude/inc stats, optionally ecc/mean-motion) "
            "from a clusters CSV. Optionally filter to kept satellites using summary.csv."
        )
    )
    ap.add_argument(
        "--clusters",
        required=True,
        help="Clusters CSV (e.g., shells_5km_01deg.csv)",
    )
    ap.add_argument(
        "--filter-summary",
        default=None,
        help="Optional summary.csv with a 'kept' column; if provided, only kept satellites are included",
    )
    ap.add_argument(
        "--out-dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    ap.add_argument(
        "--out-base",
        default="shell_stats",
        help="Output base filename (default: shell_stats -> shell_stats.csv/json)",
    )

    args = ap.parse_args()

    kept: Optional[Set[str]] = None
    if args.filter_summary:
        kept = read_kept_satellites(args.filter_summary)

    cluster_rows = read_clusters(args.clusters)
    if kept is not None:
        cluster_rows = [r for r in cluster_rows if r.satellite_name in kept]

    stats_by_shell, overall = summarize_by_shell(cluster_rows)

    out_csv = os.path.join(args.out_dir, f"{args.out_base}.csv")
    out_json = os.path.join(args.out_dir, f"{args.out_base}.json")
    write_shell_stats_csv(stats_by_shell, out_csv)
    write_shell_stats_json(stats_by_shell, overall, out_json)

    total = sum(s["count"] for s in stats_by_shell.values())
    print(f"Shells: {overall['shells']}  Satellites summarized: {total}")
    print(f"Wrote: {out_csv}")
    print(f"Wrote: {out_json}")


if __name__ == "__main__":
    main()
