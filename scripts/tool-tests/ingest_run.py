"""Ingest a tools-iuc `Tool suite tests` run into data/tool-tests/.

The earlier `Async submission comparison test` workflow ran the suite twice, once per
submission path, and the raster took the async leg. `tool-suite-tests.yaml` replaces it
and runs the async path only, so a run now carries a single `All tool test results`
artifact. This narrows that artifact to the fields the raster reads and records the run
metadata beside it; generate_raster_data.py builds the raster from there.

The scope a run was dispatched with is recorded in run.json. A `subset` run covers only
the packages with a known failing test, so its column is mostly empty next to a `full`
run; that is a property of the data rather than a defect, and the raster shows it.

Usage: anvil_ingest_iuc_run.py <ci_run_id> [<ci_run_id> ...]
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

REPO = os.environ.get("IUC_REPO", "guerler/tools-iuc")
TOOL_TESTS_DIR = "data/tool-tests"
RESULTS_ARTIFACT = "All tool test results"
FAILURES_ARTIFACT = "Failing tool tests"
SCOPE_RE = re.compile(r"^# Failing tool tests \((\w+) scope\)", re.M)


def gh_json(path: str):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def artifact(run_id: str, name: str, into: str) -> str | None:
    """Download one artifact and return the directory it unpacked into."""
    listing = gh_json(f"repos/{REPO}/actions/runs/{run_id}/artifacts")["artifacts"]
    match = next((a for a in listing if a["name"] == name and not a["expired"]), None)
    if not match:
        return None
    zipped = os.path.join(into, f"{name}.zip")
    # the blob store flakes, so give it a few tries before believing it is absent
    for _ in range(4):
        with open(zipped, "wb") as handle:
            subprocess.run(["gh", "api", f"repos/{REPO}/actions/artifacts/{match['id']}/zip"],
                           stdout=handle, stderr=subprocess.DEVNULL)
        if os.path.getsize(zipped):
            break
    else:
        raise SystemExit(f"could not download {name!r} for run {run_id}")
    target = os.path.join(into, name.replace(" ", "_"))
    with zipfile.ZipFile(zipped) as z:
        z.extractall(target)
    return target


def narrow(tests: list) -> list:
    """Keep only what the raster reads. The artifact carries full job records and
    command lines, which are large and unused here."""
    out = []
    for entry in tests:
        data = entry.get("data") or {}
        tool_id = data.get("tool_id") or ""
        # toolshed ids are .../repos/<owner>/<repo>/<tool_id>/<version>
        short = tool_id.split("/")[-2] if "/" in tool_id else tool_id
        job = data.get("job") or {}
        out.append({
            "id": f"{short}-{data.get('test_index')}",
            "data": {
                "tool_id": short,
                "tool_version": data.get("tool_version"),
                "status": data.get("status"),
                "test_index": data.get("test_index"),
                "time_seconds": data.get("time_seconds"),
                "execution_problem": data.get("execution_problem"),
                "output_problems": data.get("output_problems"),
                "job": {"create_time": job.get("create_time"),
                        "update_time": job.get("update_time")},
            },
        })
    return out


def ingest(run_id: str) -> bool:
    run = gh_json(f"repos/{REPO}/actions/runs/{run_id}")
    if run["conclusion"] not in ("success", "failure"):
        print(f"  {run_id}: {run['conclusion']}, skipping")
        return False
    with tempfile.TemporaryDirectory() as tmp:
        results_dir = artifact(run_id, RESULTS_ARTIFACT, tmp)
        if not results_dir:
            print(f"  {run_id}: no {RESULTS_ARTIFACT!r} artifact, skipping")
            return False
        failures_dir = artifact(run_id, FAILURES_ARTIFACT, tmp)
        scope = "unknown"
        if failures_dir:
            report = os.path.join(failures_dir, "failures.md")
            if os.path.exists(report):
                found = SCOPE_RE.search(open(report).read())
                scope = found.group(1) if found else "unknown"
        with open(os.path.join(results_dir, "tool_test_output.json")) as handle:
            tests = json.load(handle).get("tests", [])

    started = run["created_at"]
    stamp = re.sub(r"[-:TZ]", "", started)[2:14]
    run_dir = os.path.join(TOOL_TESTS_DIR, f"iuc-async-{stamp[:6]}-{stamp[6:]}")
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "results.json"), "w") as handle:
        json.dump({"tests": narrow(tests), "version": 0.1}, handle, indent=1)
    with open(os.path.join(run_dir, "run.json"), "w") as handle:
        json.dump({
            "report_url": run["html_url"],
            "source_repo": REPO,
            "ci_run_id": int(run_id),
            "created_at": started,
            "scope": scope,
        }, handle, indent=1)
    print(f"  {run_id}: {len(tests)} tests, {scope} scope -> {run_dir}")
    return True


def main(argv: list[str]) -> int:
    run_ids = [a for a in argv if not a.startswith("--")]
    if not run_ids:
        raise SystemExit(__doc__)
    written = sum(ingest(r) for r in run_ids)
    print(f"{written} run(s) ingested; now run generate_raster_data.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
