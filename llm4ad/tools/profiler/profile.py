from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime
from threading import Lock
from typing import Literal, Optional

from ...base import Function


class ProfilerBase:
    def __init__(
        self,
        log_dir: Optional[str] = None,
        *,
        initial_num_samples=0,
        log_style: Literal["simple", "complex"] = "complex",
        create_random_path=True,
        num_objs=1,
        **kwargs,
    ):
        assert log_style in ["simple", "complex"]

        self._num_objs = num_objs
        self._num_samples = initial_num_samples
        self._process_start_time = datetime.now()
        self._result_folder = self._process_start_time.strftime("%Y%m%d_%H%M%S")
        self._log_dir = log_dir
        self._log_style = log_style
        self._cur_best_function = None if num_objs < 2 else [None for _ in range(num_objs)]
        self._cur_best_program_sample_order = None if num_objs < 2 else [None for _ in range(num_objs)]
        self._cur_best_program_score = float("-inf") if num_objs < 2 else [float("-inf") for _ in range(num_objs)]
        self._evaluate_success_program_num = 0
        self._evaluate_failed_program_num = 0
        self._tot_sample_time = 0
        self._tot_evaluate_time = 0
        self._parameters = None
        self._logger_txt = logging.getLogger("courier_delivery_solver")
        self._register_function_lock = Lock()

        if self._log_dir and create_random_path:
            self._log_dir = os.path.join(self._log_dir, self._result_folder)

    def record_parameters(self, llm, prob, method):
        self._parameters = [llm, prob, method]
        if self._log_dir:
            self._create_log_path()

    def register_function(self, function: Function, program: str = "", *, resume_mode=False):
        try:
            self._register_function_lock.acquire()
            self._num_samples += 1
            self._record_and_print_verbose(function, program=program, resume_mode=resume_mode)
            if not resume_mode:
                self._write_json(function, program)
        finally:
            self._register_function_lock.release()

    def finish(self):
        pass

    def get_logger(self):
        return self._logger_txt

    def resume(self, *args, **kwargs):
        pass

    def _write_json(
        self,
        function: Function,
        program: str = "",
        *,
        record_type: Literal["history", "best"] = "history",
        record_sep=200,
    ):
        if not self._log_dir:
            return

        content = {
            "sample_order": self._num_samples,
            "function": str(function),
            "score": function.score,
            "operator": function.operator,
            "program": program,
        }

        if record_type == "history":
            lower_bound = ((self._num_samples - 1) // record_sep) * record_sep
            upper_bound = lower_bound + record_sep
            filename = f"samples_{lower_bound + 1}~{upper_bound}.json"
        else:
            filename = "samples_best.json"

        path = os.path.join(self._samples_json_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []

        data.append(content)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)

    def _record_and_print_verbose(self, function, program="", *, resume_mode=False):
        score = function.score
        if self._num_objs < 2:
            if score is not None and score > self._cur_best_program_score:
                self._cur_best_function = function
                self._cur_best_program_score = score
                self._cur_best_program_sample_order = self._num_samples
                if not resume_mode:
                    self._write_json(function, program=program, record_type="best")
        else:
            if score is not None:
                for index in range(self._num_objs):
                    if score[index] > self._cur_best_program_score[index]:
                        self._cur_best_function[index] = function
                        self._cur_best_program_score[index] = score[index]
                        self._cur_best_program_sample_order[index] = self._num_samples
                        if not resume_mode:
                            self._write_json(function, program=program, record_type="best")

        if not resume_mode:
            if self._log_style == "complex":
                print("================= Evaluated Function =================")
                print(str(function).strip("\n"))
                print("------------------------------------------------------")
                print(f"Operator     : {function.operator}")
                print(f"Score        : {score}")
                print(f"Sample time  : {function.sample_time}")
                print(f"Evaluate time: {function.evaluate_time}")
                print(f"Sample orders: {self._num_samples}")
                print("------------------------------------------------------")
                print(f"Current best score: {self._cur_best_program_score}")
                print("======================================================\n")
            else:
                print(
                    f"Sample{self._num_samples}: Score={score} "
                    f"Cur_Best_Score={self._cur_best_program_score}"
                )

        if score is not None:
            self._evaluate_success_program_num += 1
        else:
            self._evaluate_failed_program_num += 1
        if function.sample_time is not None:
            self._tot_sample_time += function.sample_time
        if function.evaluate_time:
            self._tot_evaluate_time += function.evaluate_time

    def _create_log_path(self):
        self._samples_json_dir = os.path.join(self._log_dir, "samples")
        os.makedirs(self._samples_json_dir, exist_ok=True)

        file_name = os.path.join(self._log_dir, "run_log.txt")
        file_mode = "a" if os.path.isfile(file_name) else "w"
        self._logger_txt.setLevel(level=logging.INFO)
        formatter = logging.Formatter("[%(asctime)s] %(filename)s(%(lineno)d) : %(message)s", "%Y-%m-%d %H:%M:%S")

        for handler in self._logger_txt.handlers[:]:
            self._logger_txt.removeHandler(handler)

        fileout = logging.FileHandler(file_name, mode=file_mode)
        fileout.setLevel(logging.INFO)
        fileout.setFormatter(formatter)
        self._logger_txt.addHandler(fileout)
        self._logger_txt.addHandler(logging.StreamHandler(sys.stdout))

        if not self._parameters:
            return
        llm, prob, method = self._parameters
        self._logger_txt.info("LLM: %s", llm.__class__.__name__)
        self._logger_txt.info("Problem: %s", prob.__class__.__name__)
        self._logger_txt.info("Method: %s", method.__class__.__name__)

    @classmethod
    def load_logfile(cls, logdir, valid_only=False):
        file_dir = os.path.join(logdir, "samples")
        sample_files = [
            file_name
            for file_name in os.listdir(file_dir)
            if file_name.startswith("samples_") and file_name != "samples_best.json"
        ]

        def extract_number(filename):
            match = re.search(r"samples_(\\d+)~", filename)
            return int(match.group(1)) if match else 0

        all_func = []
        all_score = []
        for file_name in sorted(sample_files, key=extract_number):
            path = os.path.join(file_dir, file_name)
            with open(path, "r", encoding="utf-8") as file:
                samples = json.load(file)
            for sample in samples:
                score = sample["score"] if sample["score"] is not None else float("-inf")
                if valid_only and score == float("-inf"):
                    continue
                all_func.append(sample["function"])
                all_score.append(score)

        return all_func, all_score
