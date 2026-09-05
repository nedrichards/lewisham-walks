#!/usr/bin/env python3
"""Measure network-independent planning against the bundled discovery corpus.

Run with PYTHONPATH=src python3 scripts/benchmark_planner.py.
"""

from statistics import median
from time import perf_counter

from lewisham_walks.models import Coordinate, RouteRequest
from lewisham_walks.planner import RoutePlanner
from lewisham_walks.store import load_seed_cultural_venues, load_seed_discoveries, load_seed_listed_buildings


def main() -> None:
    discoveries = load_seed_discoveries() + load_seed_listed_buildings() + load_seed_cultural_venues()
    planner = RoutePlanner(discoveries)
    print(f"Bundled discoveries: {len(discoveries)}; 20 runs per scenario; no network")
    for name, coordinate in (("Lewisham", Coordinate(51.462, -0.01)), ("Distant start", Coordinate(55, 0))):
        request = RouteRequest(coordinate, 60)
        samples = []
        for _ in range(20):
            started = perf_counter()
            planner.plan(request)
            samples.append((perf_counter() - started) * 1000)
        print(f"{name}: median {median(samples):.2f} ms, maximum {max(samples):.2f} ms")


if __name__ == "__main__":
    main()
