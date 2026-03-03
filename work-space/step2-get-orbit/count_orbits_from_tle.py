#!/usr/bin/env python3
import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SatelliteRecord:
    name: str
    satnum: str
    inclination_deg: float
    raan_deg: float


def _parse_tle_records(tle_path: Path) -> list[SatelliteRecord]:
    lines = [line.rstrip("\n") for line in tle_path.read_text(encoding="utf-8", errors="ignore").splitlines()]

    records: list[SatelliteRecord] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        if line.startswith("1 ") and i + 1 < len(lines):
            name = ""
            l1 = lines[i]
            l2 = lines[i + 1].strip()
            i += 2
        elif i + 2 < len(lines) and lines[i + 1].strip().startswith("1 ") and lines[i + 2].strip().startswith("2 "):
            name = lines[i].strip()
            l1 = lines[i + 1]
            l2 = lines[i + 2].strip()
            i += 3
        else:
            i += 1
            continue

        if not l1.strip().startswith("1 ") or not l2.startswith("2 "):
            continue

        satnum = l1[2:7].strip()
        try:
            parts = l2.split()
            inclination_deg = float(parts[2])
            raan_deg = float(parts[3]) % 360.0
        except (ValueError, IndexError):
            continue

        records.append(
            SatelliteRecord(
                name=name,
                satnum=satnum,
                inclination_deg=inclination_deg,
                raan_deg=raan_deg,
            )
        )

    return records


def _cluster_by_raan(raans: list[float], threshold_deg: float) -> list[list[float]]:
    if not raans:
        return []

    sorted_raans = sorted(raans)
    clusters: list[list[float]] = [[sorted_raans[0]]]

    for current in sorted_raans[1:]:
        prev = clusters[-1][-1]
        if current - prev <= threshold_deg:
            clusters[-1].append(current)
        else:
            clusters.append([current])

    if len(clusters) > 1 and (sorted_raans[0] + 360.0 - sorted_raans[-1]) <= threshold_deg:
        merged = clusters[-1] + clusters[0]
        clusters = [merged] + clusters[1:-1]

    return clusters


def _circular_mean_deg(values: list[float]) -> float:
    if not values:
        return 0.0
    x = sum(math.cos(math.radians(v)) for v in values)
    y = sum(math.sin(math.radians(v)) for v in values)
    ang = math.degrees(math.atan2(y, x))
    return ang % 360.0


def main() -> None:
    parser = argparse.ArgumentParser(description="统计星座轨道面数量和每个轨道面的卫星数量")
    parser.add_argument("tle_file", type=Path, help="TLE 文件路径")
    parser.add_argument(
        "--raan-threshold",
        type=float,
        default=2.0,
        help="RAAN 聚类阈值（度），默认 2.0",
    )
    parser.add_argument(
        "--min-inclination",
        type=float,
        default=None,
        help="可选：只统计倾角 >= 该值的卫星",
    )
    parser.add_argument(
        "--max-inclination",
        type=float,
        default=None,
        help="可选：只统计倾角 <= 该值的卫星",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="可选：导出统计结果到 CSV 文件",
    )
    args = parser.parse_args()

    records = _parse_tle_records(args.tle_file)
    if args.min_inclination is not None:
        records = [r for r in records if r.inclination_deg >= args.min_inclination]
    if args.max_inclination is not None:
        records = [r for r in records if r.inclination_deg <= args.max_inclination]

    if not records:
        print("未解析到任何有效卫星记录。")
        return

    raans = [r.raan_deg for r in records]
    clusters = _cluster_by_raan(raans, args.raan_threshold)
    clusters = sorted(clusters, key=_circular_mean_deg)

    print(f"卫星总数: {len(records)}")
    print(f"轨道数(轨道面数): {len(clusters)}")
    print("每个轨道的卫星数:")
    output_rows: list[tuple[int, int, float]] = []
    for idx, cluster in enumerate(clusters, start=1):
        mean_raan = _circular_mean_deg(cluster)
        output_rows.append((idx, len(cluster), mean_raan))
        print(f"  轨道 {idx:02d}: {len(cluster):4d} 颗 (平均RAAN={mean_raan:7.3f}°)")

    if args.output_csv is not None:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["orbit_index", "satellite_count", "mean_raan_deg"])
            writer.writerows(output_rows)
        print(f"已导出CSV: {args.output_csv}")


if __name__ == "__main__":
    main()
