import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[3]))

from llm4ad.method.eoh import EoH
from llm4ad.task.optimization.courier_bundle_assignment import CourierBundleAssignmentEvaluation
from llm4ad.tools.llm.llm_api_https import HttpsApi
from llm4ad.tools.profiler import ProfilerBase


def main():
    llm = HttpsApi(
        host="xxx",
        key="sk-xxx",
        model="xxx",
        timeout=60,
    )

    task = CourierBundleAssignmentEvaluation(timeout_seconds=10)

    method = EoH(
        llm=llm,
        profiler=ProfilerBase(log_dir="logs", log_style="complex"),
        evaluation=task,
        max_sample_nums=20,
        max_generations=5,
        pop_size=2,
        num_samplers=1,
        num_evaluators=1,
    )
    method.run()


if __name__ == "__main__":
    main()
