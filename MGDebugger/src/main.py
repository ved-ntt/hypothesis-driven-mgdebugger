#!/usr/bin/env python3
"""
MGDebugger - A hierarchical debugging tool for Python code
Main entry point for the debugging pipeline
"""

import argparse
import time
import json
import os
import sys
from loguru import logger

from debug_pipeline import debug_dataset
import config
from config import (
    MAX_DEBUG_RETRIES, MAX_PARSE_RETRIES, RETRY_DELAY,
    REPEAT_CONVERT_HIERARCHICAL_NUM, REPEAT_TEST_CASE_GENERATION_NUM,
    MODEL, MAX_OUTER_RETRY, CONTINUOUS_RETRY, TEMPERATURE, 
    MAX_VLLM_RETRIES, MINP
)


def setup_logging_and_output(input_seeds: str, output_folder: str = None):
    """Setup logging and create output directory"""
    if "input_data/" in input_seeds:
        seed_stamp = input_seeds.split("input_data/")[-1].replace("/seed.jsonl", "")
    else:  # [hdmg] cleaned seeds elsewhere (data/clean/<name>.jsonl): name the folder after the file
        seed_stamp = os.path.splitext(os.path.basename(input_seeds))[0]
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if output_folder is None:  # [hdmg] --out names the folder; --shard keeps parallel shards apart
        suffix = f"_shard{config.SHARD[0]}of{config.SHARD[1]}" if config.SHARD else ""
        output_folder = f"./output_data/{seed_stamp}/{timestamp}{suffix}"
    os.makedirs(output_folder, exist_ok=True)

    # Configure logger
    logger.remove()
    logger.add(sys.stderr, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")
    logger.add(f"{output_folder}/all_info.log", format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>")

    # Save all important params in a file
    with open(f"{output_folder}/params.json", "w+") as f:
        info = {
            "input_seeds": input_seeds,
            "output_folder": output_folder,
            "MAX_DEBUG_RETRIES": MAX_DEBUG_RETRIES,
            "MAX_PARSE_RETRIES": MAX_PARSE_RETRIES,
            "RETRY_DELAY": RETRY_DELAY,
            "REPEAT_CONVERT_HIERARCHICAL_NUM": REPEAT_CONVERT_HIERARCHICAL_NUM,
            "REPEAT_TEST_CASE_GENERATION_NUM": REPEAT_TEST_CASE_GENERATION_NUM,
            "MODEL": MODEL,
            "MAX_OUTER_RETRY": MAX_OUTER_RETRY,
            "CONTINUOUS_RETRY": CONTINUOUS_RETRY,
            "TEMPERATURE": TEMPERATURE,
            "MAX_VLLM_RETRIES": MAX_VLLM_RETRIES,
            "MINP": MINP,
            # [hdmg] settings that change results
            "USE_MIN_P": config.USE_MIN_P,
            "STOP_ON": config.STOP_ON,
            "MAX_OUTER_RETRY_EFFECTIVE": config.MAX_OUTER_RETRY,
            "TEMPERATURE_EFFECTIVE": config.TEMPERATURE,
            "LLM_BASE_URL": config.LLM_BASE_URL,
            "VARIANT": config.VARIANT,
            "VARIANT_SCHEME": config.VARIANT_SCHEME,
            "HYPOTHESIS_K": config.HYPOTHESIS_K,
            "SANDBOX_TIMEOUT": config.SANDBOX_TIMEOUT,
            "HARNESS": config.HARNESS,
            "EXACT_TESTS": config.EXACT_TESTS,
            "ONLY_DETECTABLE": config.ONLY_DETECTABLE,
            "SHARD": list(config.SHARD) if config.SHARD else None,
        }
        f.write(json.dumps(info, indent=2))

    return output_folder


def main():
    """Main function to run the debugging pipeline"""
    # [hdmg] command-line options instead of editing the file
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="input_data/humaneval/seed/deepseekcoder/seed.jsonl")
    ap.add_argument("--max-examples", type=int, default=None)
    ap.add_argument("--shard", default=None, help="i/N: run every N-th problem starting at i (0-based)")
    ap.add_argument("--out", default=None, help="output folder (default output_data/<seeds>/<timestamp>)")
    args = ap.parse_args()
    input_seeds = args.seeds
    if args.shard:
        index, count = (int(x) for x in args.shard.split("/"))
        if not 0 <= index < count:
            ap.error("--shard i/N needs 0 <= i < N")
        config.SHARD = (index, count)

    # Setup logging and output directory
    output_folder = setup_logging_and_output(input_seeds, args.out)
    config.CALL_LOG = f"{output_folder}/llm_calls.jsonl"
    config.HYPOTHESIS_LOG = f"{output_folder}/hypothesis_nodes.jsonl"  # [hdmg] variants B and C

    logger.info("Starting MGDebugger pipeline")
    logger.info(f"Input seeds: {input_seeds}")
    logger.info(f"Output folder: {output_folder}")
    
    # Run the debugging pipeline
    debug_dataset(input_seeds, max_examples=args.max_examples, output_folder=output_folder)
    
    logger.info("MGDebugger pipeline completed")


if __name__ == "__main__":
    main()
    # [hdmg] results are written; don't wait for test threads that timed out and are still running
    sys.stdout.flush(); sys.stderr.flush()
    os._exit(0)
