"""Merge the shard folders of one experiment (run_experiment.sh) into its top folder.

  python3 scripts/merge_runs.py MGDebugger/src/output_data/experiments/<run>

Writes, next to the shard*/ folders: params.json (shard 0's, SHARD set to the count), and the
concatenation of every shard's llm_calls.jsonl, hypothesis_nodes.jsonl and per-problem results
file, so summarize.py and compare_runs.py read a merged run like a single one.
"""
import glob
import json
import os
import sys


def merge(run: str) -> None:
    shards = sorted(d for d in glob.glob(os.path.join(run, "shard*")) if os.path.isdir(d))
    if not shards:
        sys.exit(f"no shard folders in {run}")
    params = json.load(open(os.path.join(shards[0], "params.json")))
    params["SHARD"] = len(shards)
    params["output_folder"] = run
    with open(os.path.join(run, "params.json"), "w") as f:
        json.dump(params, f, indent=2)

    for name in ("llm_calls.jsonl", "hypothesis_nodes.jsonl"):
        lines = [l for d in shards if os.path.exists(os.path.join(d, name)) for l in open(os.path.join(d, name))]
        if lines:
            with open(os.path.join(run, name), "w") as f:
                f.writelines(l if l.endswith("\n") else l + "\n" for l in lines)

    results = {}
    for d in shards:
        for path in glob.glob(os.path.join(d, "*_debugging_seeds_from_*.jsonl")):
            results.setdefault(os.path.basename(path), []).extend(open(path))
    for name, lines in results.items():
        with open(os.path.join(run, name), "w") as f:
            f.writelines(l if l.endswith("\n") else l + "\n" for l in lines)
    print(f"merged {len(shards)} shards into {run}")


if __name__ == "__main__":
    merge(sys.argv[1])
