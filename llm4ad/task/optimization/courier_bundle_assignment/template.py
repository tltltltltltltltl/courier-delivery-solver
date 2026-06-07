template_program = '''
def solve(input_text: str) -> list:
    """
    Select task-bundle to courier assignments for the courier bundle assignment problem.

    Input:
        input_text: TSV text with a header and rows:
            task_id_list<TAB>courier_id<TAB>total_score<TAB>willingness

    Output:
        A list of (task_id_list_str, [courier_id, ...]) pairs.

    Feasibility rules:
        - Each courier can be used at most once.
        - Multiple couriers may be assigned to the exact same task_id_list as backup couriers.
        - No task may appear in more than one selected task_id_list in the output.
        - Every returned (task_id_list, courier_id) pair must exist in the input.
        - It is not required to cover every task.
        - Use only the Python standard library.
        - Put all imports, helper functions, and helper data structures inside solve().

    Objective:
        Minimize:
            sum(group_expected_score(bundle)) + 100 * sum(miss(task))
    """
    from collections import defaultdict

    lines = input_text.strip().splitlines()
    start = 1 if lines and lines[0].startswith("task_id_list") else 0

    task_index = {}
    courier_index = {}
    best_pair = {}

    for raw_line in lines[start:]:
        parts = raw_line.strip().split("\\t")
        if len(parts) < 4:
            continue
        task_id_list = parts[0].strip()
        courier_id = parts[1].strip()
        if not task_id_list or not courier_id:
            continue
        try:
            total_score = float(parts[2])
            willingness = float(parts[3])
        except ValueError:
            continue
        if willingness < 0.0:
            willingness = 0.0
        elif willingness > 1.0:
            willingness = 1.0

        tasks = tuple(task.strip() for task in task_id_list.split(",") if task.strip())
        if not tasks:
            continue
        for task_id in tasks:
            if task_id not in task_index:
                task_index[task_id] = len(task_index)
        if courier_id not in courier_index:
            courier_index[courier_id] = len(courier_index)

        key = (task_id_list, courier_id)
        previous = best_pair.get(key)
        if previous is None or total_score < previous[0]:
            best_pair[key] = (total_score, willingness, tasks)

    if not best_pair:
        return []

    by_bundle = defaultdict(list)
    for (task_id_list, courier_id), (total_score, willingness, tasks) in best_pair.items():
        by_bundle[task_id_list].append((courier_id, total_score, willingness, tasks))

    def group_objective(candidates, task_count):
        miss_probability = 1.0
        willingness_sum = 0.0
        weighted_score = 0.0
        for _, total_score, willingness, _ in candidates:
            miss_probability *= 1.0 - willingness
            willingness_sum += willingness
            weighted_score += total_score * willingness
        expected_score = 0.0
        if willingness_sum > 0.0:
            expected_score = (1.0 - miss_probability) * weighted_score / willingness_sum
        return expected_score + 100.0 * task_count * miss_probability

    options = []
    for task_id_list, candidates in by_bundle.items():
        tasks = candidates[0][3]
        task_count = len(tasks)
        task_mask = 0
        for task_id in tasks:
            task_mask |= 1 << task_index[task_id]

        ranked = []
        for candidate in candidates:
            benefit = 100.0 * task_count - group_objective([candidate], task_count)
            courier_id, total_score, willingness, _ = candidate
            ranked.append((benefit, willingness, -total_score, courier_id, candidate))
        ranked.sort(reverse=True)
        top_candidates = [item[4] for item in ranked[:10]]

        local_options = []
        for candidate in top_candidates:
            benefit = 100.0 * task_count - group_objective([candidate], task_count)
            if benefit > 1e-9:
                local_options.append((benefit, [candidate]))

        combination_pool = top_candidates[:8]
        pool_size = len(combination_pool)
        for i in range(pool_size):
            for j in range(i + 1, pool_size):
                pair = [combination_pool[i], combination_pool[j]]
                benefit = 100.0 * task_count - group_objective(pair, task_count)
                if benefit > 1e-9:
                    local_options.append((benefit, pair))
                for h in range(j + 1, pool_size):
                    triple = [combination_pool[i], combination_pool[j], combination_pool[h]]
                    benefit = 100.0 * task_count - group_objective(triple, task_count)
                    if benefit > 1e-9:
                        local_options.append((benefit, triple))

        chosen = []
        remaining = top_candidates[:16]
        current_objective = 100.0 * task_count
        for _ in range(6):
            best_add = None
            best_objective = current_objective
            for candidate in remaining:
                objective = group_objective(chosen + [candidate], task_count)
                if objective < best_objective - 1e-9:
                    best_objective = objective
                    best_add = candidate
            if best_add is None:
                break
            chosen.append(best_add)
            remaining.remove(best_add)
            current_objective = best_objective
            benefit = 100.0 * task_count - current_objective
            if benefit > 1e-9:
                local_options.append((benefit, chosen[:]))

        seen_courier_sets = set()
        kept = 0
        for benefit, candidate_group in sorted(local_options, key=lambda item: item[0], reverse=True):
            courier_ids = [candidate[0] for candidate in candidate_group]
            key = tuple(sorted(courier_ids))
            if key in seen_courier_sets:
                continue
            seen_courier_sets.add(key)
            courier_mask = 0
            for courier_id in courier_ids:
                courier_mask |= 1 << courier_index[courier_id]
            options.append(
                {
                    "task_id_list": task_id_list,
                    "couriers": courier_ids,
                    "benefit": benefit,
                    "task_mask": task_mask,
                    "courier_mask": courier_mask,
                }
            )
            kept += 1
            if kept >= 18:
                break

    best_solution = []
    best_benefit = 0.0
    search_settings = []
    for courier_penalty in (0.0, 0.05, 0.1, 0.2, 0.35, 0.6, 1.0):
        for task_power in (0.0, 0.4, 0.8, 1.2):
            search_settings.append((courier_penalty, task_power))

    for courier_penalty, task_power in search_settings:
        def option_rank(option):
            courier_factor = (option["courier_mask"].bit_count() + courier_penalty) ** 0.5
            if task_power:
                task_factor = option["task_mask"].bit_count() ** task_power
            else:
                task_factor = 1.0
            return option["benefit"] / (courier_factor * task_factor)

        ordered_options = sorted(options, key=option_rank, reverse=True)
        task_mask = 0
        courier_mask = 0
        solution = []
        total_benefit = 0.0

        for option in ordered_options:
            if option["task_mask"] & task_mask:
                continue
            if option["courier_mask"] & courier_mask:
                continue
            task_mask |= option["task_mask"]
            courier_mask |= option["courier_mask"]
            solution.append(option)
            total_benefit += option["benefit"]

        improved = True
        while improved:
            improved = False
            for remove_index in range(len(solution)):
                remaining_solution = [
                    option for index, option in enumerate(solution) if index != remove_index
                ]
                trial_task_mask = 0
                trial_courier_mask = 0
                trial_benefit = 0.0
                for option in remaining_solution:
                    trial_task_mask |= option["task_mask"]
                    trial_courier_mask |= option["courier_mask"]
                    trial_benefit += option["benefit"]

                additions = []
                for option in ordered_options:
                    if option["task_mask"] & trial_task_mask:
                        continue
                    if option["courier_mask"] & trial_courier_mask:
                        continue
                    trial_task_mask |= option["task_mask"]
                    trial_courier_mask |= option["courier_mask"]
                    trial_benefit += option["benefit"]
                    additions.append(option)

                if trial_benefit > total_benefit + 1e-9:
                    solution = remaining_solution + additions
                    total_benefit = trial_benefit
                    improved = True
                    break

        if total_benefit > best_benefit:
            best_benefit = total_benefit
            best_solution = solution

    return [(option["task_id_list"], option["couriers"]) for option in best_solution]
'''

task_description = """
Given task bundles and courier offers, choose assignments that minimize expected total cost.
Each input row gives a task bundle, a courier, a total_score cost, and a willingness probability.
The same task_id_list usually appears in multiple rows with different couriers. Selecting
multiple couriers for one task_id_list means using those existing rows as backup offers;
it does not allow inventing a (task_id_list, courier_id) pair that is absent from the input.
For one selected task bundle with backup couriers S, miss(S)=product(1-w_c), and
group_expected_score(S)=(1-miss(S))*sum(w_c*score_c)/sum(w_c).
The final objective is sum of group_expected_score over selected bundles plus 100 times the
miss probability of every task. The solver should return valid assignments in the contest
interface format: [(task_id_list_str, [courier_id, ...]), ...].

Important feasibility constraint: two different selected task_id_list strings must be
task-disjoint. A task can be covered by only one selected bundle. It is valid to assign
multiple backup couriers to the same selected task_id_list, but it is invalid to select
two different bundles that share any task.

Examples:
- Valid backup assignment if both pairs exist in the input:
  [("T0012", ["C001", "C007"])].
- Invalid pair if ("T0012", "C099") is not an input row:
  [("T0012", ["C099"])].
- Invalid overlap because task T0012 is covered twice:
  [("T0012", ["C001"]), ("T0012,T0034", ["C007"])].
- Valid but penalized: leaving some tasks uncovered.

Implementation constraint: the evaluator uses only the body of solve(). Any generated
imports, helper classes, helper functions, or global variables outside solve() are not
available during evaluation. If an algorithm needs them, define them inside solve().
"""
