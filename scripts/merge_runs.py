"""Merge the shard folders of one experiment (run_experiment.sh) into its top folder.

  python3 scripts/merge_runs.py MGDebugger/src/output_data/experiments/<run>

Writes, next to the shard*/ folders: params.json (shard 0's, SHARD set to the count), and the
concatenation of every shard's llm_calls.jsonl, hypothesis_nodes.jsonl and per-problem results
file, so summarize.py and compare_runs.py read a merged run like a single one.

A resumed run (run_experiment.sh with HDMG_RESUME) has more shard folders; a problem that one shard
was in the middle of when it was killed is finished by another. Results keep one row per problem
(the finished one), and log lines of a problem from a shard that did not finish it are dropped, so
its cost is counted once.
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

    # which shard finished each problem
    finished_in = {}
    rows = {}
    order = []
    for d in shards:
        for path in glob.glob(os.path.join(d, "*_debugging_seeds_from_*.jsonl")):
            for line in open(path):
                p = json.loads(line)
                t = p["task_id"]
                if t not in rows:
                    order.append(t)
                if p.get("attempts"):
                    finished_in[t] = d
                    rows[t] = line
                elif t not in rows or not json.loads(rows[t]).get("attempts"):
                    rows[t] = line

    def keep(d, line):
        if not line.strip():
            return False
        t = json.loads(line).get("task_id")
        return t not in finished_in or finished_in[t] == d

    for name in ("llm_calls.jsonl", "hypothesis_nodes.jsonl"):
        lines = [l for d in shards if os.path.exists(os.path.join(d, name))
                 for l in open(os.path.join(d, name)) if keep(d, l)]
        if lines:
            with open(os.path.join(run, name), "w") as f:
                f.writelines(l if l.endswith("\n") else l + "\n" for l in lines)

    names = sorted({os.path.basename(p) for d in shards
                    for p in glob.glob(os.path.join(d, "*_debugging_seeds_from_*.jsonl"))})
    if names:
        for stale in names[1:]:  # one results file per run
            if os.path.exists(os.path.join(run, stale)):
                os.remove(os.path.join(run, stale))
        with open(os.path.join(run, names[0]), "w") as f:
            f.writelines(rows[t] if rows[t].endswith("\n") else rows[t] + "\n" for t in order)
    print(f"merged {len(shards)} shards into {run}")


if __name__ == "__main__":
    merge(sys.argv[1])
