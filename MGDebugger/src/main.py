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


def setup_logging_and_output(input_seeds: str):
    """Setup logging and create output directory"""
    seed_stamp = input_seeds.split("input_data/")[-1].replace("/seed.jsonl", "")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_folder = f"./output_data/{seed_stamp}/{timestamp}"
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
            "HYPOTHESIS_K": config.HYPOTHESIS_K,
            "SANDBOX_TIMEOUT": config.SANDBOX_TIMEOUT,
        }
        f.write(json.dumps(info, indent=2))

    return output_folder


def main():
    """Main function to run the debugging pipeline"""
    # [hdmg] command-line options instead of editing the file
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="input_data/humaneval/seed/deepseekcoder/seed.jsonl")
    ap.add_argument("--max-examples", type=int, default=None)
    args = ap.parse_args()
    input_seeds = args.seeds

    # Setup logging and output directory
    output_folder = setup_logging_and_output(input_seeds)
    config.CALL_LOG = f"{output_folder}/llm_calls.jsonl"
    config.HYPOTHESIS_LOG = f"{output_folder}/hypothesis_nodes.jsonl"  # [hdmg] variant C only

    logger.info("Starting MGDebugger pipeline")
    logger.info(f"Input seeds: {input_seeds}")
    logger.info(f"Output folder: {output_folder}")
    
    # Run the debugging pipeline
    debug_dataset(input_seeds, max_examples=args.max_examples, output_folder=output_folder)
    
    logger.info("MGDebugger pipeline completed")


if __name__ == "__main__":
    main()
