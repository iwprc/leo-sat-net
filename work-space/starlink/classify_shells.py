"""Group Starlink TLEs by orbital shell (altitude and inclination)."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


MU_EARTH_KM3_S2 = 398600.4418  # standard gravitational parameter (km^3/s^2)
EARTH_RADIUS_KM = 6378.137


@dataclass
class SatEntry:
    name: str
    line0: str
    line1: str
    line2: str
    inc_deg: float
    altitude_km: float


def parse_tles(path: Path) -> Iterable[SatEntry]:
    """Yield parsed satellites with original TLE lines kept intact."""

    lines: List[str] = path.read_text().splitlines()
    if len(lines) % 3 != 0:
        raise ValueError("TLE file must contain name + 2 lines per satellite")

    for i in range(0, len(lines), 3):
        line0 = lines[i]
        line1 = lines[i + 1]
        line2 = lines[i + 2]

        name = line0.strip()
        parts = line2.split()
        if len(parts) < 8:
            raise ValueError(f"Unexpected TLE line 2 format near {name!r}: {line2}")

        inclination_deg = float(parts[2])
        mean_motion_rev_per_day = float(parts[7])

        mean_motion_rad_s = mean_motion_rev_per_day * 2.0 * math.pi / 86400.0
        semi_major_axis_km = (MU_EARTH_KM3_S2 ** (1.0 / 3.0)) / (
            mean_motion_rad_s ** (2.0 / 3.0)
        )
        altitude_km = semi_major_axis_km - EARTH_RADIUS_KM

        yield SatEntry(
            name=name,
            line0=line0,
            line1=line1,
            line2=line2,
            inc_deg=inclination_deg,
            altitude_km=altitude_km,
        )


def group_shells(
    satellites: Iterable[SatEntry],
    alt_tol_km: float,
    inc_tol_deg: float,
):
    """Greedy grouping of satellites into shells based on tolerances.

    A satellite joins the first shell whose running mean altitude and inclination
    are both within the given tolerances; otherwise a new shell is created.
    """

    shells: List[dict] = []
    for sat in satellites:
        inc = sat.inc_deg
        alt = sat.altitude_km
        chosen = None
        for shell in shells:
            if (
                abs(alt - shell["mean_alt"]) <= alt_tol_km
                and abs(inc - shell["mean_inc"]) <= inc_tol_deg
            ):
                chosen = shell
                break

        if chosen is None:
            shells.append(
                {
                    "entries": [sat],
                    "count": 1,
                    "mean_alt": alt,
                    "mean_inc": inc,
                    "min_alt": alt,
                    "max_alt": alt,
                }
            )
        else:
            chosen["entries"].append(sat)
            chosen["count"] += 1
            # Update running mean to keep shells compact.
            chosen["mean_alt"] += (alt - chosen["mean_alt"]) / chosen["count"]
            chosen["mean_inc"] += (inc - chosen["mean_inc"]) / chosen["count"]
            chosen["min_alt"] = min(chosen["min_alt"], alt)
            chosen["max_alt"] = max(chosen["max_alt"], alt)

    shells.sort(key=lambda s: s["mean_alt"])
    return shells


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Group Starlink TLEs by orbital shell (altitude + inclination)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("tles.txt"),
        help="Path to tles.txt (default: alongside this script)",
    )
    parser.add_argument(
        "--alt-tol-km",
        type=float,
        default=30.0,
        help="Altitude tolerance in km for shell grouping",
    )
    parser.add_argument(
        "--inc-tol-deg",
        type=float,
        default=0.2,
        help="Inclination tolerance in degrees for shell grouping",
    )
    parser.add_argument(
        "--top-names",
        type=int,
        default=5,
        help="How many example satellite names to show per shell",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional path to write shell summary as CSV",
    )
    parser.add_argument(
        "--split-dir",
        type=Path,
        default=None,
        help="If set, write each shell's TLEs to this directory",
    )

    args = parser.parse_args()

    satellites = list(parse_tles(args.input))
    shells = group_shells(satellites, args.alt_tol_km, args.inc_tol_deg)

    print(f"Found {len(shells)} shells across {len(satellites)} satellites")
    for idx, shell in enumerate(shells, start=1):
        names_preview = ", ".join(
            entry.name for entry in shell["entries"][: args.top_names]
        )
        print(
            f"Shell {idx:02d}: alt≈{shell['mean_alt']:.1f} km (min {shell['min_alt']:.1f}, max {shell['max_alt']:.1f}), "
            f"inc≈{shell['mean_inc']:.3f}°, count={shell['count']}, examples=[{names_preview}]"
        )

    if args.output_csv:
        lines = ["shell_id,mean_alt_km,mean_inc_deg,count,names"]
        for idx, shell in enumerate(shells, start=1):
            names_joined = " ".join(entry.name for entry in shell["entries"])
            lines.append(
                f"{idx},{shell['mean_alt']:.3f},{shell['mean_inc']:.5f},{shell['count']},{names_joined}"
            )
        args.output_csv.write_text("\n".join(lines))
        print(f"CSV written to {args.output_csv}")

    if args.split_dir:
        args.split_dir.mkdir(parents=True, exist_ok=True)
        for idx, shell in enumerate(shells, start=1):
            out_path = args.split_dir / f"shell_{idx:02d}.txt"
            lines: List[str] = []
            for entry in shell["entries"]:
                lines.extend([entry.line0, entry.line1, entry.line2])
            out_path.write_text("\n".join(lines) + "\n")
            print(f"Shell {idx:02d} written to {out_path}")


if __name__ == "__main__":
    main()
