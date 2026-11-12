from collections import Counter
from loguru import logger
import json
import traceback
from tqdm import tqdm
from utils import evaluate_simple, evaluate_given_tests, parse_transcoder_problem_content
from testcase_utils import get_parameter_names, parse_tests
from mg_debugger import mg_debug
from config import MAX_OUTER_RETRY, CONTINUOUS_RETRY
import config


def debug_dataset(input_seeds: str, max_examples: int = None, output_folder: str = None):
    """Main function to debug problems"""
    fixed_problems = 0
    total_unsolved = 0

    with open(input_seeds, "r") as f:
        seeds = f.readlines()

    unsolved_seeds = []
    # filter those problems that are not solved
    for i in range(len(seeds)):
        problem = json.loads(seeds[i])
        if not problem["is_solved"]:
            unsolved_seeds.append(problem)

    # parse transcoder problems
    if "transcoder" in input_seeds.lower():
        logger.info(f"Parsing the problem content for transcoder problems")
        unsolved_seeds = [parse_transcoder_problem_content(problem) for problem in tqdm(unsolved_seeds)]

    total_unsolved = len(unsolved_seeds)
    logger.info(f"Debugging {total_unsolved} unsolved problems")
    if max_examples is not None:
        unsolved_seeds = unsolved_seeds[:max_examples]
        logger.info(f"Filtering to {max_examples} examples")

    from llm_client import budget_left, BudgetExceeded
    for problem in tqdm(unsolved_seeds, ncols=100):
        if not budget_left():  # [hdmg] stop cleanly; unstarted problems stay unattempted
            logger.warning(f"Budget reached (${config.SPENT_USD:.2f}); stopping before {problem['task_id']}")
            break
        
        model_to_be_fixed = input_seeds.split("/")[-2]
        from config import MODEL
        model_name = MODEL.split("/")[-1]
        with open(f"{output_folder}/{model_name}_debugging_seeds_from_{model_to_be_fixed}.jsonl", "w+") as f:
            for seed in unsolved_seeds:
                f.write(json.dumps(seed) + "\n")
                
        logger.info(f"Processing unsolved problem: {problem['task_id']}")
        logger.info(f"Problem: {problem}")
        logger.info(f"Problem Raw Prompt: \n{problem['prompt']}")

        try:
            buggy_code = problem["solution"]
            entry_point = problem["entry_point"]
            try:
                parameter_names = get_parameter_names(problem["prompt"], entry_point)
            except:
                parameter_names = get_parameter_names(problem["solution"], entry_point)
            logger.info(f"Extracted parameter names: {parameter_names}")

            # in order to save time, we extract the first 3 given tests for transcoder
            if "transcoder" in problem["task_id"].lower():
                logger.info(f"Extracted {len(problem['given_tests'])} given tests, only using the first 3 samples")
                problem["given_tests"] = problem["given_tests"][:3]

            gold_tests_raw = "\n".join(problem["given_tests"]).replace(entry_point, "candidate")
            gold_tests = parse_tests(gold_tests_raw, parameter_names, entry_point)["test_cases"]
            logger.info(f"Extracted gold test cases: {gold_tests}")

            problem['fixed_codes'] = []  # Initialize list to store fixed codes for each retry
            problem['mg_debug_retries'] = 0  # Initialize retry counter
            # [hdmg] per-attempt record: did it pass the given (public) tests, the hidden tests,
            # and how many tokens did the attempt use
            problem['attempts'] = []
            config.CURRENT_TASK_ID = problem['task_id']
            first_public = first_hidden = None

            for outer_retry in range(config.MAX_OUTER_RETRY):
                config.CURRENT_ATTEMPT = outer_retry + 1
                tok0 = config.TOTAL_PROMPT_TOKENS + config.TOTAL_COMPLETION_TOKENS
                fixed_code = mg_debug(buggy_code, gold_tests)
                problem['fixed_codes'].append(fixed_code)
                problem['mg_debug_retries'] += 1

                hidden_pass = evaluate_simple(fixed_code, entry_point, problem["test"])
                public_pass = evaluate_given_tests(fixed_code, "\n".join(problem["given_tests"]))
                problem['attempts'].append({
                    "attempt": outer_retry + 1,
                    "public_pass": public_pass,
                    "hidden_pass": hidden_pass,
                    "tokens": config.TOTAL_PROMPT_TOKENS + config.TOTAL_COMPLETION_TOKENS - tok0,
                })
                if public_pass and first_public is None:
                    first_public = outer_retry + 1
                if hidden_pass and first_hidden is None:
                    first_hidden = outer_retry + 1

                if config.STOP_ON == "hidden":
                    stop = first_hidden is not None
                elif config.STOP_ON == "public":
                    stop = first_public is not None
                else:  # "both"
                    stop = first_hidden is not None and first_public is not None
                if stop:
                    break
                if CONTINUOUS_RETRY:
                    buggy_code = fixed_code  # upstream option, off by default

            # [hdmg] the two ways of scoring the same run
            # paper / oracle selection: any attempt passed the hidden tests
            problem['fixed_hidden_selection'] = first_hidden is not None
            # deployable: take the first attempt that passed the public tests, then grade it on hidden tests
            problem['fixed_public_selection'] = (
                first_public is not None and problem['attempts'][first_public - 1]['hidden_pass'])
            problem['first_public_attempt'] = first_public
            problem['first_hidden_attempt'] = first_hidden
            all_passed = problem['fixed_hidden_selection'] if config.STOP_ON != "public" else problem['fixed_public_selection']
            if all_passed:
                fixed_problems += 1
                problem['debugged'] = True
                logger.info(f"Successfully fixed problem: {problem['task_id']}")
            else:
                logger.info(f"Failed to fix problem: {problem['task_id']}")
                problem['debugged'] = False

        except BudgetExceeded:
            # [hdmg] ran out mid-problem: not a failure of the method, exclude it from scoring
            logger.warning(f"Budget reached during {problem['task_id']}; excluded from results")
            problem['budget_stopped'] = True
            problem.pop('attempts', None)
            break
        except Exception as e:
            logger.error(f"Error occurred while processing problem: {problem['task_id']}")
            logger.error(traceback.format_exc())
            problem['fixed_codes'] = []
            problem['debugged'] = False
            problem['mg_debug_retries'] = 0

    # Log final statistics
    _log_final_statistics(seeds, unsolved_seeds, total_unsolved, fixed_problems, input_seeds, output_folder)

    return unsolved_seeds


def _log_final_statistics(seeds, unsolved_seeds, total_unsolved, fixed_problems, input_seeds, output_folder):
    """Log and save final statistics"""
    # Add statistics to the log
    logger.info("=== Statistics ===")
    logger.info(f"Total prompt tokens: {config.TOTAL_PROMPT_TOKENS}")
    logger.info(f"Total completion tokens: {config.TOTAL_COMPLETION_TOKENS}")
    logger.info(f"Total mg_debug calls: {config.TOTAL_MG_DEBUG_CALLS}")
    logger.info(f"Total debug_function calls: {config.TOTAL_DEBUG_FUNCTION_CALLS}")
    logger.info(f"Total generate_test_cases calls: {config.TOTAL_GENERATE_TEST_CASES_CALLS}")
    logger.info(f"Total convert_hierarchical calls: {config.TOTAL_CONVERT_HIERARCHICAL_CALLS}")

    # Compute and log average statistics
    avg_prompt_tokens = config.TOTAL_PROMPT_TOKENS / config.TOTAL_MG_DEBUG_CALLS if config.TOTAL_MG_DEBUG_CALLS > 0 else 0
    avg_completion_tokens = config.TOTAL_COMPLETION_TOKENS / config.TOTAL_MG_DEBUG_CALLS if config.TOTAL_MG_DEBUG_CALLS > 0 else 0
    avg_debug_function_calls = config.TOTAL_DEBUG_FUNCTION_CALLS / config.TOTAL_MG_DEBUG_CALLS if config.TOTAL_MG_DEBUG_CALLS > 0 else 0
    avg_generate_test_cases_calls = config.TOTAL_GENERATE_TEST_CASES_CALLS / config.TOTAL_MG_DEBUG_CALLS if config.TOTAL_MG_DEBUG_CALLS > 0 else 0

    logger.info(f"Average prompt tokens per mg_debug call: {avg_prompt_tokens:.2f}")
    logger.info(f"Average completion tokens per mg_debug call: {avg_completion_tokens:.2f}")
    logger.info(f"Average debug_function calls per mg_debug call: {avg_debug_function_calls:.2f}")
    logger.info(f"Average generate_test_cases calls per mg_debug call: {avg_generate_test_cases_calls:.2f}")

    # distribution of debug retries that solved the problem
    debug_retries = [problem['mg_debug_retries'] for problem in unsolved_seeds if problem.get('debugged')]  # [hdmg] .get: budget stop leaves some unstarted
    debug_retries_counter = Counter(debug_retries)

    logger.info(f"=== Final Results ===")
    logger.info(f"Total unsolved problems in seeds: {total_unsolved}")
    logger.info(f"Problems fixed by our method: {fixed_problems}")
    logger.info(f"Success rate: {fixed_problems / total_unsolved * 100:.2f}%")
    logger.info(f"Debug retries distribution for solved problems: {debug_retries_counter}")

    logger.info(f"Total solved problems before: {len(seeds) - total_unsolved}")
    logger.info(f"Total solved problems after: {len(seeds) - total_unsolved + fixed_problems}")
    logger.info(f"Previous accuracy: {(len(seeds) - total_unsolved) / len(seeds) * 100:.2f}%")
    logger.info(f"Final accuracy: {(len(seeds) - total_unsolved + fixed_problems) / len(seeds) * 100:.2f}%")

    # save the final results to a file
    model_to_be_fixed = input_seeds.split("/")[-2]
    from config import MODEL
    model_name = MODEL.split("/")[-1]
    with open(f"{output_folder}/{model_name}_debugging_seeds_from_{model_to_be_fixed}.jsonl", "w+") as f:
        for seed in unsolved_seeds:
            f.write(json.dumps(seed) + "\n")

    # Save statistics
    with open(f"{output_folder}/statistics.json", "w") as f:
        stats = {
            "total_prompt_tokens": config.TOTAL_PROMPT_TOKENS,
            "total_completion_tokens": config.TOTAL_COMPLETION_TOKENS,
            "total_mg_debug_calls": config.TOTAL_MG_DEBUG_CALLS,
            "total_debug_function_calls": config.TOTAL_DEBUG_FUNCTION_CALLS,
            "total_generate_test_cases_calls": config.TOTAL_GENERATE_TEST_CASES_CALLS,
            "total_convert_hierarchical_calls": config.TOTAL_CONVERT_HIERARCHICAL_CALLS,
            "spent_usd": config.SPENT_USD,
            "avg_prompt_tokens_per_mg_debug": avg_prompt_tokens,
            "avg_completion_tokens_per_mg_debug": avg_completion_tokens,
            "avg_debug_function_calls_per_mg_debug": avg_debug_function_calls,
            "avg_generate_test_cases_calls_per_mg_debug": avg_generate_test_cases_calls
        }
        json.dump(stats, f, indent=2)
        
        scores = {
            "total_unsolved": total_unsolved,
            "fixed_problems": fixed_problems,
            "success_rate": fixed_problems / total_unsolved * 100,
            "debug_retries_distribution": debug_retries_counter,
            "total_solved_problems_before": len(seeds) - total_unsolved,
            "total_solved_problems_after": len(seeds) - total_unsolved + fixed_problems,
            "previous_accuracy": (len(seeds) - total_unsolved) / len(seeds) * 100,
            "final_accuracy": (len(seeds) - total_unsolved + fixed_problems) / len(seeds) * 100
        }
        json.dump(scores, f, indent=2) 