# 外卖配送求解系统说明书

这是一个用于外卖配送任务束分配的求解与评测系统。项目已经收敛为单任务工程：保留评测沙箱、基线求解器、可选的 LLM 搜索入口，以及一份内置大规模评测数据。

README 的目标是说明系统怎么安装、运行、扩展和验证；具体组合优化题面与目标函数细节在 `template.py` 和 `evaluation.py` 中维护。

## 系统能力

- 读取 TSV 格式的外卖配送候选方案数据
- 执行 `solve(input_text)` 求解器并校验输出合法性
- 计算目标函数并返回统一 fitness
- 提供一个可直接运行的基线求解器
- 提供迭代后的最优求解器 `bestsolver.py`
- 支持通过 EoH + LLM 自动搜索新的 `solve()` 实现
- 使用 `uv` 管理环境与锁文件

## 快速开始

进入项目目录：

```bash
cd /Users/tanglei/Desktop/agent2/LLM4AD
```

同步环境：

```bash
uv sync
```

运行基线求解器：

```bash
uv run python example/tasks/courier_bundle_assignment/run_baseline.py
```

当前内置数据上的参考结果：

```text
case: CaseData(lines=33781, tasks=40, candidates=33780)
fitness: -930.2886616069427
objective: 930.2886616069427
```

其中 `objective` 越小越好；系统内部使用 `fitness = -objective`，方便搜索方法按越大越好排序。

评测迭代后的最优求解器：

```bash
uv run python - <<'PY'
from bestsolver import solve
from llm4ad.task.optimization.courier_bundle_assignment import CourierBundleAssignmentEvaluation

task = CourierBundleAssignmentEvaluation(timeout_seconds=10)
solution = solve(task.input_text)
objective = task.evaluate_solution(solution)
print("groups:", len(solution))
print("objective:", objective)
print("fitness:", -objective)
PY
```

当前内置数据上的参考结果：

```text
groups: 37
objective: 649.935226291243
fitness: -649.935226291243
```

## 目录说明

```text
.
├── README.md
├── bestsolver.py
├── pyproject.toml
├── uv.lock
├── example/tasks/courier_bundle_assignment/
│   ├── run_baseline.py
│   └── run_eoh.py
└── llm4ad/
    ├── base/
    ├── method/eoh/
    ├── tools/
    └── task/optimization/courier_bundle_assignment/
        ├── __init__.py
        ├── evaluation.py
        ├── official_large_seed301.txt
        ├── paras.yaml
        └── template.py
```

核心文件：

- `bestsolver.py`：迭代后的最优求解器，可直接导入其中的 `solve()`
- `llm4ad/task/optimization/courier_bundle_assignment/template.py`：求解器模板，包含 `solve(input_text)`
- `llm4ad/task/optimization/courier_bundle_assignment/evaluation.py`：数据读取、输出校验和评分逻辑
- `llm4ad/task/optimization/courier_bundle_assignment/official_large_seed301.txt`：内置评测数据
- `example/tasks/courier_bundle_assignment/run_baseline.py`：直接评测当前模板求解器
- `example/tasks/courier_bundle_assignment/run_eoh.py`：调用 LLM 搜索求解器

## 求解器接口

系统只要求求解器实现一个函数：

```python
def solve(input_text: str) -> list:
    ...
```

返回格式：

```python
[(task_id_list_str, [courier_id, ...]), ...]
```

重要约束：

- `solve()` 内部算法保持零依赖，只使用 Python 标准库
- helper 函数、import 和辅助结构都放进 `solve()` 内部
- 不要依赖全局变量、外部类或模块级缓存
- 输出必须通过 `evaluation.py` 的合法性校验

工程环境安装了 `numpy<2`，供框架侧、分析脚本或后续实验使用；这不改变 `solve()` 的零依赖要求。

推荐把实验生成的更优版本放在独立文件中，例如当前仓库根目录的 `bestsolver.py`。这样可以保留 `template.py` 作为搜索模板，同时保留一个可复现的最优提交版本。

## 更换评测数据

默认评测文件是：

```text
llm4ad/task/optimization/courier_bundle_assignment/official_large_seed301.txt
```

如需换数据，可以实例化评测器时传入文件路径：

```python
from llm4ad.task.optimization.courier_bundle_assignment import CourierBundleAssignmentEvaluation

task = CourierBundleAssignmentEvaluation(case_file="/path/to/case.tsv")
```

相对路径会按 `evaluation.py` 所在目录解析；绝对路径会直接读取。

## 运行 LLM 搜索

编辑：

```text
example/tasks/courier_bundle_assignment/run_eoh.py
```

配置 LLM 接口：

```python
llm = HttpsApi(
    host="xxx",
    key="sk-xxx",
    model="xxx",
    timeout=60,
)
```

启动搜索：

```bash
uv run python example/tasks/courier_bundle_assignment/run_eoh.py
```

搜索过程会生成候选 `solve()`，通过 `CourierBundleAssignmentEvaluation` 评测，并把结果写入 `logs/`。

## 直接在代码中评测

```python
from llm4ad.base import SecureEvaluator
from llm4ad.task.optimization.courier_bundle_assignment import (
    CourierBundleAssignmentEvaluation,
    template_program,
)

task = CourierBundleAssignmentEvaluation(timeout_seconds=10)
evaluator = SecureEvaluator(task)
fitness = evaluator.evaluate_program(template_program)
print("objective:", -fitness)
```

评测 `bestsolver.py`：

```python
from bestsolver import solve
from llm4ad.task.optimization.courier_bundle_assignment import CourierBundleAssignmentEvaluation

task = CourierBundleAssignmentEvaluation(timeout_seconds=10)
objective = task.evaluate_solution(solve(task.input_text))
print("objective:", objective)
```

## 验证命令

常用检查：

```bash
uv run python example/tasks/courier_bundle_assignment/run_baseline.py
uv run python -c "from bestsolver import solve; from llm4ad.task.optimization.courier_bundle_assignment import CourierBundleAssignmentEvaluation; t=CourierBundleAssignmentEvaluation(); print(t.evaluate_solution(solve(t.input_text)))"
uv run python -m compileall llm4ad example/tasks/courier_bundle_assignment
```

导入检查：

```bash
uv run python - <<'PY'
from llm4ad.method.eoh import EoH
from llm4ad.tools.llm import HttpsApi
from llm4ad.tools.profiler import ProfilerBase
from llm4ad.task import CourierBundleAssignmentEvaluation
print(EoH.__name__, HttpsApi.__name__, ProfilerBase.__name__, CourierBundleAssignmentEvaluation.__name__)
PY
```

## 开发建议

- 修改 `template.py` 后先运行 `run_baseline.py`
- 如果输出非法，评测器会打印失败原因
- 基线目标值可作为回归参考，改动后不应无意退化
- 搜索日志默认不纳入版本控制

## 仓库状态

本仓库已经删除旧项目中与本系统无关的任务、示例、GUI、图片素材和旧依赖文件。当前公开仓库只保留配送求解系统需要的核心代码与数据。
