"""Cross-tabulate this dashboard's tool outcomes against the AnVIL deployment's.

Two dashboards run the same suite in different places: this fork tests tools-iuc in
GitHub Actions, the AnVIL one tests a curated set on a deployed Galaxy. A tool that
fails in both is very likely a real tool problem. A tool that fails only on AnVIL is
much more likely to be the deployment, and one that fails only here points at the test
or the tool version this CI pins.

Both sides are judged on recurrence rather than a single run, because one bad run takes
out large blocks of tests at once: a tool counts as failing on a side when it failed in
at least half of that side's most recent runs.

Usage: compare_dashboards.py [--runs N] [--json OUT]
"""

import argparse
import json
import sys
import urllib.request

ANVIL_BASE = "https://anvilproject.github.io/galaxy-tests/raster-data"
LOCAL_MATRIX = "docs/tool-tests/data/matrix.json"
LOCAL_MANIFEST = "docs/tool-tests/data/manifest.json"
SENTINEL = "__SORTLIST__"
BAD = {"fail", "error", "mixed"}
# a run covering only the failing-package subset is not comparable to a full sweep
FULL_RUN_TOOLS = 1000


def short(tool_id: str) -> str:
    """AnVIL records full toolshed ids; this dashboard records the bare tool id."""
    return tool_id.rsplit("/", 1)[-1]


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def local(path: str) -> dict:
    with open(path) as handle:
        return json.load(handle)


def failure_rate(matrix: dict, runs: int, only: set[str] | None = None) -> dict[str, tuple[int, int]]:
    """tool -> (runs it failed in, runs it appeared in), over the most recent `runs`."""
    usable = [r for r in matrix["runs"] if only is None or r in only]
    recent = usable[-runs:]
    out = {}
    for tool, by_run in matrix["cells"].items():
        if tool == SENTINEL:
            continue
        seen = [by_run[r] for r in recent if r in by_run]
        if not seen:
            continue
        out[short(tool)] = (sum(1 for c in seen if c.get("status") in BAD), len(seen))
    return out


def full_runs(manifest_path: str) -> set[str]:
    with open(manifest_path) as handle:
        return {r["run_id"] for r in json.load(handle)
                if r["tools_attempted"] >= FULL_RUN_TOOLS}


def verdict(on_anvil: bool, on_iuc: bool) -> str:
    if on_anvil and on_iuc:
        return "tool"
    if on_anvil:
        return "deployment"
    if on_iuc:
        return "iuc-test"
    return "clean"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5, help="recent runs to judge on")
    parser.add_argument("--json", dest="out", help="write the full table here")
    parser.add_argument("--overlay", help="write the raster overlay here")
    parser.add_argument("--panel", help="write the aligned AnVIL cell block here")
    args = parser.parse_args(argv)

    anvil = failure_rate(fetch(f"{ANVIL_BASE}/matrix.json"), args.runs)
    iuc = failure_rate(local(LOCAL_MATRIX), args.runs, only=full_runs(LOCAL_MANIFEST))
    shared = sorted(set(anvil) & set(iuc))

    rows, counts = [], {"tool": 0, "deployment": 0, "iuc-test": 0, "clean": 0}
    for tool in shared:
        a_bad, a_seen = anvil[tool]
        i_bad, i_seen = iuc[tool]
        kind = verdict(a_bad * 2 >= a_seen, i_bad * 2 >= i_seen)
        counts[kind] += 1
        rows.append({"tool": tool, "verdict": kind,
                     "anvil": f"{a_bad}/{a_seen}", "iuc": f"{i_bad}/{i_seen}"})

    print(f"{len(anvil)} tools on AnVIL, {len(iuc)} here, {len(shared)} in both "
          f"(last {args.runs} runs each)\n")
    for kind, blurb in (("tool", "fails in both, likely a real tool problem"),
                        ("deployment", "fails only on AnVIL, likely the deployment"),
                        ("iuc-test", "fails only here, likely the test or the pinned version")):
        picked = [r for r in rows if r["verdict"] == kind]
        print(f"{kind.upper():11} {len(picked):4}  {blurb}")
        for r in picked[:15]:
            print(f"    {r['tool']:44} anvil {r['anvil']:>6}   iuc {r['iuc']:>6}")
        if len(picked) > 15:
            print(f"    ... and {len(picked) - 15} more")
        print()
    print(f"{'CLEAN':11} {counts['clean']:4}  passes in both")

    if args.out:
        with open(args.out, "w") as handle:
            json.dump({"runs_considered": args.runs, "counts": counts, "tools": rows},
                      handle, indent=1)
        print(f"\nwrote {args.out}")

    if args.panel:
        # Per-run cells for the shared tools only, so the raster can draw an aligned
        # AnVIL block without pulling their full matrix over the wire.
        raw = fetch(f"{ANVIL_BASE}/matrix.json")
        keep = set(shared)
        cells = {}
        for tool, by_run in raw["cells"].items():
            if tool == SENTINEL or short(tool) not in keep:
                continue
            cells[short(tool)] = {run: {"status": c.get("status"), "affected": c.get("affected", 1)}
                                  for run, c in by_run.items()}
        with open(args.panel, "w") as handle:
            json.dump({"runs": raw["runs"], "cells": cells}, handle, separators=(",", ":"))
        print(f"wrote {args.panel} ({len(cells)} tools x {len(raw['runs'])} runs)")

    if args.overlay:
        overlay = {r["tool"]: {"verdict": r["verdict"], "anvil": r["anvil"], "iuc": r["iuc"]}
                   for r in rows if r["verdict"] != "clean"}
        with open(args.overlay, "w") as handle:
            json.dump({"runs_considered": args.runs, "counts": counts, "tools": overlay},
                      handle, indent=1)
        print(f"wrote {args.overlay} ({len(overlay)} tools)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
