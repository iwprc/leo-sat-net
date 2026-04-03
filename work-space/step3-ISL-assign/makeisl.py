#!/usr/bin/env python3

import argparse
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import DefaultDict, Dict, Iterable, List, Sequence, Set, Tuple

import numpy as np
from sgp4.api import Satrec, jday


EARTH_MU_KM3_S2 = 398600.4418
START_TIME_UTC = datetime(2026, 4, 3, 0, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Satellite:
    sid: int
    name: str
    tle1: str
    tle2: str
    satrec: Satrec
    semi_major_axis_km: float
    inclination_deg: float
    raan_deg: float


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, value: int) -> int:
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1


def normalize_deg(angle_deg: float) -> float:
    return angle_deg % 360.0


def shortest_signed_delta_deg(source_deg: float, target_deg: float) -> float:
    return (target_deg - source_deg + 180.0) % 360.0 - 180.0


def forward_delta_deg(source_deg: float, target_deg: float) -> float:
    return (target_deg - source_deg) % 360.0


def parse_three_line_tles(tle_path: Path) -> List[Satellite]:
    raw_lines = [line.rstrip("\n") for line in tle_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    start_index = 0
    if raw_lines:
        first_parts = raw_lines[0].split()
        if len(first_parts) == 2 and all(part.isdigit() for part in first_parts):
            start_index = 1

    payload_lines = raw_lines[start_index:]
    if len(payload_lines) % 3 != 0:
        raise ValueError(f"TLE file must contain groups of three non-empty lines: {tle_path}")

    satellites: List[Satellite] = []
    for offset in range(0, len(payload_lines), 3):
        name = payload_lines[offset].strip()
        tle1 = payload_lines[offset + 1].strip()
        tle2 = payload_lines[offset + 2].strip()

        inclination_deg = float(tle2[8:16].strip())
        raan_deg = normalize_deg(float(tle2[17:25].strip()))
        mean_motion_rev_per_day = float(tle2[52:63].strip())
        mean_motion_rad_per_s = mean_motion_rev_per_day * 2.0 * math.pi / 86400.0
        semi_major_axis_km = (EARTH_MU_KM3_S2 / (mean_motion_rad_per_s ** 2)) ** (1.0 / 3.0)

        satellites.append(
            Satellite(
                sid=len(satellites),
                name=name,
                tle1=tle1,
                tle2=tle2,
                satrec=Satrec.twoline2rv(tle1, tle2),
                semi_major_axis_km=semi_major_axis_km,
                inclination_deg=inclination_deg,
                raan_deg=raan_deg,
            )
        )

    return satellites


def build_sample_times(start_time: datetime, duration_minutes: int, interval_minutes: int) -> Tuple[np.ndarray, np.ndarray]:
    minute_offsets = list(range(0, duration_minutes + 1, interval_minutes))
    jd_values: List[float] = []
    fr_values: List[float] = []
    for minute_offset in minute_offsets:
        current = start_time + timedelta(minutes=minute_offset)
        second = current.second + current.microsecond / 1_000_000.0
        jd_value, fr_value = jday(current.year, current.month, current.day, current.hour, current.minute, second)
        jd_values.append(jd_value)
        fr_values.append(fr_value)
    return np.asarray(jd_values, dtype=np.float64), np.asarray(fr_values, dtype=np.float64)


def propagate_positions(
    satellites: Sequence[Satellite],
    jd_values: np.ndarray,
    fr_values: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    positions_km = np.empty((len(satellites), len(jd_values), 3), dtype=np.float64)
    velocities_km_s = np.empty((len(satellites), 3), dtype=np.float64)

    for satellite in satellites:
        errors, sat_positions, sat_velocities = satellite.satrec.sgp4_array(jd_values, fr_values)
        if np.any(errors != 0):
            first_error = int(errors[np.nonzero(errors)[0][0]])
            raise RuntimeError(f"SGP4 propagation failed for satellite {satellite.sid} ({satellite.name}): error {first_error}")
        positions_km[satellite.sid] = sat_positions
        velocities_km_s[satellite.sid] = sat_velocities[0]

    return positions_km, velocities_km_s


def compute_argument_of_latitude_deg(position_km: np.ndarray, velocity_km_s: np.ndarray) -> float:
    angular_momentum = np.cross(position_km, velocity_km_s)
    angular_momentum_norm = np.linalg.norm(angular_momentum)
    if angular_momentum_norm == 0.0:
        raise ValueError("Angular momentum vector is zero")
    angular_momentum_hat = angular_momentum / angular_momentum_norm

    ascending_node = np.cross(np.array([0.0, 0.0, 1.0]), angular_momentum)
    ascending_node_norm = np.linalg.norm(ascending_node)
    if ascending_node_norm == 0.0:
        ascending_node = np.array([1.0, 0.0, 0.0])
        ascending_node_norm = 1.0
    ascending_node_hat = ascending_node / ascending_node_norm

    quarter_turn_hat = np.cross(angular_momentum_hat, ascending_node_hat)
    angle_deg = math.degrees(
        math.atan2(
            float(np.dot(position_km, quarter_turn_hat)),
            float(np.dot(position_km, ascending_node_hat)),
        )
    )
    return normalize_deg(angle_deg)


def compute_geocentric_angle_deg(position_a_km: np.ndarray, position_b_km: np.ndarray) -> float:
    denominator = np.linalg.norm(position_a_km) * np.linalg.norm(position_b_km)
    if denominator == 0.0:
        raise ValueError("Cannot compute geocentric angle for zero-length position vector")
    cosine = float(np.dot(position_a_km, position_b_km) / denominator)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def build_index(satellites: Sequence[Satellite]) -> DefaultDict[Tuple[int, int, int], List[int]]:
    index: DefaultDict[Tuple[int, int, int], List[int]] = defaultdict(list)
    for satellite in satellites:
        sma_bin = int(math.floor(satellite.semi_major_axis_km))
        inc_bin = int(math.floor(satellite.inclination_deg))
        raan_bin = int(math.floor(satellite.raan_deg)) % 360
        index[(sma_bin, inc_bin, raan_bin)].append(satellite.sid)
    return index


def iter_candidate_ids(
    satellite: Satellite,
    index: DefaultDict[Tuple[int, int, int], List[int]],
    min_raan_offset_deg: int,
    max_raan_offset_deg: int,
) -> Iterable[int]:
    seen: Set[int] = set()
    sma_bin = int(math.floor(satellite.semi_major_axis_km))
    inc_bin = int(math.floor(satellite.inclination_deg))
    raan_bin = int(math.floor(satellite.raan_deg)) % 360

    for sma_delta in (-1, 0, 1):
        for inc_delta in (-1, 0, 1):
            for raan_delta in range(min_raan_offset_deg, max_raan_offset_deg + 1):
                candidate_bin = (sma_bin + sma_delta, inc_bin + inc_delta, (raan_bin + raan_delta) % 360)
                for candidate_id in index.get(candidate_bin, []):
                    if candidate_id == satellite.sid or candidate_id in seen:
                        continue
                    seen.add(candidate_id)
                    yield candidate_id


class IslBuilder:
    def __init__(
        self,
        satellites: Sequence[Satellite],
        positions_km: np.ndarray,
        velocities_km_s: np.ndarray,
    ) -> None:
        self.satellites = list(satellites)
        self.positions_km = positions_km
        self.index = build_index(satellites)
        self.argument_of_latitude_deg = [
            compute_argument_of_latitude_deg(positions_km[satellite.sid, 0], velocities_km_s[satellite.sid])
            for satellite in satellites
        ]
        self.geocentric_angle_cache: Dict[Tuple[int, int], float] = {}
        self.average_distance_cache: Dict[Tuple[int, int], float] = {}

    def average_distance_km(self, sat_a: int, sat_b: int) -> float:
        key = (sat_a, sat_b) if sat_a < sat_b else (sat_b, sat_a)
        cached = self.average_distance_cache.get(key)
        if cached is not None:
            return cached
        diff = self.positions_km[key[0]] - self.positions_km[key[1]]
        distances = np.sqrt(np.sum(diff * diff, axis=1))
        average_distance = float(distances.mean())
        self.average_distance_cache[key] = average_distance
        return average_distance

    def get_geocentric_angle_deg(self, sat_a: int, sat_b: int) -> float:
        key = (sat_a, sat_b) if sat_a < sat_b else (sat_b, sat_a)
        cached = self.geocentric_angle_cache.get(key)
        if cached is not None:
            return cached
        angle_deg = compute_geocentric_angle_deg(self.positions_km[key[0], 0], self.positions_km[key[1], 0])
        self.geocentric_angle_cache[key] = angle_deg
        return angle_deg

    def generate_intra_orbit_isls(self) -> List[Tuple[int, int]]:
        forward_used = [False] * len(self.satellites)
        backward_used = [False] * len(self.satellites)
        edges: List[Tuple[int, int]] = []

        for satellite in self.satellites:
            if forward_used[satellite.sid]:
                continue

            best_candidate = None
            best_distance = None
            for candidate_id in iter_candidate_ids(satellite, self.index, -1, 1):
                candidate = self.satellites[candidate_id]
                if backward_used[candidate_id]:
                    continue
                if abs(satellite.semi_major_axis_km - candidate.semi_major_axis_km) >= 1.0:
                    continue
                if abs(satellite.inclination_deg - candidate.inclination_deg) >= 1.0:
                    continue
                if abs(shortest_signed_delta_deg(satellite.raan_deg, candidate.raan_deg)) >= 2.0:
                    continue

                relative_argument = forward_delta_deg(
                    self.argument_of_latitude_deg[satellite.sid],
                    self.argument_of_latitude_deg[candidate_id],
                )
                if not (1.0 <= relative_argument <= 31.0):
                    continue

                distance_km = self.average_distance_km(satellite.sid, candidate_id)
                if best_distance is None or distance_km < best_distance:
                    best_candidate = candidate_id
                    best_distance = distance_km

            if best_candidate is None:
                continue

            forward_used[satellite.sid] = True
            backward_used[best_candidate] = True
            edge = (min(satellite.sid, best_candidate), max(satellite.sid, best_candidate))
            edges.append(edge)

        return edges

    def build_orbits_from_intra_isls(self, intra_edges: Sequence[Tuple[int, int]]) -> List[List[int]]:
        intra_connected: Set[int] = set()
        union_find = UnionFind(len(self.satellites))
        for left, right in intra_edges:
            intra_connected.add(left)
            intra_connected.add(right)
            union_find.union(left, right)

        components: DefaultDict[int, List[int]] = defaultdict(list)
        for satellite_id in intra_connected:
            components[union_find.find(satellite_id)].append(satellite_id)

        ordered_orbits: List[List[int]] = []
        for orbit_members in components.values():
            ordered_orbits.append(
                sorted(orbit_members, key=lambda sat_id: self.argument_of_latitude_deg[sat_id])
            )
        ordered_orbits.sort(key=lambda orbit_members: orbit_members[0])
        return ordered_orbits

    def generate_inter_orbit_isls(self, orbits: Sequence[Sequence[int]]) -> List[Tuple[int, int]]:
        side_used = [False] * len(self.satellites)
        edges: List[Tuple[int, int]] = []

        for orbit_members in orbits:
            tag = 0
            for satellite_id in orbit_members:
                if side_used[satellite_id]:
                    continue

                satellite = self.satellites[satellite_id]
                if tag == 0:
                    candidate_range = (-31, 0)
                else:
                    candidate_range = (0, 31)

                best_candidate = None
                best_distance = None
                for candidate_id in iter_candidate_ids(satellite, self.index, candidate_range[0], candidate_range[1]):
                    candidate = self.satellites[candidate_id]
                    if side_used[candidate_id]:
                        continue
                    if abs(satellite.semi_major_axis_km - candidate.semi_major_axis_km) >= 1.0:
                        continue
                    if abs(satellite.inclination_deg - candidate.inclination_deg) >= 1.0:
                        continue

                    relative_raan = shortest_signed_delta_deg(satellite.raan_deg, candidate.raan_deg)
                    if tag == 0 and not (-31.0 <= relative_raan <= -1.0):
                        continue
                    if tag == 1 and not (1.0 <= relative_raan <= 31.0):
                        continue
                    if self.get_geocentric_angle_deg(satellite_id, candidate_id) >= 31.0:
                        continue

                    distance_km = self.average_distance_km(satellite_id, candidate_id)
                    if best_distance is None or distance_km < best_distance:
                        best_candidate = candidate_id
                        best_distance = distance_km

                if best_candidate is None:
                    continue

                side_used[satellite_id] = True
                side_used[best_candidate] = True
                edge = (min(satellite_id, best_candidate), max(satellite_id, best_candidate))
                edges.append(edge)
                tag ^= 1

        return edges


def write_isls(output_path: Path, edges: Sequence[Tuple[int, int]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for left, right in sorted(set(edges)):
            handle.write(f"{left} {right}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ISLs from a 3-line TLE file.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).with_name("starlink-TLE-20260403.txt"),
        help="Input TLE file in three-line format.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("isls.txt"),
        help="Output ISL file path.",
    )
    parser.add_argument(
        "--start-time",
        default=START_TIME_UTC.strftime("%Y-%m-%dT%H:%M:%SZ"),
        help="Sampling start time in UTC, format YYYY-MM-DDTHH:MM:SSZ.",
    )
    parser.add_argument(
        "--duration-minutes",
        type=int,
        default=100,
        help="Sampling horizon in minutes.",
    )
    parser.add_argument(
        "--sample-interval-minutes",
        type=int,
        default=1,
        help="Sampling interval in minutes.",
    )
    return parser.parse_args()


def parse_start_time(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def main() -> None:
    args = parse_args()
    if args.duration_minutes <= 0:
        raise ValueError("duration-minutes must be positive")
    if args.sample_interval_minutes <= 0:
        raise ValueError("sample-interval-minutes must be positive")

    satellites = parse_three_line_tles(args.input)
    start_time = parse_start_time(args.start_time)
    jd_values, fr_values = build_sample_times(start_time, args.duration_minutes, args.sample_interval_minutes)
    positions_km, velocities_km_s = propagate_positions(satellites, jd_values, fr_values)

    builder = IslBuilder(satellites, positions_km, velocities_km_s)
    intra_edges = builder.generate_intra_orbit_isls()
    orbits = builder.build_orbits_from_intra_isls(intra_edges)
    inter_edges = builder.generate_inter_orbit_isls(orbits)

    all_edges = intra_edges + inter_edges
    write_isls(args.output, all_edges)

    print(f"satellites={len(satellites)}")
    print(f"intra_orbit_isls={len(intra_edges)}")
    print(f"orbits={len(orbits)}")
    print(f"inter_orbit_isls={len(inter_edges)}")
    print(f"total_isls={len(set(all_edges))}")
    print(f"output={args.output}")


if __name__ == "__main__":
    main()