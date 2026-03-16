#!/usr/bin/env python3
"""
Program to divide satellite constellation shells based on altitude and inclination.

This program reads TLE (Two-Line Element Set) data, calculates orbital parameters,
and groups satellites into shells based on similar altitude and inclination values.

Usage:
    python divide_constellation_shells.py <input_tle_file> [options]
    python divide_constellation_shells.py tles.txt --altitude-tolerance 100 --inclination-tolerance 0.5
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

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
        Divide satellites into shells using clustering based on altitude and inclination.

        Returns:
            Dictionary mapping shell_id to list of satellites in that shell.
        """
        if not satellites:
            return {}

        shells = {}
        shell_id = 0
        used_satellites = set()

        # Sort by altitude then inclination for more consistent grouping
        sorted_sats = sorted(satellites, key=lambda x: (x["altitude"], x["inclination"]))

        for sat in sorted_sats:
            if id(sat) in used_satellites:
                continue

            # Start a new shell
            current_shell = [sat]
            used_satellites.add(id(sat))

            # Find all satellites within tolerance of this one
            for other_sat in sorted_sats:
                if id(other_sat) in used_satellites:
                    continue

                alt_diff = abs(sat["altitude"] - other_sat["altitude"])
                inc_diff = abs(sat["inclination"] - other_sat["inclination"])

                if alt_diff <= self.altitude_tolerance and inc_diff <= self.inclination_tolerance:
                    current_shell.append(other_sat)
                    used_satellites.add(id(other_sat))

            shells[shell_id] = current_shell
            shell_id += 1

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


def export_shells_to_csv(shells: Dict, output_file: str):
    """Export shell division results to CSV file."""
    with open(output_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["shell_id", "satellite_name", "satellite_id", "altitude_km", "inclination_deg", 
                        "eccentricity", "mean_motion"])

        # Sort by shell_id for consistent output
        for shell_id in sorted(shells.keys()):
            for sat in shells[shell_id]:
                writer.writerow(
                    [
                        shell_id,
                        sat["name"],
                        sat["id"],
                        f"{sat['altitude']:.2f}",
                        f"{sat['inclination']:.4f}",
                        f"{sat['eccentricity']:.6f}",
                        f"{sat['mean_motion']:.8f}",
                    ]
                )

    print(f"\nResults exported to: {output_file}")


def export_shells_to_json(shells: Dict, analysis: Dict, output_file: str):
    """Export shell division results to JSON file."""
    json_data = {
        "metadata": {
            "total_shells": analysis["num_shells"],
            "total_satellites": analysis["total_satellites"],
        },
        "shells": {},
    }

    for shell_id, satellites_in_shell in shells.items():
        shell_id_str = str(shell_id)
        json_data["shells"][shell_id_str] = {
            "num_satellites": len(satellites_in_shell),
            "satellites": [
                {
                    "name": s["name"],
                    "id": s["id"],
                    "altitude_km": round(s["altitude"], 2),
                    "inclination_deg": round(s["inclination"], 4),
                    "eccentricity": round(s["eccentricity"], 6),
                    "mean_motion": round(s["mean_motion"], 8),
                }
                for s in satellites_in_shell
            ],
            "statistics": {
                "altitude_mean": round(analysis["shells"][shell_id]["altitude_mean"], 2),
                "altitude_std": round(analysis["shells"][shell_id]["altitude_std"], 2),
                "altitude_range": [
                    round(analysis["shells"][shell_id]["altitude_range"][0], 2),
                    round(analysis["shells"][shell_id]["altitude_range"][1], 2),
                ],
                "inclination_mean": round(analysis["shells"][shell_id]["inclination_mean"], 4),
                "inclination_std": round(analysis["shells"][shell_id]["inclination_std"], 4),
                "inclination_range": [
                    round(analysis["shells"][shell_id]["inclination_range"][0], 4),
                    round(analysis["shells"][shell_id]["inclination_range"][1], 4),
                ],
            },
        }

    with open(output_file, "w") as f:
        json.dump(json_data, f, indent=2)

    print(f"Results exported to: {output_file}")


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
  
  # Export results
  python divide_constellation_shells.py tles.txt --output-csv shells.csv --output-json shells.json
  
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
        "--output-csv",
        help="Output CSV file path",
    )
    parser.add_argument(
        "--output-json",
        help="Output JSON file path",
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

    # Export results
    if args.output_csv:
        export_shells_to_csv(shells, args.output_csv)

    if args.output_json:
        export_shells_to_json(shells, analysis, args.output_json)

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
