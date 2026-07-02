import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta


NUMBER_MIN = 1
NUMBER_MAX = 39
DRAW_SIZE = 5
BASE_PROBABILITY = DRAW_SIZE / NUMBER_MAX
EXPECTED_GAP = NUMBER_MAX / DRAW_SIZE


MODEL_LABELS = {
    "dirichlet_multinomial": "bayes_dirichlet_multinomial",
    "beta_inclusion": "beta_inclusion_posterior",
    "omission_wave": "omission_rebound_wave",
    "transition_lag": "lagged_transition_follow",
    "shape_similarity": "draw_shape_similarity",
    "tail_bucket_pressure": "tail_bucket_pressure",
    "calendar_cycle": "calendar_cycle_mapping",
    "pair_echo": "pair_echo_follow",
    "review_recall": "settlement_error_recall",
}


def clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value or 0.0)))


def normalize(values):
    if not values:
        return {}
    low = min(values.values())
    high = max(values.values())
    if abs(high - low) < 1e-12:
        return {key: 0.0 for key in values}
    return {key: (value - low) / (high - low) for key, value in values.items()}


def rank_values(values):
    return sorted(range(NUMBER_MIN, NUMBER_MAX + 1), key=lambda n: (values.get(n, 0.0), -n), reverse=True)


def numbers_range():
    return range(NUMBER_MIN, NUMBER_MAX + 1)


def next_draw_date(date_text):
    current = datetime.strptime(date_text, "%Y-%m-%d").date()
    candidate = current + timedelta(days=1)
    while candidate.weekday() == 6:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def normalize_number(value):
    value = abs(int(value))
    if value <= 0:
        return NUMBER_MAX
    return ((value - 1) % NUMBER_MAX) + 1


def bucket8(number):
    if number <= 5:
        return "01-05"
    if number <= 10:
        return "06-10"
    if number <= 15:
        return "11-15"
    if number <= 20:
        return "16-20"
    if number <= 25:
        return "21-25"
    if number <= 30:
        return "26-30"
    if number <= 35:
        return "31-35"
    return "36-39"


def draw_shape(numbers):
    values = sorted(int(n) for n in numbers)
    buckets = Counter(bucket8(n) for n in values)
    tails = Counter(n % 10 for n in values)
    return {
        "odd": sum(1 for n in values if n % 2),
        "high": sum(1 for n in values if n >= 20),
        "sum_bucket": sum(values) // 20,
        "spread_bucket": (max(values) - min(values)) // 6,
        "bucket_count": len(buckets),
        "tail_count": len(tails),
        "buckets": buckets,
        "tails": tails,
    }


def shape_distance(left, right):
    score = 0.0
    for key, weight in [
        ("odd", 0.70),
        ("high", 0.70),
        ("sum_bucket", 0.55),
        ("spread_bucket", 0.40),
        ("bucket_count", 0.45),
        ("tail_count", 0.35),
    ]:
        score += abs(left[key] - right[key]) * weight
    all_buckets = set(left["buckets"]) | set(right["buckets"])
    score += sum(abs(left["buckets"].get(k, 0) - right["buckets"].get(k, 0)) for k in all_buckets) * 0.28
    all_tails = set(left["tails"]) | set(right["tails"])
    score += sum(abs(left["tails"].get(k, 0) - right["tails"].get(k, 0)) for k in all_tails) * 0.10
    return score


def frequency(draws):
    counter = Counter()
    for draw in draws:
        counter.update(int(n) for n in draw["numbers"])
    return counter


def omission_map(draws):
    last_seen = {n: None for n in numbers_range()}
    for idx, draw in enumerate(draws):
        for number in draw["numbers"]:
            last_seen[int(number)] = idx
    last_index = len(draws) - 1
    return {
        number: (last_index - last_seen[number] if last_seen[number] is not None else len(draws))
        for number in numbers_range()
    }


def ewma_counts(draws, half_life=80):
    scores = {n: 0.0 for n in numbers_range()}
    if not draws:
        return scores
    decay = 0.5 ** (1.0 / max(half_life, 1))
    for age, draw in enumerate(reversed(draws)):
        weight = decay ** age
        for number in draw["numbers"]:
            scores[int(number)] += weight
    return scores


def dirichlet_multinomial_scores(draws):
    counts = frequency(draws)
    fast = ewma_counts(draws, 35)
    slow = ewma_counts(draws, 160)
    total = max(len(draws) * DRAW_SIZE, 1)
    alpha = 1.65
    values = {}
    for number in numbers_range():
        blended_count = counts[number] * 0.55 + fast[number] * 5.0 + slow[number] * 1.4
        values[number] = (alpha + blended_count) / (NUMBER_MAX * alpha + total)
    return normalize(values)


def beta_inclusion_scores(draws):
    counts = frequency(draws)
    draw_count = max(len(draws), 1)
    alpha = 2.0
    beta = alpha * (1.0 / BASE_PROBABILITY - 1.0)
    values = {
        number: (alpha + counts[number]) / (alpha + beta + draw_count)
        for number in numbers_range()
    }
    return normalize(values)


def omission_wave_scores(draws):
    omissions = omission_map(draws)
    values = {}
    center = EXPECTED_GAP * 1.18
    width = EXPECTED_GAP * 0.85
    for number, gap in omissions.items():
        wave = math.exp(-((gap - center) ** 2) / (2 * width * width))
        if gap <= 1:
            wave *= 0.20
        elif gap >= EXPECTED_GAP * 3.4:
            wave *= 0.72
        values[number] = wave
    return normalize(values)


def transition_lag_scores(draws, lookback=900):
    if len(draws) < 3:
        return {n: 0.0 for n in numbers_range()}
    latest = set(int(n) for n in draws[-1]["numbers"])
    latest_tails = {n % 10 for n in latest}
    latest_buckets = {bucket8(n) for n in latest}
    scores = Counter()
    subset_start = max(0, len(draws) - lookback - 1)
    for idx in range(subset_start, len(draws) - 1):
        current = set(int(n) for n in draws[idx]["numbers"])
        anchors = len(current & latest)
        tail_hits = sum(1 for n in current if n % 10 in latest_tails)
        bucket_hits = sum(1 for n in current if bucket8(n) in latest_buckets)
        if anchors == 0 and tail_hits < 2 and bucket_hits < 2:
            continue
        recency = 1.0 + (idx - subset_start) / max(len(draws) - subset_start, 1)
        weight = (anchors * 1.00 + tail_hits * 0.18 + bucket_hits * 0.15) * recency
        for number in draws[idx + 1]["numbers"]:
            scores[int(number)] += weight
    return normalize({n: scores.get(n, 0.0) for n in numbers_range()})


def pair_echo_scores(draws, lookback=1200):
    if len(draws) < 4:
        return {n: 0.0 for n in numbers_range()}
    latest = sorted(int(n) for n in draws[-1]["numbers"])
    latest_pairs = {tuple(pair) for idx, a in enumerate(latest) for pair in [(a, b) for b in latest[idx + 1:]]}
    latest_adjacent = {abs(a - b) for a, b in latest_pairs}
    scores = Counter()
    subset_start = max(0, len(draws) - lookback - 1)
    for idx in range(subset_start, len(draws) - 1):
        current = sorted(int(n) for n in draws[idx]["numbers"])
        current_pairs = {tuple(pair) for pos, a in enumerate(current) for pair in [(a, b) for b in current[pos + 1:]]}
        pair_hits = len(current_pairs & latest_pairs)
        distance_hits = sum(1 for a, b in current_pairs if abs(a - b) in latest_adjacent)
        if pair_hits == 0 and distance_hits < 2:
            continue
        weight = pair_hits * 1.8 + distance_hits * 0.16
        for number in draws[idx + 1]["numbers"]:
            scores[int(number)] += weight
    return normalize({n: scores.get(n, 0.0) for n in numbers_range()})


def tail_bucket_pressure_scores(draws, recent_window=50, long_window=600):
    recent = draws[-recent_window:] if len(draws) >= recent_window else draws
    long = draws[-long_window:] if len(draws) >= long_window else draws
    recent_bucket = Counter(bucket8(n) for draw in recent for n in draw["numbers"])
    long_bucket = Counter(bucket8(n) for draw in long for n in draw["numbers"])
    recent_tail = Counter(int(n) % 10 for draw in recent for n in draw["numbers"])
    long_tail = Counter(int(n) % 10 for draw in long for n in draw["numbers"])
    recent_total = max(len(recent) * DRAW_SIZE, 1)
    long_total = max(len(long) * DRAW_SIZE, 1)
    values = {}
    for number in numbers_range():
        b = bucket8(number)
        t = number % 10
        bucket_deficit = long_bucket[b] / long_total - recent_bucket[b] / recent_total
        tail_deficit = long_tail[t] / long_total - recent_tail[t] / recent_total
        values[number] = bucket_deficit * 0.68 + tail_deficit * 0.32
    return normalize(values)


def shape_similarity_scores(draws, lookback=900):
    if len(draws) < 8:
        return {n: 0.0 for n in numbers_range()}
    target_shape = draw_shape(draws[-1]["numbers"])
    scores = Counter()
    subset_start = max(0, len(draws) - lookback - 1)
    for idx in range(subset_start, len(draws) - 1):
        distance = shape_distance(draw_shape(draws[idx]["numbers"]), target_shape)
        if distance > 4.4:
            continue
        weight = 1.0 / (1.0 + distance)
        for number in draws[idx + 1]["numbers"]:
            scores[int(number)] += weight
    return normalize({n: scores.get(n, 0.0) for n in numbers_range()})


def calendar_cycle_scores(draws):
    latest_date = draws[-1].get("draw_date") if draws else None
    if not latest_date:
        return {n: 0.0 for n in numbers_range()}
    target = datetime.strptime(next_draw_date(latest_date), "%Y-%m-%d")
    roc_year = target.year - 1911
    raw_values = [
        roc_year,
        target.month,
        target.day,
        int(f"{target.month}{target.day:02d}"),
        int(target.strftime("%m%d")),
        sum(int(ch) for ch in target.strftime("%Y%m%d")),
        roc_year + target.month,
        roc_year + target.day,
        target.month + target.day,
        target.isoweekday() + target.day,
    ]
    direct = {normalize_number(value) for value in raw_values}
    values = {n: 0.0 for n in numbers_range()}
    for number in numbers_range():
        values[number] = max(0.0, 1.0 - min(abs(number - target_number) for target_number in direct) / 12.0)
        if number in direct:
            values[number] = 1.0
    return normalize(values)


def review_recall_scores(draws, review):
    values = {n: 0.0 for n in numbers_range()}
    if not review:
        return values
    rolling = review.get("rolling_adjustment", {}) or {}
    weighted_keys = [
        ("late_hit_numbers", 0.95),
        ("missed_actual_numbers", 0.88),
        ("monthly_recall_numbers", 0.82),
        ("repeated_failed_numbers", -0.55),
    ]
    for key, weight in weighted_keys:
        for item in rolling.get(key, []) or []:
            try:
                number = int(item.get("number"))
            except (TypeError, ValueError):
                continue
            if NUMBER_MIN <= number <= NUMBER_MAX:
                values[number] += weight
    for key, weight in [("missed_actual_tails", 0.18), ("monthly_recall_tails", 0.13)]:
        tails = {int(item.get("tail")) for item in rolling.get(key, []) or [] if item.get("tail") is not None}
        for number in numbers_range():
            if number % 10 in tails:
                values[number] += weight
    for key, weight in [("missed_actual_zones", 0.16), ("monthly_recall_zones", 0.12)]:
        zones = {str(item.get("zone")) for item in rolling.get(key, []) or [] if item.get("zone")}
        for number in numbers_range():
            if bucket8(number) in zones:
                values[number] += weight
    return normalize(values)


def model_score_maps(draws, review=None, fast=False):
    transition_lookback = 260 if fast else 900
    shape_lookback = 280 if fast else 900
    pair_lookback = 320 if fast else 1200
    long_window = 260 if fast else 600
    maps = {
        "dirichlet_multinomial": dirichlet_multinomial_scores(draws),
        "beta_inclusion": beta_inclusion_scores(draws),
        "omission_wave": omission_wave_scores(draws),
        "transition_lag": transition_lag_scores(draws, lookback=transition_lookback),
        "shape_similarity": shape_similarity_scores(draws, lookback=shape_lookback),
        "tail_bucket_pressure": tail_bucket_pressure_scores(draws, long_window=long_window),
        "calendar_cycle": calendar_cycle_scores(draws),
        "pair_echo": pair_echo_scores(draws, lookback=pair_lookback),
    }
    recall = review_recall_scores(draws, review)
    if max(recall.values() or [0]) > 0:
        maps["review_recall"] = recall
    return maps


def model_backtest(draws, rounds=96):
    if len(draws) < 160:
        return {"rounds": 0, "models": {}, "status": "insufficient_history"}
    start = max(120, len(draws) - rounds - 1)
    keys = [
        "dirichlet_multinomial",
        "beta_inclusion",
        "omission_wave",
        "transition_lag",
        "shape_similarity",
        "tail_bucket_pressure",
        "calendar_cycle",
        "pair_echo",
    ]
    totals = {key: {"rounds": 0, "top5_hits": 0, "top9_hits": 0, "top15_hits": 0, "bottom5_hits": 0, "bottom10_hits": 0, "bottom15_hits": 0} for key in keys}
    for idx in range(start, len(draws) - 1):
        train = draws[: idx + 1]
        actual = set(int(n) for n in draws[idx + 1]["numbers"])
        maps = model_score_maps(train, None, fast=True)
        for key in keys:
            scores = maps.get(key) or {n: 0.0 for n in numbers_range()}
            ranked = rank_values(scores)
            bottom = list(reversed(ranked))
            totals[key]["rounds"] += 1
            totals[key]["top5_hits"] += len(set(ranked[:5]) & actual)
            totals[key]["top9_hits"] += len(set(ranked[:9]) & actual)
            totals[key]["top15_hits"] += len(set(ranked[:15]) & actual)
            totals[key]["bottom5_hits"] += len(set(bottom[:5]) & actual)
            totals[key]["bottom10_hits"] += len(set(bottom[:10]) & actual)
            totals[key]["bottom15_hits"] += len(set(bottom[:15]) & actual)
    result = {}
    for key, data in totals.items():
        rounds_done = max(data["rounds"], 1)
        top5 = data["top5_hits"] / rounds_done
        top9 = data["top9_hits"] / rounds_done
        top15 = data["top15_hits"] / rounds_done
        bottom5 = data["bottom5_hits"] / rounds_done
        bottom10 = data["bottom10_hits"] / rounds_done
        bottom15 = data["bottom15_hits"] / rounds_done
        random5 = DRAW_SIZE * 5 / NUMBER_MAX
        random9 = DRAW_SIZE * 9 / NUMBER_MAX
        random15 = DRAW_SIZE * 15 / NUMBER_MAX
        result[key] = {
            "label": MODEL_LABELS.get(key, key),
            "rounds": data["rounds"],
            "top5_avg_hits": round(top5, 4),
            "top9_avg_hits": round(top9, 4),
            "top15_avg_hits": round(top15, 4),
            "top5_edge_vs_random": round(top5 - random5, 4),
            "top9_edge_vs_random": round(top9 - random9, 4),
            "top15_edge_vs_random": round(top15 - random15, 4),
            "bottom5_avg_hits": round(bottom5, 4),
            "bottom10_avg_hits": round(bottom10, 4),
            "bottom15_avg_hits": round(bottom15, 4),
            "avoid5_edge_vs_random": round(random5 - bottom5, 4),
            "avoid10_edge_vs_random": round(DRAW_SIZE * 10 / NUMBER_MAX - bottom10, 4),
            "avoid15_edge_vs_random": round(random15 - bottom15, 4),
        }
    return {
        "rounds": max((item["rounds"] for item in result.values()), default=0),
        "random_expectation": {
            "top5": round(DRAW_SIZE * 5 / NUMBER_MAX, 4),
            "top9": round(DRAW_SIZE * 9 / NUMBER_MAX, 4),
            "top15": round(DRAW_SIZE * 15 / NUMBER_MAX, 4),
        },
        "models": result,
        "status": "completed",
    }


def derive_model_weights(backtest):
    models = backtest.get("models", {}) or {}
    raw = {}
    for key, data in models.items():
        top9_edge = float(data.get("top9_edge_vs_random", 0.0) or 0.0)
        top5_edge = float(data.get("top5_edge_vs_random", 0.0) or 0.0)
        top15_edge = float(data.get("top15_edge_vs_random", 0.0) or 0.0)
        value = max(0.0, top9_edge * 1.00 + top5_edge * 0.55 + top15_edge * 0.25)
        raw[key] = 0.025 + value
    if not raw or sum(raw.values()) <= 0:
        return {key: round(1 / max(len(models), 1), 4) for key in models}
    total = sum(raw.values())
    return {key: round(value / total, 4) for key, value in raw.items()}


def candidate_allowed(item):
    if not item:
        return True
    hard = item.get("hard_iron_rule") or {}
    repeat = item.get("repeat_guard") or {}
    previous = item.get("previous_prediction_guard") or {}
    if hard.get("blocked"):
        return False
    if repeat and not repeat.get("passed"):
        return False
    if previous and not previous.get("passed"):
        recovery = int(previous.get("recovery_condition_count") or 0)
        strong = int(previous.get("strong_condition_count") or 0)
        if recovery == 0 and strong < 2:
            return False
    return True


def build_ensemble(draws, candidates=None, review=None, backtest=None):
    maps = model_score_maps(draws, review)
    backtest = backtest or model_backtest(draws)
    weights = derive_model_weights(backtest)
    if "review_recall" in maps and "review_recall" not in weights:
        weights["review_recall"] = 0.075
        total = sum(weights.values())
        weights = {key: round(value / total, 4) for key, value in weights.items()}
    candidate_map = {int(item["number"]): item for item in (candidates or []) if item.get("number")}
    rows = []
    for number in numbers_range():
        source_models = []
        score = 0.0
        for key, scores in maps.items():
            model_score = float(scores.get(number, 0.0) or 0.0)
            weight = float(weights.get(key, 0.0) or 0.0)
            score += model_score * weight
            if model_score >= 0.62:
                source_models.append(key)
        candidate_item = candidate_map.get(number)
        candidate_score = float(candidate_item.get("score", 0.0) if candidate_item else 0.0)
        cross = int(((candidate_item or {}).get("cross_validation") or {}).get("passed_count") or 0)
        stability = int((candidate_item or {}).get("stability_count") or 0)
        score = clamp(score * 0.72 + candidate_score * 0.21 + min(cross, 10) / 10 * 0.04 + min(stability, 5) / 5 * 0.03)
        rows.append({
            "number": number,
            "score": round(score, 4),
            "source_models": source_models,
            "support_count": len(source_models),
            "candidate_score": round(candidate_score, 4),
            "candidate_rank": int((candidate_item or {}).get("rank") or 99),
            "allowed": candidate_allowed(candidate_item),
        })
    rows.sort(key=lambda row: (row["allowed"], row["score"], row["support_count"], -row["candidate_rank"], -row["number"]), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows, maps, weights


def select_pack(ensemble, size):
    selected = []
    pool = [row for row in ensemble if row.get("allowed")]
    while len(selected) < size and pool:
        best = max(
            pool,
            key=lambda row: (
                row["score"]
                - sum(0.030 for n in selected if n % 10 == row["number"] % 10)
                - sum(0.042 for n in selected if bucket8(n) == bucket8(row["number"]))
                - sum(0.020 for n in selected if abs(n - row["number"]) == 1),
                row["support_count"],
                -row["number"],
            ),
        )
        selected.append(best["number"])
        pool.remove(best)
    return sorted(selected)


def build_pack_plan(ensemble):
    return {
        "strong_single": {"size": 1, "numbers": select_pack(ensemble, 1)},
        "two_hit_one": {"size": 2, "numbers": select_pack(ensemble, 2)},
        "three_hit_one": {"size": 3, "numbers": select_pack(ensemble, 3)},
        "five_hit_two": {"size": 5, "numbers": select_pack(ensemble, 5)},
        "nine_hit_three": {"size": 9, "numbers": select_pack(ensemble, 9)},
    }


def build_avoid_plan(ensemble, backtest):
    models = backtest.get("models", {}) or {}
    avoid_edges = [float(item.get("avoid10_edge_vs_random", 0.0) or 0.0) for item in models.values()]
    avg_avoid_edge = sum(avoid_edges) / len(avoid_edges) if avoid_edges else 0.0
    bottom = sorted(ensemble, key=lambda row: (row["score"], row["support_count"], -row["candidate_rank"], row["number"]))
    result = {}
    for key, size in [("five_miss", 5), ("ten_miss", 10), ("fifteen_miss", 15)]:
        numbers = [row["number"] for row in bottom[:size]]
        result[key] = {
            "numbers": numbers if avg_avoid_edge > 0.02 else [],
            "diagnostic_numbers": numbers,
            "avg_avoid_edge": round(avg_avoid_edge, 4),
            "status": "released" if avg_avoid_edge > 0.02 else "withheld_backtest_not_positive",
        }
    return result


def source_summary(backtest):
    rows = []
    for key, data in sorted((backtest.get("models") or {}).items(), key=lambda pair: pair[1].get("top9_edge_vs_random", -99), reverse=True):
        action = "active" if float(data.get("top9_edge_vs_random", 0.0) or 0.0) >= 0 else "low_weight"
        rows.append({
            "model": key,
            "label": MODEL_LABELS.get(key, key),
            "rounds": data.get("rounds", 0),
            "top5_avg_hits": data.get("top5_avg_hits"),
            "top9_avg_hits": data.get("top9_avg_hits"),
            "top15_avg_hits": data.get("top15_avg_hits"),
            "top9_edge_vs_random": data.get("top9_edge_vs_random"),
            "avoid10_edge_vs_random": data.get("avoid10_edge_vs_random"),
            "action": action,
        })
    return rows


def run_formula_lab(draws, candidates=None, review=None, rounds=96):
    try:
        if len(draws) < 100:
            return {"status": "insufficient_history", "version": "formula_lab_v1"}
        backtest = model_backtest(draws, rounds=rounds)
        ensemble, maps, weights = build_ensemble(draws, candidates, review, backtest)
        return {
            "status": "ready",
            "version": "formula_lab_v1",
            "source_basis": [
                "dirichlet_multinomial_posterior",
                "beta_inclusion_posterior",
                "hypergeometric_random_baseline",
                "lagged_transition",
                "shape_similarity",
                "tail_bucket_pressure",
                "calendar_cycle",
                "pair_echo",
                "settlement_error_recall",
            ],
            "backtest": backtest,
            "model_weights": weights,
            "model_summary": source_summary(backtest),
            "ensemble": ensemble,
            "pack_plan": build_pack_plan(ensemble),
            "avoid_plan": build_avoid_plan(ensemble, backtest),
            "top9": [row["number"] for row in ensemble[:9]],
            "maps_available": sorted(maps.keys()),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "version": "formula_lab_v1",
            "error": str(exc),
        }
