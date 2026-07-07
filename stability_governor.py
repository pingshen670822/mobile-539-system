import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime


NUMBER_MIN = 1
NUMBER_MAX = 39


def _as_int_list(values):
    result = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if NUMBER_MIN <= number <= NUMBER_MAX:
            result.append(number)
    return result


def _load_json(text, fallback):
    try:
        return json.loads(text or "")
    except (TypeError, json.JSONDecodeError):
        return fallback


def _recent_settled_rows(db_path, limit=36):
    if not db_path:
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT actual_period, actual_date, actual_numbers_json,
                   strong_pack_hits_json, unlikely_pack_hits_json
            FROM predictions_539
            WHERE status='settled'
            ORDER BY actual_period DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def _candidate_map(analysis):
    candidates = analysis.get("official_candidates") or analysis.get("candidates") or []
    return {
        int(item.get("number")): item
        for item in candidates
        if isinstance(item, dict) and item.get("number") is not None
    }


def _score_map(analysis):
    return {
        number: float(item.get("score", 0.0) or 0.0)
        for number, item in _candidate_map(analysis).items()
    }


def _zone_label(number):
    if number <= 10:
        return "01-10"
    if number <= 20:
        return "11-20"
    if number <= 30:
        return "21-30"
    return "31-39"


def _sync_pack_score(pack, score_by_number):
    numbers = _as_int_list(pack.get("numbers", []))
    pack["numbers"] = numbers
    pack["zones"] = dict(Counter(_zone_label(number) for number in numbers))
    pack["tails"] = dict(Counter(str(number % 10) for number in numbers))
    if not numbers:
        pack["score_sum"] = 0.0
        pack["avg_score"] = 0.0
        return pack
    score_sum = sum(score_by_number.get(number, 0.0) for number in numbers)
    pack["score_sum"] = round(score_sum, 4)
    pack["avg_score"] = round(score_sum / len(numbers), 4)
    return pack


def single_lock_audit(rows):
    recent = []
    total_counts = Counter()
    miss_counts = Counter()
    hit_counts = Counter()
    consecutive_miss = defaultdict(int)
    for row in rows:
        strong_hits = _load_json(row.get("strong_pack_hits_json"), {})
        single = strong_hits.get("strong_single") or {}
        numbers = _as_int_list(single.get("numbers", []))
        if not numbers:
            continue
        number = numbers[0]
        hits = int(single.get("hits") or 0)
        total_counts[number] += 1
        hit_counts[number] += 1 if hits > 0 else 0
        miss_counts[number] += 1 if hits <= 0 else 0
        if hits <= 0:
            consecutive_miss[number] += 1
        else:
            consecutive_miss[number] = 0
        recent.append({
            "date": row.get("actual_date"),
            "number": number,
            "hits": hits,
            "passed": bool(single.get("passed")),
        })
    recent12 = recent[:12]
    recent8 = recent[:8]
    recent_counts = Counter(item["number"] for item in recent8)
    recent_misses = Counter(item["number"] for item in recent8 if not item["passed"])
    recent12_counts = Counter(item["number"] for item in recent12)
    recent12_misses = Counter(item["number"] for item in recent12 if not item["passed"])
    locked = {}
    soft_guarded = {}
    for number in set(total_counts) | set(recent_counts):
        total = total_counts[number]
        misses = miss_counts[number]
        hits = hit_counts[number]
        recent_repeat = recent_counts[number]
        recent_miss = recent_misses[number]
        recent12_repeat = recent12_counts[number]
        recent12_miss = recent12_misses[number]
        hit_rate = hits / total if total else 0.0
        reasons = []
        if recent_repeat >= 3 and recent_miss >= 2:
            reasons.append("\u8fd1\u516b\u671f\u7368\u96bb\u91cd\u8907\u4e14\u672a\u547d\u4e2d")
        if recent12_repeat >= 2 and recent12_miss >= 2 and hit_rate < 0.35:
            reasons.append("recent_12_single_repeat_miss")
        if misses >= 4 and hit_rate < 0.25:
            reasons.append("\u7d2f\u8a08\u7368\u96bb\u547d\u4e2d\u7387\u904e\u4f4e")
        if consecutive_miss[number] >= 2:
            reasons.append("\u7368\u96bb\u9023\u7e8c\u672a\u547d\u4e2d")
        if recent_miss >= 1 and (hits == 0 or recent12_miss >= 2):
            soft_guarded[number] = {
                "number": number,
                "total": total,
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hit_rate, 3),
                "recent8_count": recent_repeat,
                "recent8_misses": recent_miss,
                "recent12_count": recent12_repeat,
                "recent12_misses": recent12_miss,
                "reasons": ["\u8fd1\u671f\u7368\u96bb\u672a\u547d\u4e2d\uff0c\u672c\u671f\u5148\u964d\u6b0a\u6539\u7531\u5176\u4ed6\u5019\u9078\u7af6\u722d"],
            }
        if reasons:
            locked[number] = {
                "number": number,
                "total": total,
                "hits": hits,
                "misses": misses,
                "hit_rate": round(hit_rate, 3),
                "recent8_count": recent_repeat,
                "recent8_misses": recent_miss,
                "recent12_count": recent12_repeat,
                "recent12_misses": recent12_miss,
                "reasons": reasons,
            }
    return {
        "recent_single_rows": recent12,
        "locked_numbers": sorted(locked.values(), key=lambda item: (item["recent8_misses"], item["misses"], item["number"]), reverse=True),
        "soft_guard_numbers": sorted(soft_guarded.values(), key=lambda item: (item["recent8_misses"], item["misses"], item["number"]), reverse=True),
    }


def _choose_replacement(candidates, blocked_numbers, required_size, current_numbers=None):
    selected = []
    for number in _as_int_list(current_numbers or []):
        if number not in blocked_numbers and number not in selected:
            selected.append(number)
    for item in candidates:
        number = int(item.get("number"))
        if number in blocked_numbers or number in selected:
            continue
        selected.append(number)
        if len(selected) >= required_size:
            break
    return selected[:required_size]


def apply_candidate_guard(analysis, audit):
    locked_numbers = {int(item["number"]) for item in audit.get("locked_numbers", [])}
    soft_guard_numbers = {int(item["number"]) for item in audit.get("soft_guard_numbers", [])}
    guarded_numbers = locked_numbers | soft_guard_numbers
    if not guarded_numbers:
        return []

    actions = []

    def adjust_rows(rows):
        adjusted = []
        changed = []
        for row in rows or []:
            item = dict(row)
            try:
                number = int(item.get("number"))
            except (TypeError, ValueError):
                adjusted.append(item)
                continue
            if number in locked_numbers:
                penalty = 0.42
                reason = "\u7a69\u5b9a\u6cbb\u7406\u9396\u865f\u964d\u6b0a"
            elif number in soft_guard_numbers:
                penalty = 0.26
                reason = "\u7a69\u5b9a\u6cbb\u7406\u8edf\u6027\u964d\u6b0a"
            else:
                adjusted.append(item)
                continue
            before = float(item.get("score", 0.0) or 0.0)
            item["pre_stability_governor_score"] = round(before, 4)
            item["score"] = round(max(0.0, before - penalty), 4)
            reasons = [text for text in item.get("reasons", []) if text != reason]
            item["reasons"] = ([reason] + reasons)[:4]
            item["stability_governor_candidate_guard"] = {
                "status": "penalized",
                "penalty": penalty,
                "guard_type": "hard" if number in locked_numbers else "soft",
            }
            changed.append({
                "number": number,
                "before": round(before, 4),
                "after": item["score"],
                "guard_type": "hard" if number in locked_numbers else "soft",
            })
            adjusted.append(item)
        adjusted.sort(
            key=lambda item: (
                float(item.get("score", 0.0) or 0.0),
                int((item.get("cross_validation") or {}).get("passed_count") or 0),
                -int(item.get("number", 0) or 0),
            ),
            reverse=True,
        )
        for index, item in enumerate(adjusted, 1):
            item["rank"] = index
        return adjusted, changed

    for key in ["candidates", "official_candidates"]:
        rows = analysis.get(key)
        if rows:
            adjusted, changed = adjust_rows(rows)
            analysis[key] = adjusted
            if changed:
                actions.append({
                    "type": "candidate_guard",
                    "target": key,
                    "changed": changed[:12],
                })

    industrial = analysis.setdefault("industrial_engine", {})
    rows = industrial.get("candidates")
    if rows:
        adjusted, changed = adjust_rows(rows)
        industrial["candidates"] = adjusted
        if changed:
            actions.append({
                "type": "candidate_guard",
                "target": "industrial_candidates",
                "changed": changed[:12],
            })
    return actions


def apply_single_lock_guard(analysis, audit):
    locked_numbers = {int(item["number"]) for item in audit.get("locked_numbers", [])}
    soft_guard_numbers = {int(item["number"]) for item in audit.get("soft_guard_numbers", [])}
    guarded_numbers = locked_numbers | soft_guard_numbers
    candidates = analysis.get("official_candidates") or analysis.get("candidates") or []
    score_by_number = _score_map(analysis)
    packs = analysis.get("strong_prediction_packs") or {}
    actions = []
    if not guarded_numbers or not packs:
        return actions
    pack_specs = {
        "strong_single": 1,
        "two_hit_one": 2,
        "three_hit_one": 3,
        "five_hit_two": 5,
        "nine_hit_three": 9,
    }
    for key, size in pack_specs.items():
        pack = packs.get(key) or {}
        original = _as_int_list(pack.get("numbers", []))
        if not original or not (set(original) & guarded_numbers):
            continue
        replacement = _choose_replacement(candidates, guarded_numbers, size, original)
        removed = sorted(set(original) & guarded_numbers)
        pack["numbers"] = replacement
        pack["status"] = "watch"
        pack["official_release"] = False
        pack["release_note"] = "\u7a69\u5b9a\u6cbb\u7406\u5df2\u6821\u6b63\u8fd1\u671f\u9396\u865f\u8207\u9023\u7e8c\u5931\u6557\u7368\u96bb\uff0c\u6539\u7531\u5176\u4ed6\u5019\u9078\u7af6\u722d"
        pack["stability_governor_removed"] = removed
        pack["stability_governor_hard_removed"] = sorted(set(original) & locked_numbers)
        pack["stability_governor_soft_removed"] = sorted((set(original) & soft_guard_numbers) - locked_numbers)
        pack["stability_governor_replacement"] = replacement
        _sync_pack_score(pack, score_by_number)
        if key == "strong_single":
            decision = pack.get("super_single_decision") or {}
            if replacement:
                item = _candidate_map(analysis).get(replacement[0], {})
                cross = item.get("cross_validation") or {}
                passed_count = int(cross.get("passed_count") or 0)
                total_count = int(cross.get("total_count") or 0) or 1
                score = float(item.get("score", decision.get("super_single_score", 0.0)) or 0.0)
                decision["number"] = replacement[0]
                decision["decision_label"] = "\u7a69\u5b9a\u6cbb\u7406\u6539\u9078\u7368\u96bb"
                decision["risk_flags"] = sorted(set(decision.get("risk_flags", []) + ["\u8fd1\u671f\u7368\u96bb\u91cd\u8907\u5931\u6e96\u6821\u6b63"]))
                decision["risk_penalty"] = round(float(decision.get("risk_penalty", 0.0) or 0.0) + 0.35, 4)
                decision["selection_policy"] = "\u7a69\u5b9a\u6cbb\u7406\u512a\u5148\uff1a\u8fd1\u671f\u91cd\u8907\u5931\u6557\u7368\u96bb\u964d\u6b0a\u5f8c\u91cd\u65b0\u9078\u865f"
                decision["super_single_score"] = round(score, 4)
                decision["confidence_index"] = item.get("confidence_index", decision.get("confidence_index"))
                decision["model_probability_percent"] = item.get("model_probability_percent", decision.get("model_probability_percent"))
                decision["model_sources"] = item.get("model_sources", decision.get("model_sources", []))
                decision["passed_layer_count"] = passed_count
                decision["total_layer_count"] = total_count
                decision["layers"] = [
                    {"name": "candidate_score", "label": "\u5019\u9078\u7e3d\u5206", "score": round(score, 4), "threshold": 0.55, "passed": score >= 0.55},
                    {"name": "cross_validation", "label": "\u4ea4\u53c9\u9a57\u7b97", "score": round(passed_count / total_count, 4), "threshold": 0.34, "passed": passed_count / total_count >= 0.34},
                    {"name": "stability_reselection", "label": "\u7a69\u5b9a\u6cbb\u7406\u6539\u9078", "score": 1.0, "threshold": 1.0, "passed": True},
                ]
                decision["rank"] = item.get("rank", decision.get("rank"))
                decision["candidate"] = item or decision.get("candidate", {})
                decision["candidate_rankings"] = [
                    row for row in decision.get("candidate_rankings", [])
                    if int(row.get("number", -1)) not in removed
                ][:8]
                pack["selected_number_audit"] = [item] if item else []
            pack["super_single_decision"] = decision
        actions.append({
            "type": "single_lock_guard",
            "pack": key,
            "removed": removed,
            "hard_removed": sorted(set(original) & locked_numbers),
            "soft_removed": sorted((set(original) & soft_guard_numbers) - locked_numbers),
            "replacement": replacement,
        })
    industrial = analysis.setdefault("industrial_engine", {})
    if "strong_prediction_packs" in industrial:
        industrial["strong_prediction_packs"] = packs
    analysis["strong_prediction_packs"] = packs
    return actions


def _avoid_threshold(size):
    if size == 5:
        return {"max_edge": -0.08, "min_zero_rate": 0.52}
    if size == 10:
        return {"max_edge": -0.12, "min_zero_rate": 0.22}
    return {"max_edge": -0.18, "min_zero_rate": 0.10}


def apply_unlikely_gate(analysis):
    industrial = analysis.setdefault("industrial_engine", {})
    unlikely = industrial.get("unlikely_number_analysis") or {}
    backtest = industrial.get("unlikely_backtest") or {}
    backtest_packs = backtest.get("packs") or {}
    packs = unlikely.get("avoid_packs") or {}
    inversion_guard = unlikely.get("inversion_guard") or {}
    inversion_packs = inversion_guard.get("blocked_packs") or {}
    global_reverse_hit_numbers = set(_as_int_list(inversion_guard.get("recent_reverse_hit_numbers", [])))
    actions = []
    released_any = False
    for key, pack in list(packs.items()):
        reverse_guard = inversion_packs.get(key) or {}
        reverse_blocked = bool(reverse_guard.get("blocked"))
        pack_reverse_hit_numbers = set(global_reverse_hit_numbers)
        for item in reverse_guard.get("hit_numbers", []) or []:
            try:
                pack_reverse_hit_numbers.add(int(item.get("number")))
            except (TypeError, ValueError):
                continue
        stat = backtest_packs.get(key) or {}
        size = int(stat.get("avoid_size") or len(pack.get("numbers") or []))
        edge = float(stat.get("edge_vs_random", 0.0) or 0.0)
        zero_rate = float(stat.get("zero_hit_rate", 0.0) or 0.0)
        threshold = _avoid_threshold(size)
        legacy_passed = bool(stat.get("rounds", 0) >= 90 and edge <= threshold["max_edge"] and zero_rate >= threshold["min_zero_rate"])
        formula_edge = float(pack.get("formula_lab_edge", 0.0) or 0.0)
        formula_status = str(pack.get("formula_lab_status") or "")
        original_numbers = _as_int_list(pack.get("numbers", []))
        formula_passed = bool(original_numbers and formula_status == "released" and formula_edge >= 0.02)
        passed = bool(original_numbers and not reverse_blocked and (legacy_passed or formula_passed))
        diagnostic_numbers = (
            original_numbers
            or _as_int_list(pack.get("diagnostic_numbers", []))
            or _as_int_list(pack.get("rejected_candidates", []))
        )
        removed_reverse_diagnostics = [number for number in diagnostic_numbers if number in pack_reverse_hit_numbers]
        diagnostic_numbers = [number for number in diagnostic_numbers if number not in pack_reverse_hit_numbers]
        pack["backtest_gate"] = {
            "status": "passed" if passed else "failed",
            "gate_model": "formula_lab_inverse_consensus" if formula_passed and not legacy_passed else "legacy_inverse_signal",
            "edge_vs_random": round(edge, 4),
            "required_edge_at_most": threshold["max_edge"],
            "formula_avoid_edge": round(formula_edge, 4),
            "required_formula_avoid_edge_at_least": 0.02,
            "zero_hit_rate": round(zero_rate, 3),
            "required_zero_hit_rate": threshold["min_zero_rate"],
            "rounds": stat.get("rounds", 0),
            "reverse_hit_guard": reverse_guard,
        }
        if passed:
            original_numbers = [number for number in original_numbers if number not in pack_reverse_hit_numbers]
            if len(original_numbers) != len(_as_int_list(pack.get("numbers", []))):
                passed = False
                pack["numbers"] = []
                pack["status"] = "\u53cd\u5411\u547d\u4e2d\u865f\u6df7\u5165\u5df2\u6263\u7559"
                pack["warning"] = "\u4f4e\u6a5f\u7387\u5305\u6df7\u5165\u8fd1\u671f\u53cd\u5411\u547d\u4e2d\u865f\uff0c\u5df2\u5f37\u5236\u6263\u7559\u91cd\u65b0\u6821\u6b63"
                pack["reverse_hit_removed_diagnostics"] = removed_reverse_diagnostics
            else:
                pack["numbers"] = original_numbers
        if passed:
            released_any = True
            confidence = max(55.0, min(90.0, 55.0 + max(abs(edge), formula_edge) * 180 + zero_rate * 18))
            pack["confidence_index"] = round(confidence, 1)
            pack["confidence_label"] = "\u56de\u6e2c\u901a\u904e"
            pack["status"] = "\u56de\u6e2c\u901a\u904e\u767c\u5e03"
            pack["warning"] = "\u4f4e\u6a5f\u7387\u50c5\u4ee3\u8868\u56de\u6e2c\u66ab\u907f\u512a\u52e2\uff0c\u4e0d\u4ee3\u8868\u4fdd\u8b49\u4e0d\u958b"
        else:
            pack["diagnostic_candidates"] = diagnostic_numbers
            pack["withheld_numbers"] = diagnostic_numbers
            pack["reverse_hit_removed_diagnostics"] = removed_reverse_diagnostics
            pack["numbers"] = []
            pack["confidence_index"] = 0.0
            pack["confidence_label"] = "\u672a\u767c\u5e03"
            if reverse_blocked:
                pack["status"] = "\u8fd1\u671f\u53cd\u5411\u547d\u4e2d\u504f\u9ad8\u5df2\u6263\u7559"
                pack["warning"] = "\u6b64\u4f4e\u6a5f\u7387\u5305\u8fd1\u671f\u8aa4\u4e2d\u504f\u9ad8\uff0c\u7981\u6b62\u7576\u6210\u6b63\u5f0f\u4e0d\u4e2d\u865f\u78bc\uff0c\u6539\u5217\u53cd\u5411\u547d\u4e2d\u8b66\u8a0a"
            else:
                pack["status"] = "\u56de\u6e2c\u4e0d\u5408\u683c\u672a\u767c\u5e03"
                pack["warning"] = "\u8fd1\u7aef\u56de\u6e2c\u672a\u660e\u986f\u52dd\u904e\u96a8\u6a5f\uff0c\u5019\u9078\u4fdd\u7559\u5728\u8a3a\u65b7\u6b04\uff0c\u4e0d\u5217\u70ba\u6b63\u5f0f\u4f4e\u6a5f\u7387\u66ab\u907f\u865f\u78bc"
            actions.append({
                "type": "unlikely_gate",
                "pack": key,
                "withheld_numbers": diagnostic_numbers,
                "reverse_hit_removed_diagnostics": removed_reverse_diagnostics,
                "edge_vs_random": round(edge, 4),
                "zero_hit_rate": round(zero_rate, 3),
                "reverse_hit_blocked": reverse_blocked,
            })
    if not released_any:
        unlikely["diagnostic_numbers"] = unlikely.get("numbers", [])
        unlikely["numbers"] = []
        unlikely["warning"] = "\u4f4e\u6a5f\u7387\u6a21\u578b\u8fd1\u671f\u672a\u901a\u904e\u56de\u6e2c\u6216\u53cd\u5411\u547d\u4e2d\u6aa2\u67e5\uff0c\u672c\u671f\u4e0d\u767c\u5e03\u6b63\u5f0f\u66ab\u907f\u865f\u78bc\uff0c\u8a3a\u65b7\u5019\u9078\u4ecd\u5b8c\u6574\u4fdd\u7559"
    unlikely["avoid_packs"] = packs
    unlikely["release_status"] = "released" if released_any else "withheld_by_backtest_gate"
    industrial["unlikely_number_analysis"] = unlikely
    return actions


def sync_decisive_decision_from_packs(analysis):
    industrial = analysis.setdefault("industrial_engine", {})
    packs = analysis.get("strong_prediction_packs") or industrial.get("strong_prediction_packs") or {}
    decision = industrial.get("decisive_battle_decision") or {}
    mapping = {
        "strong_single": ["primary_single"],
        "two_hit_one": ["primary_two"],
        "three_hit_one": ["primary_three"],
        "five_hit_two": ["primary_five", "five_hit_two"],
        "nine_hit_three": ["primary_nine", "nine_hit_three", "attack_core_top9"],
    }
    changed = []
    for pack_key, decision_keys in mapping.items():
        numbers = _as_int_list((packs.get(pack_key) or {}).get("numbers", []))
        if not numbers:
            continue
        for decision_key in decision_keys:
            if decision.get(decision_key) != numbers:
                decision[decision_key] = numbers
                changed.append(decision_key)
    industrial["decisive_battle_decision"] = decision
    return [{
        "type": "decision_cache_sync",
        "changed_fields": sorted(set(changed)),
    }] if changed else []


def apply_stability_governor(db_path, analysis):
    rows = _recent_settled_rows(db_path)
    single_audit = single_lock_audit(rows)
    actions = []
    actions.extend(apply_candidate_guard(analysis, single_audit))
    actions.extend(apply_single_lock_guard(analysis, single_audit))
    actions.extend(sync_decisive_decision_from_packs(analysis))
    actions.extend(apply_unlikely_gate(analysis))
    industrial = analysis.setdefault("industrial_engine", {})
    industrial["stability_governor"] = {
        "status": "corrected" if actions else "checked",
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "policy": "\u4f4e\u6a5f\u7387\u5fc5\u9808\u56de\u6e2c\u660e\u986f\u52dd\u904e\u96a8\u6a5f\u624d\u767c\u5e03\uff1b\u7368\u96bb\u82e5\u8fd1\u671f\u91cd\u8907\u5931\u6557\u5247\u964d\u6b0a\u6539\u9078\uff0c\u8a3a\u65b7\u8cc7\u6599\u5b8c\u6574\u4fdd\u7559",
        "single_lock_audit": single_audit,
        "actions": actions,
    }
    return analysis
