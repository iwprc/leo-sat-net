#!/usr/bin/env python3
import csv
import math
from pathlib import Path


def geodetic2cartesian(lat_degrees: float, lon_degrees: float, ele_m: float):
    a = 6378135.0
    f = 1.0 / 298.26
    e = math.sqrt(2.0 * f - f * f)

    lat = math.radians(lat_degrees)
    lon = math.radians(lon_degrees)

    v = a / math.sqrt(1.0 - e * e * math.sin(lat) * math.sin(lat))
    x = (v + ele_m) * math.cos(lat) * math.cos(lon)
    y = (v + ele_m) * math.cos(lat) * math.sin(lon)
    z = (v * (1.0 - e * e) + ele_m) * math.sin(lat)
    return x, y, z


def try_float(value: str):
    try:
        return float(value.strip())
    except Exception:
        return None


def main():
    base_dir = Path(__file__).resolve().parent
    src = base_dir / "ground_station_info.csv"
    out_basic = base_dir / "ground_stations.basic.txt"
    out_extended = base_dir / "ground_stations.txt"

    if not src.exists():
        raise FileNotFoundError(f"Input file not found: {src}")

    stations = []
    skipped = 0

    with src.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)

        for row in reader:
            if not row:
                continue

            # Skip obvious broken continuation lines (e.g., raw URL line)
            if len(row) < 3:
                skipped += 1
                continue

            name = row[0].strip()
            lon = try_float(row[1])
            lat = try_float(row[2])

            if lat is None or lon is None:
                skipped += 1
                continue

            if not name:
                name = "Unknown"

            # Hypatia parser uses plain line.split(',') rather than CSV parsing,
            # so the name field itself must not contain commas.
            name = " ".join(name.split()).replace(",", ";")

            stations.append((name, lat, lon, 0.0))

    with out_basic.open("w", encoding="utf-8", newline="") as fb, out_extended.open(
        "w", encoding="utf-8", newline=""
    ) as fe:
        for gid, (name, lat, lon, ele) in enumerate(stations):
            fb.write(f"{gid},{name},{lat:.6f},{lon:.6f},{ele:.1f}\n")
            x, y, z = geodetic2cartesian(lat, lon, ele)
            fe.write(f"{gid},{name},{lat:.6f},{lon:.6f},{ele:.1f},{x:.6f},{y:.6f},{z:.6f}\n")

    print(f"Generated {len(stations)} stations")
    print(f"Skipped {skipped} malformed rows")
    print(f"Basic: {out_basic}")
    print(f"Extended: {out_extended}")


if __name__ == "__main__":
    main()
