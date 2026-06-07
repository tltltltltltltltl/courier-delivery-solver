# 外卖配送任务束分配求解系统

这是一个面向外卖配送任务束分配问题的算法设计与评测项目。系统输入一批候选配送方案，选择任务束和骑手的组合，在合法性约束下最小化期望总成本。

## 问题概述

输入数据是 TSV 文本，每行表示一个候选报价：

```text
task_id_list    courier_id    total_score    willingness
```

含义如下：

- `task_id_list`：一个任务或任务束，例如 `T0012` 或 `T0012,T0034`
- `courier_id`：可接该任务束的骑手
- `total_score`：该候选方案的成本分数
- `willingness`：骑手接受该方案的概率

系统需要返回：

```python
[(task_id_list_str, [courier_id, ...]), ...]
```

同一个任务束可以配置多个备选骑手，但必须满足：

- 每个骑手最多使用一次
- 不能虚构输入中不存在的 `(task_id_list, courier_id)` 组合
- 不同任务束之间不能共享任务
- 可以不覆盖所有任务，未覆盖任务按漏单概率 `1` 计入惩罚

目标函数为：

```text
sum(group_expected_score(bundle)) + 100 * sum(miss(task))
```

其中一个任务束内多个备选骑手的漏单概率为：

```text
group_miss(S) = product(1 - willingness_c)
```

期望配送成本为：

```text
group_expected_score(S)
  = (1 - group_miss(S)) * sum(willingness_c * total_score_c) / sum(willingness_c)
```

## 目录结构

```text
.
├── llm4ad/
│   ├── base/                         # 程序执行、超时保护和评测基类
│   ├── method/                       # 可选的 LLM/进化式算法搜索方法
│   ├── tools/                        # LLM 接口和日志工具
│   └── task/optimization/
│       └── courier_bundle_assignment/
│           ├── evaluation.py         # 外卖配送问题评测器
│           ├── template.py           # solve(input_text) 模板和基线启发式
│           ├── paras.yaml            # 任务参数
│           └── official_large_seed301.txt
├── example/tasks/courier_bundle_assignment/
│   ├── run_baseline.py               # 直接评测模板求解器
│   └── run_eoh.py                    # 使用 LLM 搜索改进求解器的示例
├── pyproject.toml
└── uv.lock
```

仓库中已经删除了与本问题无关的历史任务、旧示例、GUI、图片素材和旧依赖文件。

## 环境管理

本项目使用 `uv` 管理 Python 环境。

```bash
uv sync
```

Python 版本要求：

```text
>=3.9,<3.13
```

当前工程环境默认安装 `numpy`，便于框架侧或分析脚本使用；但被评测的 `solve()` 求解器算法仍按题目要求保持零依赖，只使用 Python 标准库。若要使用 LLM 搜索示例，需要根据所选接口安装或补充相应的 LLM 客户端依赖。

## 快速评测

运行内置基线求解器：

```bash
uv run python example/tasks/courier_bundle_assignment/run_baseline.py
```

在内置大用例 `official_large_seed301.txt` 上，当前模板求解器的参考输出为：

```text
case: CaseData(lines=33781, tasks=40, candidates=33780)
fitness: -930.2886616069427
objective: 930.2886616069427
```

评测器返回的是 fitness，内部约定为 `-objective`，因此目标函数越小越好，fitness 越大越好。

## 开发自己的求解器

核心接口是：

```python
def solve(input_text: str) -> list:
    ...
```

约束：

- 所有 import、helper 函数和辅助数据结构都应放在 `solve()` 内部
- 只能使用 Python 标准库
- 返回值必须是 `[(task_id_list_str, [courier_id, ...]), ...]`

可直接修改：

```text
llm4ad/task/optimization/courier_bundle_assignment/template.py
```

评测器会检查：

- 输出是否可迭代
- 每个任务束是否重复
- 骑手是否重复使用
- 任务是否被多个任务束覆盖
- 每个 `(task_id_list, courier_id)` 是否来自输入数据

## 使用 LLM 搜索

示例入口：

```bash
uv run python example/tasks/courier_bundle_assignment/run_eoh.py
```

运行前需要在脚本中配置：

```python
llm = HttpsApi(
    host="xxx",
    key="sk-xxx",
    model="xxx",
    timeout=60,
)
```

`run_eoh.py` 会以 `CourierBundleAssignmentEvaluation` 作为评测任务，生成并评估新的 `solve()` 实现。

## 重要文件

- `evaluation.py`：负责读取数据、校验解、计算目标函数
- `template.py`：包含问题说明和当前基线启发式
- `official_large_seed301.txt`：内置大规模评测数据
- `paras.yaml`：任务默认参数

## 当前基线思路

模板中的基线求解器将问题转化为“相对全漏单基线的收益最大化”：

```text
收益 = 漏单罚分减少量 - 期望配送成本
```

求解过程会先为每个任务束生成若干骑手备选组合，再在任务不重叠、骑手不重复的约束下做多轮贪心选择和局部替换。这个版本用于提供可靠起点，后续可以继续通过手写启发式或 LLM 搜索改进。
