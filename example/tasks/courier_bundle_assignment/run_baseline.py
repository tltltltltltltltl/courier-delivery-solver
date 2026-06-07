import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from llm4ad.base import SecureEvaluator
from llm4ad.task.optimization.courier_bundle_assignment import (
    CourierBundleAssignmentEvaluation,
    template_program,
)


def main():
    task = CourierBundleAssignmentEvaluation(timeout_seconds=10)
    evaluator = SecureEvaluator(task, debug_mode=False)
    score = evaluator.evaluate_program(template_program)
    objective = None if score is None else -score

    print(f"case: {task.case_data}")
    print(f"fitness: {score}")
    print(f"objective: {objective}")


if __name__ == "__main__":
    main()
