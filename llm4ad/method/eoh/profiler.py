from __future__ import annotations

import json
import os
from threading import Lock
from typing import Optional

from .population import Population
from ...base import Function
from ...tools.profiler import ProfilerBase


class EoHProfiler(ProfilerBase):
    def __init__(
        self,
        log_dir: Optional[str] = None,
        *,
        initial_num_samples=0,
        log_style="complex",
        create_random_path=True,
        **kwargs,
    ):
        super().__init__(
            log_dir=log_dir,
            initial_num_samples=initial_num_samples,
            log_style=log_style,
            create_random_path=create_random_path,
            **kwargs,
        )
        self._cur_gen = 0
        self._pop_lock = Lock()
        if self._log_dir:
            self._ckpt_dir = os.path.join(self._log_dir, "population")
            os.makedirs(self._ckpt_dir, exist_ok=True)

    def register_population(self, pop: Population):
        if not self._log_dir:
            return
        try:
            self._pop_lock.acquire()
            if self._num_samples == 0 or pop.generation == self._cur_gen:
                return
            records = []
            for function in pop.population:  # type: Function
                records.append(
                    {
                        "algorithm": function.algorithm,
                        "function": str(function),
                        "score": function.score,
                    }
                )
            path = os.path.join(self._ckpt_dir, f"pop_{pop.generation}.json")
            with open(path, "w", encoding="utf-8") as file:
                json.dump(records, file, indent=2, ensure_ascii=False)
            self._cur_gen += 1
        finally:
            if self._pop_lock.locked():
                self._pop_lock.release()
