from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from llm4ad.base import Evaluation
from llm4ad.task.optimization.courier_bundle_assignment.template import (
    task_description,
    template_program,
)

__all__ = ["CourierBundleAssignmentEvaluation"]


@dataclass(frozen=True)
class Candidate:
    task_id_list: str
    courier_id: str
    total_score: float
    willingness: float
    tasks: tuple[str, ...]


@dataclass(frozen=True)
class CaseData:
    input_text: str
    candidates_by_pair: dict[tuple[str, str], Candidate]
    tasks: tuple[str, ...]

    def __repr__(self) -> str:
        lines = self.input_text.count("\n") + (1 if self.input_text else 0)
        return (
            f"CaseData(lines={lines}, tasks={len(self.tasks)}, "
            f"candidates={len(self.candidates_by_pair)})"
        )


class CourierBundleAssignmentEvaluation(Evaluation):
    """Evaluator for the courier bundle assignment expected-cost problem."""

    def __init__(
        self,
        case_file: str = "official_large_seed301.txt",
        timeout_seconds: int = 10,
        penalty_per_missed_task: float = 100.0,
        failure_log_path: str | None = None,
        **kwargs,
    ):
        super().__init__(
            template_program=template_program,
            task_description=task_description,
            use_numba_accelerate=False,
            timeout_seconds=int(timeout_seconds),
        )
        case_path = Path(case_file)
        if not case_path.is_absolute():
            case_path = Path(__file__).resolve().parent / case_path
        self.case_file = str(case_path)
        self.penalty_per_missed_task = float(penalty_per_missed_task)
        self.failure_log_path = failure_log_path
        self._validation_error = ""
        input_text = case_path.read_text()
        candidates_by_pair, tasks = self._parse_case(input_text)
        self.case_data = CaseData(input_text, candidates_by_pair, tasks)

    @property
    def input_text(self) -> str:
        return self.case_data.input_text

    @property
    def candidates_by_pair(self) -> dict[tuple[str, str], Candidate]:
        return self.case_data.candidates_by_pair

    @property
    def tasks(self) -> tuple[str, ...]:
        return self.case_data.tasks

    def evaluate_program(self, program_str: str, callable_func: callable) -> Any | None:
        try:
            solution = callable_func(self.input_text)
            objective = self.evaluate_solution(solution)
        except Exception as exc:
            return self._fail(f"{exc.__class__.__name__}: {exc}", program_str)
        if objective is None:
            self._fail(self._validation_error or "invalid solution", program_str)
            return None
        return -objective

    def _parse_case(self, input_text: str) -> tuple[dict[tuple[str, str], Candidate], tuple[str, ...]]:
        lines = input_text.strip().splitlines()
        start = 1 if lines and lines[0].startswith("task_id_list") else 0
        best_by_pair: dict[tuple[str, str], Candidate] = {}
        task_seen: dict[str, None] = {}

        for raw_line in lines[start:]:
            parts = raw_line.strip().split("\t")
            if len(parts) < 4:
                continue
            task_id_list = parts[0].strip()
            courier_id = parts[1].strip()
            try:
                total_score = float(parts[2])
                willingness = self._clamp_probability(float(parts[3]))
            except ValueError:
                continue
            tasks = tuple(task.strip() for task in task_id_list.split(",") if task.strip())
            if not tasks or not courier_id:
                continue
            for task_id in tasks:
                task_seen[task_id] = None
            candidate = Candidate(task_id_list, courier_id, total_score, willingness, tasks)
            key = (task_id_list, courier_id)
            previous = best_by_pair.get(key)
            if previous is None or candidate.total_score < previous.total_score:
                best_by_pair[key] = candidate

        return best_by_pair, tuple(sorted(task_seen))

    def evaluate_solution(self, solution: Iterable[tuple[str, Iterable[str]]]) -> float | None:
        groups = self._validate_solution(solution)
        if groups is None:
            return None

        expected_score = 0.0
        miss_by_task = {task_id: 1.0 for task_id in self.tasks}

        for candidates in groups.values():
            expected_score += self._group_expected_score(candidates)
            remaining = self._group_miss_probability(candidates)
            for task_id in candidates[0].tasks:
                miss_by_task[task_id] *= remaining

        penalty = self.penalty_per_missed_task * sum(miss_by_task.values())
        return expected_score + penalty

    def _validate_solution(
        self, solution: Iterable[tuple[str, Iterable[str]]]
    ) -> dict[str, list[Candidate]] | None:
        self._validation_error = ""
        if not isinstance(solution, Iterable):
            self._validation_error = "solution is not iterable"
            return None

        groups: dict[str, list[Candidate]] = {}
        used_couriers: dict[str, str] = {}
        task_owner: dict[str, str] = {}

        for item in solution:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                self._validation_error = "each solution item must be a (task_id_list, couriers) pair"
                return None
            task_id_list = str(item[0]).strip()
            if not task_id_list or task_id_list in groups:
                self._validation_error = f"empty or duplicate task_id_list: {task_id_list!r}"
                return None

            try:
                couriers = list(item[1])
            except TypeError:
                self._validation_error = f"couriers for {task_id_list!r} is not iterable"
                return None
            if not couriers:
                self._validation_error = f"empty courier list for task_id_list {task_id_list!r}"
                return None

            group_candidates: list[Candidate] = []
            group_tasks: tuple[str, ...] | None = None
            for raw_courier_id in couriers:
                courier_id = str(raw_courier_id).strip()
                if courier_id in used_couriers:
                    self._validation_error = (
                        f"duplicate courier {courier_id!r}; already used by "
                        f"{used_couriers[courier_id]!r}"
                    )
                    return None
                candidate = self.candidates_by_pair.get((task_id_list, courier_id))
                if candidate is None:
                    self._validation_error = (
                        f"unknown pair: task_id_list={task_id_list!r}, "
                        f"courier_id={courier_id!r}"
                    )
                    return None
                if group_tasks is None:
                    group_tasks = candidate.tasks
                elif group_tasks != candidate.tasks:
                    self._validation_error = (
                        f"inconsistent task list for {task_id_list!r} with courier "
                        f"{courier_id!r}"
                    )
                    return None
                used_couriers[courier_id] = task_id_list
                group_candidates.append(candidate)

            if group_tasks is None:
                self._validation_error = f"no valid candidates for {task_id_list!r}"
                return None
            for task_id in group_tasks:
                owner = task_owner.get(task_id)
                if owner is not None and owner != task_id_list:
                    self._validation_error = (
                        f"task overlap: task {task_id!r} appears in both "
                        f"{owner!r} and {task_id_list!r}"
                    )
                    return None
                task_owner[task_id] = task_id_list
            groups[task_id_list] = group_candidates

        return groups

    def _fail(self, reason: str, program_str: str | None = None) -> None:
        print(f"CourierBundleAssignmentEvaluation error: {reason}", flush=True)
        if not self.failure_log_path:
            return None

        path = Path(self.failure_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "time": time.time(),
            "reason": reason,
        }
        if program_str is not None:
            record["program_head"] = program_str[:1000]
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        return None

    def _group_expected_score(self, candidates: list[Candidate]) -> float:
        willingness_sum = sum(candidate.willingness for candidate in candidates)
        if willingness_sum <= 0.0:
            return 0.0
        accepted_probability = 1.0 - self._group_miss_probability(candidates)
        weighted_score = sum(
            candidate.total_score * candidate.willingness / willingness_sum
            for candidate in candidates
        )
        return accepted_probability * weighted_score

    @staticmethod
    def _group_miss_probability(candidates: list[Candidate]) -> float:
        miss_probability = 1.0
        for candidate in candidates:
            miss_probability *= 1.0 - candidate.willingness
        return miss_probability

    @staticmethod
    def _clamp_probability(value: float) -> float:
        if value < 0.0:
            return 0.0
        if value > 1.0:
            return 1.0
        return value
