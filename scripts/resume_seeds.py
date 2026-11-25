"""Seeds for resuming an interrupted run_experiment.sh run: the problems no shard finished.

  python3 scripts/resume_seeds.py MGDebugger/src/output_data/experiments/<run>

Reads the original seeds named in the shards' params.json, drops every problem some shard of the
run already finished (a results row with attempts), and writes the rest to <run>/resume_<time>/clean/
<name>.jsonl (the "clean" folder keeps the results file name the same as the original shards').
Prints that path, or nothing if every problem is done. With --check it writes nothing and prints
only whether problems are left. A problem a shard was in the middle of
when it was killed has no attempts, so it runs again; merge_runs.py drops its partial log lines.
"""
import glob
import json
import os
import sys
import time


def finished(run: str) -> set:
    done = set()
    for path in glob.glob(os.path.join(run, "shard*", "*_debugging_seeds_from_*.jsonl")):
        for line in open(path):
            p = json.loads(line)
            if p.get("attempts"):
                done.add(p["task_id"])
    return done


def main(run: str, check: bool = False) -> None:
    params_files = sorted(glob.glob(os.path.join(run, "shard*", "params.json")))
    if not params_files:
        sys.exit(f"no shard folders in {run}")
    seeds_path = json.load(open(params_files[0]))["input_seeds"]
    done = finished(run)
    rest = [l for l in open(seeds_path) if json.loads(l)["task_id"] not in done]
    todo = [l for l in rest if not json.loads(l)["is_solved"] and json.loads(l).get("usable", json.loads(l).get("detectable")) is not False]
    if not todo or check:
        if todo:
            print(f"{len(todo)} to go")  # --check: print something only if the run is unfinished
        return
    out_dir = os.path.join(run, f"resume_{time.strftime('%H%M%S')}", "clean")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, os.path.basename(seeds_path))
    with open(out, "w") as f:
        f.writelines(rest)
    print(f"{len(done)} problems finished, {len(todo)} to go", file=sys.stderr)
    print(os.path.abspath(out))


if __name__ == "__main__":
    main(sys.argv[1], check="--check" in sys.argv[2:])
