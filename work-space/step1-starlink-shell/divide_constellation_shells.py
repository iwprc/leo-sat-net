#!/usr/bin/env python3
"""
Program to divide satellite constellation shells based on altitude and inclination.

This program reads TLE (Two-Line Element Set) data, calculates orbital parameters,
and groups satellites into shells based on similar altitude and inclination values.

Usage:
    python divide_constellation_shells.py <input_tle_file> [options]

Examples:
    # Cluster into shells (transitive closure) and write per-shell TLE files
    python divide_constellation_shells.py tles.txt --altitude-tolerance 1 --inclination-tolerance 0.1 --output-tle-dir shells_tle

    # Additionally write per-shell statistics
    python divide_constellation_shells.py tles.txt --output-shell-stats-csv out/shell_stats.csv --output-shell-stats-json out/shell_stats.json
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Tuple

import numpy as np


class TLEParser:
    """Parse TLE (Two-Line Element Set) data and calculate orbital parameters."""

    EARTH_RADIUS_KM = 6371.0  # Mean Earth radius in kilometers

    def __init__(self):
        pass

    @staticmethod
    def parse_tle_line_2(line: str) -> Dict[str, float]:
        """
        Parse TLE line 2 to extract orbital parameters.

        TLE Line 2 format:
        Line 2: 2 NNNNNC NNNNN IIIII.IIII RRRRR.RRRR EEEEE MMMMM NNNNNN NNNNNNNNN
        Where:
        - IIIII.IIII = Inclination (degrees)
        - RRRRR.RRRR = Right Ascension of Ascending Node (degrees)
        - EEEEE = Eccentricity (0.EEEEE)
        - MMMMM = Argument of Perigee (degrees)
        - NNNNNN = Mean Anomaly (degrees)
        - NNNNNN = Mean Motion (revolutions per day)
        """
        try:
            inclination = float(line[8:16].strip())
            mean_motion = float(line[52:63].strip())
            eccentricity = float("0." + line[26:33].strip())

            # Calculate semi-major axis using Kepler's third law
            # n = sqrt(GM / a^3), where n is mean motion in radians per minute
            # Converting mean motion from revolutions per day to radians per minute
            mean_motion_rad_per_min = (mean_motion * 2 * np.pi) / (24 * 60)

            # GM = 398600.4418 km^3/s^2 (standard gravitational parameter for Earth)
            # a = (GM / n^2)^(1/3)
            GM = 398600.4418
            a = (GM / (mean_motion_rad_per_min / 60) ** 2) ** (1 / 3)

            # Calculate altitude (semi-major axis - Earth's radius)
            altitude = a - TLEParser.EARTH_RADIUS_KM

            return {
                "inclination": inclination,
                "altitude": altitude,
                "eccentricity": eccentricity,
                "mean_motion": mean_motion,
                "semi_major_axis": a,
            }
        except (ValueError, IndexError) as e:
            raise ValueError(f"Failed to parse TLE line 2: {line}") from e

    @staticmethod
    def read_tle_file(filename: str) -> List[Dict]:
        """
        Read TLE file and parse satellite data.

        TLE file format (variant without header line):
        Line 1: Satellite name
        Line 2: TLE line 1
        Line 3: TLE line 2
        """
        satellites = []
        try:
            with open(filename, "r") as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                if i + 2 >= len(lines):
                    break

                name_line = lines[i].strip()
                tle1 = lines[i + 1].strip()
                tle2 = lines[i + 2].strip()

                # Skip empty lines
                if not name_line or not tle1 or not tle2:
                    i += 1
                    continue

                try:
                    # Extract satellite ID from name
                    sat_id = name_line.split("-")[-1].strip() if "-" in name_line else name_line.split()[-1].strip()

                    orbital_params = TLEParser.parse_tle_line_2(tle2)

                    satellites.append(
                        {
                            "name": name_line,
                            "id": sat_id,
                            "tle1": tle1,
                            "tle2": tle2,
                            **orbital_params,
                        }
                    )
                except (ValueError, IndexError) as e:
                    print(f"Warning: Skipping satellite {name_line}: {e}")

                i += 3

        except FileNotFoundError:
            raise FileNotFoundError(f"TLE file not found: {filename}")

        return satellites


class ConstellationShellDivider:
    """Divide satellites into constellation shells based on orbital parameters."""

    def __init__(self, altitude_tolerance: float = 100, inclination_tolerance: float = 0.5):
        """
        Initialize the shell divider.

        Args:
            altitude_tolerance: Altitude tolerance in km for grouping satellites
            inclination_tolerance: Inclination tolerance in degrees for grouping satellites
        """
        self.altitude_tolerance = altitude_tolerance
        self.inclination_tolerance = inclination_tolerance

    def divide_into_shells(self, satellites: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Divide satellites into shells using transitive-closure clustering (connected components)
        based on altitude and inclination.

        Two satellites are considered neighbors if:
            |alt_i - alt_j| <= altitude_tolerance AND |inc_i - inc_j| <= inclination_tolerance

        Shells are the connected components under this neighbor relation.

        Returns:
            Dictionary mapping shell_id to list of satellites in that shell.
        """
        if not satellites:
            return {}

        class _UnionFind:
            def __init__(self, n: int):
                self.parent = list(range(n))
                self.size = [1] * n

            def find(self, x: int) -> int:
                while self.parent[x] != x:
                    self.parent[x] = self.parent[self.parent[x]]
                    x = self.parent[x]
                return x

            def union(self, a: int, b: int) -> None:
                ra = self.find(a)
                rb = self.find(b)
                if ra == rb:
                    return
                if self.size[ra] < self.size[rb]:
                    ra, rb = rb, ra
                self.parent[rb] = ra
                self.size[ra] += self.size[rb]

        def _cell_index(value: float, cell_size: float) -> int:
            # floor division is fine because altitude/inclination are non-negative here
            return int(value // cell_size)

        n = len(satellites)
        altitudes = [s["altitude"] for s in satellites]
        inclinations = [s["inclination"] for s in satellites]

        bins: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)
        for i in range(n):
            key = (
                _cell_index(altitudes[i], self.altitude_tolerance),
                _cell_index(inclinations[i], self.inclination_tolerance),
            )
            bins[key].append(i)

        uf = _UnionFind(n)

        # Only compare points within the 3x3 neighborhood of each grid cell.
        # Compare j > i to avoid duplicate checks.
        for (a_bin, i_bin), indices in bins.items():
            neighbor_cells = [(a_bin + da, i_bin + di) for da in (-1, 0, 1) for di in (-1, 0, 1)]
            for idx in indices:
                a0 = altitudes[idx]
                i0 = inclinations[idx]
                for nb in neighbor_cells:
                    for j in bins.get(nb, []):
                        if j <= idx:
                            continue
                        if (
                            abs(a0 - altitudes[j]) <= self.altitude_tolerance
                            and abs(i0 - inclinations[j]) <= self.inclination_tolerance
                        ):
                            uf.union(idx, j)

        # Group satellites by component root
        comps: DefaultDict[int, List[int]] = defaultdict(list)
        for i in range(n):
            comps[uf.find(i)].append(i)

        # Deterministic shell ids: sort components by (mean altitude, mean inclination, size desc)
        comp_summaries = []
        for root, idxs in comps.items():
            mean_alt = float(np.mean([altitudes[i] for i in idxs]))
            mean_inc = float(np.mean([inclinations[i] for i in idxs]))
            comp_summaries.append((mean_alt, mean_inc, -len(idxs), root))
        comp_summaries.sort()

        shells: Dict[int, List[Dict]] = {}
        for shell_id, (_, _, _, root) in enumerate(comp_summaries):
            shells[shell_id] = [satellites[i] for i in comps[root]]

        return shells

    def divide_into_shells_grid(self, satellites: List[Dict]) -> Dict[Tuple, List[Dict]]:
        """
        Divide satellites into shells using grid-based binning.

        Returns:
            Dictionary mapping (altitude_bin, inclination_bin) to list of satellites.
        """
        if not satellites:
            return {}

        shells = defaultdict(list)

        for sat in satellites:
            # Calculate bin indices
            altitude_bin = int(sat["altitude"] / self.altitude_tolerance)
            inclination_bin = int(sat["inclination"] / self.inclination_tolerance)

            shells[(altitude_bin, inclination_bin)].append(sat)

        return dict(shells)

    @staticmethod
    def analyze_shells(shells: Dict) -> Dict:
        """
        Analyze shell characteristics.

        Returns:
            Dictionary with shell statistics.
        """
        analysis = {
            "num_shells": len(shells),
            "total_satellites": 0,
            "shells": {},
        }

        for shell_id, satellites_in_shell in shells.items():
            altitudes = [s["altitude"] for s in satellites_in_shell]
            inclinations = [s["inclination"] for s in satellites_in_shell]

            shell_stats = {
                "num_satellites": len(satellites_in_shell),
                "altitude_range": (min(altitudes), max(altitudes)),
                "altitude_mean": np.mean(altitudes),
                "altitude_std": np.std(altitudes),
                "inclination_range": (min(inclinations), max(inclinations)),
                "inclination_mean": np.mean(inclinations),
                "inclination_std": np.std(inclinations),
            }

            analysis["shells"][shell_id] = shell_stats
            analysis["total_satellites"] += len(satellites_in_shell)

        return analysis


def print_shell_summary(shells: Dict, analysis: Dict):
    """Print a summary of shell division."""
    print("\n" + "=" * 80)
    print("CONSTELLATION SHELL DIVISION SUMMARY")
    print("=" * 80)

    print(f"\nTotal Shells: {analysis['num_shells']}")
    print(f"Total Satellites: {analysis['total_satellites']}")

    # Sort shells by number of satellites (descending)
    sorted_shells = sorted(analysis["shells"].items(), key=lambda x: x[1]["num_satellites"], reverse=True)

    print("\nShell Details:")
    print("-" * 80)
    print(f"{'Shell':<8} {'Satellites':<12} {'Altitude (km)':<25} {'Inclination (°)':<15}")
    print("-" * 80)

    for shell_id, stats in sorted_shells:
        alt_range = stats["altitude_range"]
        inc_range = stats["inclination_range"]

        print(
            f"{shell_id:<8} {stats['num_satellites']:<12} "
            f"{alt_range[0]:>8.1f} - {alt_range[1]:>8.1f}  "
            f"{inc_range[0]:>6.2f} - {inc_range[1]:>6.2f}"
        )

    print("-" * 80)


def _safe_stats(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {"min": None, "max": None, "mean": None, "std": None, "median": None}

    vmin = float(min(values))
    vmax = float(max(values))
    median = float(np.median(values))
    mean = float(np.mean(values))
    std = 0.0 if len(values) == 1 else float(np.std(values))
    return {"min": vmin, "max": vmax, "mean": mean, "std": std, "median": median}


def compute_shell_stats(shells: Dict[int, List[Dict]]) -> Tuple[Dict[int, Dict], Dict]:
    """Compute per-shell statistics similar to summarize_shells.py output."""
    stats_by_shell: Dict[int, Dict] = {}

    rows_seen = 0
    missing_altitude = 0
    missing_inclination = 0

    for shell_id, sats in shells.items():
        rows_seen += len(sats)
        altitudes = []
        inclinations = []
        eccentricities = []
        mean_motions = []

        for s in sats:
            alt = s.get("altitude")
            inc = s.get("inclination")
            if alt is None or not np.isfinite(alt):
                missing_altitude += 1
            else:
                altitudes.append(float(alt))

            if inc is None or not np.isfinite(inc):
                missing_inclination += 1
            else:
                inclinations.append(float(inc))

            ecc = s.get("eccentricity")
            if ecc is not None and np.isfinite(ecc):
                eccentricities.append(float(ecc))

            mm = s.get("mean_motion")
            if mm is not None and np.isfinite(mm):
                mean_motions.append(float(mm))

        stats_by_shell[shell_id] = {
            "shell_id": shell_id,
            "count": len(sats),
            "altitude_km": _safe_stats(altitudes),
            "inclination_deg": _safe_stats(inclinations),
            "eccentricity": _safe_stats(eccentricities) if eccentricities else None,
            "mean_motion_rev_per_day": _safe_stats(mean_motions) if mean_motions else None,
        }

    overall = {
        "rows_seen": rows_seen,
        "shells": len(stats_by_shell),
        "missing_altitude": missing_altitude,
        "missing_inclination": missing_inclination,
    }

    return stats_by_shell, overall


def write_shell_stats_csv(stats_by_shell: Dict[int, Dict], out_csv_path: str) -> None:
    import csv

    out_path = Path(out_csv_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def get(d: Dict, path: str):
        cur = d
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

    with open(out_path, "w", newline="") as f:
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


def write_shell_stats_json(stats_by_shell: Dict[int, Dict], overall: Dict, out_json_path: str) -> None:
    out_path = Path(out_json_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "overall": overall,
        "shells": [stats_by_shell[sid] for sid in sorted(stats_by_shell.keys())],
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=False)


def export_shells_to_tle_files(shells: Dict, output_dir: str, file_prefix: str = "shell"):
    """Export each shell to a separate TLE file (3 lines per satellite: name, tle1, tle2)."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for shell_id in sorted(shells.keys(), key=lambda k: str(k)):
        sats = shells[shell_id]
        out_path = out_dir / f"{file_prefix}_{shell_id}.tle"
        with open(out_path, "w") as f:
            for sat in sats:
                # Preserve original input lines for compatibility.
                f.write(f"{sat['name']}\n")
                f.write(f"{sat['tle1']}\n")
                f.write(f"{sat['tle2']}\n")
        written += 1

    print(f"\nWrote {written} shell TLE file(s) to: {out_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Divide satellite constellation shells based on altitude and inclination.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage with default tolerances
  python divide_constellation_shells.py tles.txt
  
  # Custom tolerances
  python divide_constellation_shells.py tles.txt --altitude-tolerance 50 --inclination-tolerance 1.0
  
    # Export each shell as its own TLE file
    python divide_constellation_shells.py tles.txt --output-tle-dir shells_tle
  
  # Use grid-based binning instead of clustering
  python divide_constellation_shells.py tles.txt --method grid
        """,
    )

    parser.add_argument("tle_file", help="Input TLE file")
    parser.add_argument(
        "--altitude-tolerance",
        type=float,
        default=100,
        help="Altitude tolerance in km for grouping (default: 100)",
    )
    parser.add_argument(
        "--inclination-tolerance",
        type=float,
        default=0.5,
        help="Inclination tolerance in degrees for grouping (default: 0.5)",
    )
    parser.add_argument(
        "--method",
        choices=["clustering", "grid"],
        default="clustering",
        help="Division method: clustering or grid-based binning (default: clustering)",
    )
    parser.add_argument(
        "--output-tle-dir",
        default=None,
        help="If set, export each shell to a separate .tle file in this directory (TLE 3-line format).",
    )
    parser.add_argument(
        "--output-tle-prefix",
        default="shell",
        help="Prefix for per-shell TLE output files (default: shell).",
    )
    parser.add_argument(
        "--output-shell-stats-csv",
        default=None,
        help="If set, write per-shell summary statistics CSV to this path.",
    )
    parser.add_argument(
        "--output-shell-stats-json",
        default=None,
        help="If set, write per-shell summary statistics JSON to this path.",
    )

    args = parser.parse_args()

    # Parse TLE file
    print(f"Reading TLE file: {args.tle_file}")
    parser_tle = TLEParser()
    satellites = parser_tle.read_tle_file(args.tle_file)
    print(f"Loaded {len(satellites)} satellites")

    # Divide into shells
    print(f"\nDividing satellites into shells...")
    print(f"  Altitude tolerance: {args.altitude_tolerance} km")
    print(f"  Inclination tolerance: {args.inclination_tolerance}°")
    print(f"  Method: {args.method}")

    divider = ConstellationShellDivider(
        altitude_tolerance=args.altitude_tolerance, inclination_tolerance=args.inclination_tolerance
    )

    if args.method == "clustering":
        shells = divider.divide_into_shells(satellites)
    else:
        shells = divider.divide_into_shells_grid(satellites)

    # Analyze results
    analysis = divider.analyze_shells(shells)

    # Print summary
    print_shell_summary(shells, analysis)

    if args.output_tle_dir:
        export_shells_to_tle_files(shells, args.output_tle_dir, file_prefix=args.output_tle_prefix)

    if args.output_shell_stats_csv or args.output_shell_stats_json:
        stats_by_shell, overall = compute_shell_stats(shells)
        if args.output_shell_stats_csv:
            write_shell_stats_csv(stats_by_shell, args.output_shell_stats_csv)
            print(f"Wrote shell stats CSV: {args.output_shell_stats_csv}")
        if args.output_shell_stats_json:
            write_shell_stats_json(stats_by_shell, overall, args.output_shell_stats_json)
            print(f"Wrote shell stats JSON: {args.output_shell_stats_json}")

    # Print detailed altitude and inclination ranges
    print("\n" + "=" * 80)
    print("OVERALL CONSTELLATION CHARACTERISTICS")
    print("=" * 80)

    all_altitudes = [s["altitude"] for s in satellites]
    all_inclinations = [s["inclination"] for s in satellites]

    print(f"\nAltitude Statistics:")
    print(f"  Min:  {min(all_altitudes):>8.2f} km")
    print(f"  Max:  {max(all_altitudes):>8.2f} km")
    print(f"  Mean: {np.mean(all_altitudes):>8.2f} km")
    print(f"  Std:  {np.std(all_altitudes):>8.2f} km")

    print(f"\nInclination Statistics:")
    print(f"  Min:  {min(all_inclinations):>8.4f}°")
    print(f"  Max:  {max(all_inclinations):>8.4f}°")
    print(f"  Mean: {np.mean(all_inclinations):>8.4f}°")
    print(f"  Std:  {np.std(all_inclinations):>8.4f}°")


if __name__ == "__main__":
    main()
