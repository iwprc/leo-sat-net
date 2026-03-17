#!/usr/bin/env python3
"""Sweep clustering thresholds for constellation shells.

Given a TLE file, this script clusters satellites in the (altitude_km, inclination_deg)
space using a rectangular neighborhood criterion:

  |alt_i - alt_j| <= altitude_tolerance_km AND |inc_i - inc_j| <= inclination_tolerance_deg

Clusters are computed as connected components (i.e., transitive closure) using a grid
index + union-find for efficiency.

It prints, for each (alt_tol, inc_tol) pair, the sizes of the top-k largest clusters.

Example:
  python sweep_shell_clustering.py tles.txt --alt 1 5 10 --inc 0.01 0.1 1 --top-k 3
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from typing import DefaultDict, Dict, Iterable, List, Tuple

from divide_constellation_shells import TLEParser


@dataclass
class UnionFind:
    parent: List[int]
    size: List[int]

    @classmethod
    def create(cls, n: int) -> "UnionFind":
        return cls(parent=list(range(n)), size=[1] * n)

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


def cluster_top_sizes(
    satellites: List[Dict],
    altitude_tolerance_km: float,
    inclination_tolerance_deg: float,
    top_k: int,
) -> List[int]:
    n = len(satellites)
    if n == 0:
        return []

    # Build grid index
    bins: DefaultDict[Tuple[int, int], List[int]] = defaultdict(list)
    altitudes = [s["altitude"] for s in satellites]
    inclinations = [s["inclination"] for s in satellites]

    for i in range(n):
        key = (
            _cell_index(altitudes[i], altitude_tolerance_km),
            _cell_index(inclinations[i], inclination_tolerance_deg),
        )
        bins[key].append(i)

    uf = UnionFind.create(n)

    # For each point, compare to points in the 3x3 neighborhood of its cell.
    # Only compare j > i to avoid duplicate checks.
    for (a_bin, i_bin), indices in bins.items():
        neighbor_cells = [
            (a_bin + da, i_bin + di)
            for da in (-1, 0, 1)
            for di in (-1, 0, 1)
        ]
        for idx in indices:
            a0 = altitudes[idx]
            i0 = inclinations[idx]
            for nb in neighbor_cells:
                for j in bins.get(nb, []):
                    if j <= idx:
                        continue
                    if abs(a0 - altitudes[j]) <= altitude_tolerance_km and abs(i0 - inclinations[j]) <= inclination_tolerance_deg:
                        uf.union(idx, j)

    # Aggregate component sizes
    comp_sizes: Dict[int, int] = {}
    for i in range(n):
        r = uf.find(i)
        comp_sizes[r] = comp_sizes.get(r, 0) + 1

    sizes_sorted = sorted(comp_sizes.values(), reverse=True)
    return sizes_sorted[:top_k]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sweep shell clustering thresholds and report top-k cluster sizes.")
    parser.add_argument("tle_file", help="Input TLE file")
    parser.add_argument("--alt", nargs="+", type=float, required=True, help="Altitude tolerances in km (space-separated)")
    parser.add_argument("--inc", nargs="+", type=float, required=True, help="Inclination tolerances in degrees (space-separated)")
    parser.add_argument("--top-k", type=int, default=3, help="How many largest clusters to report (default: 3)")

    args = parser.parse_args()

    satellites = TLEParser.read_tle_file(args.tle_file)
    print(f"Loaded {len(satellites)} satellites from {args.tle_file}")
    print()

    # Header
    print("alt_tol_km\tinc_tol_deg\ttop_sizes")
    for alt_tol in args.alt:
        for inc_tol in args.inc:
            top_sizes = cluster_top_sizes(
                satellites,
                altitude_tolerance_km=alt_tol,
                inclination_tolerance_deg=inc_tol,
                top_k=args.top_k,
            )
            print(f"{alt_tol:g}\t\t{inc_tol:g}\t\t{top_sizes}")


if __name__ == "__main__":
    main()
