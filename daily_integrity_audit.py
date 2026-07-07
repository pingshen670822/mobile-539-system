import json
import sqlite3
import subprocess
import base64
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "539.sqlite"
ANALYSIS_JSON = REPORT_DIR / "latest_analysis.json"
HEALTH_JSON = REPORT_DIR / "health_status.json"
HISTORY_JSON = REPORT_DIR / "prediction_history.json"
BATTLE_HTML = REPORT_DIR / "539\u6700\u65b0\u5f37\u5316\u6230\u5831.html"
LATEST_BATTLE_HTML = REPORT_DIR / "latest_battle_report.html"
LOW_PROBABILITY_HTML = REPORT_DIR / "539\u4f4e\u6a5f\u7387\u7cbe\u6e96\u66ab\u907f.html"
LOW_PROBABILITY_DAILY_JSON = REPORT_DIR / "\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304.json"
LOW_PROBABILITY_DAILY_HTML = REPORT_DIR / "539\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304.html"
LOW_PROBABILITY_MONTHLY_JSON = REPORT_DIR / "\u4f4e\u6a5f\u7387\u6bcf\u6708\u7e3d\u7d00\u9304\u5206\u6790.json"
LOW_PROBABILITY_MONTHLY_HTML = REPORT_DIR / "539\u4f4e\u6a5f\u7387\u6bcf\u6708\u7e3d\u7d00\u9304\u5206\u6790.html"
LOW_PROBABILITY_MONTHLY_DAILY_HTML = REPORT_DIR / "539\u4f4e\u6a5f\u7387\u6bcf\u6708\u6bcf\u65e5\u7e3d\u6574\u7406.html"
MONTHLY_SUMMARY_HTML = REPORT_DIR / "539\u6bcf\u6708\u9810\u6e2c\u7e3d\u6574\u7406.html"
AUDIT_JSON = REPORT_DIR / "daily_integrity_audit.json"
AUDIT_MD = REPORT_DIR / "daily_integrity_audit.md"
SITE_DIR = BASE_DIR / "site"
SITE_ANALYSIS_JSON = SITE_DIR / "latest_analysis.json"
SITE_VERSION_JSON = SITE_DIR / "version.json"
MOBILE_SYNC_JSON = REPORT_DIR / "mobile_sync_verification.json"
CLOUD_STATUS_JSON = BASE_DIR / "\u624b\u6a5f\u96f2\u7aef\u767c\u5e03\u72c0\u614b.json"
SCHEDULE_STATUS_JSON = REPORT_DIR / "daily_auto_task_status.json"


def expected_latest_draw_date(now=None):
    now = now or datetime.now()
    candidate = now.date()
    if now.time() < clock_time(21, 0):
        candidate -= timedelta(days=1)
    while candidate.weekday() == 6:
        candidate -= timedelta(days=1)
    return candidate.isoformat()


def load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def add_check(checks, name, passed, detail):
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def latest_draw_signature(draw):
    return {
        "period": draw.get("period"),
        "draw_date": draw.get("draw_date"),
        "numbers": [int(n) for n in draw.get("numbers", [])],
    }


def prediction_signature(analysis):
    packs = ((analysis.get("industrial_engine") or {}).get("strong_prediction_packs") or
             analysis.get("strong_prediction_packs") or {})
    pack_keys = [
        "strong_single",
        "two_hit_one",
        "three_hit_one",
        "five_hit_two",
        "nine_hit_three",
    ]
    return {
        "top10": [
            int(item.get("number"))
            for item in (analysis.get("candidates") or [])[:10]
            if item.get("number") is not None
        ],
        "packs": {
            key: [int(number) for number in ((packs.get(key) or {}).get("numbers") or [])]
            for key in pack_keys
        },
    }


def number_text(numbers):
    return " ".join(f"{int(number):02d}" for number in (numbers or []))


def html_signature(prediction):
    packs = prediction.get("packs") or {}
    return {
        "strong_single": number_text(packs.get("strong_single") or []),
        "nine_hit_three": number_text(packs.get("nine_hit_three") or []),
    }


def html_has_current_prediction(html, signature):
    return bool(
        signature.get("strong_single")
        and signature["strong_single"] in html
        and signature.get("nine_hit_three")
        and signature["nine_hit_three"] in html
    )


def html_has_stale_core(html):
    stale_cores = [
        "36 13 30 34 03 26 32 05 24",
        "36 13 30 34 03 26 32 05",
    ]
    return any(core in html for core in stale_cores)


def scheduled_task_exists(task_name):
    try:
        escaped = task_name.replace("'", "''")
        command = f"Get-ScheduledTask -TaskName '{escaped}' -ErrorAction Stop | Select-Object -ExpandProperty TaskName"
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as exc:
        return False, str(exc)


def text_from_codes(codes):
    return "".join(chr(code) for code in codes)


def build_audit():
    checks = []
    if not DB_PATH.exists():
        add_check(checks, "database_exists", False, str(DB_PATH))
        return finalize(checks)

    analysis = load_json(ANALYSIS_JSON)
    restored_mode = analysis.get("prediction_mode") == "restored_20260604_hit4_v31"
    health = load_json(HEALTH_JSON)
    history = load_json(HISTORY_JSON)
    site_analysis = load_json(SITE_ANALYSIS_JSON)
    site_version = load_json(SITE_VERSION_JSON)
    mobile_sync = load_json(MOBILE_SYNC_JSON)
    cloud_status = load_json(CLOUD_STATUS_JSON)
    schedule_status = load_json(SCHEDULE_STATUS_JSON)
    battle_text = BATTLE_HTML.read_text(encoding="utf-8") if BATTLE_HTML.exists() else ""
    latest_battle_text = LATEST_BATTLE_HTML.read_text(encoding="utf-8") if LATEST_BATTLE_HTML.exists() else ""
    low_probability_text = LOW_PROBABILITY_HTML.read_text(encoding="utf-8") if LOW_PROBABILITY_HTML.exists() else ""
    low_daily = load_json(LOW_PROBABILITY_DAILY_JSON)
    low_monthly = load_json(LOW_PROBABILITY_MONTHLY_JSON)
    low_daily_text = LOW_PROBABILITY_DAILY_HTML.read_text(encoding="utf-8") if LOW_PROBABILITY_DAILY_HTML.exists() else ""
    low_monthly_text = LOW_PROBABILITY_MONTHLY_HTML.read_text(encoding="utf-8") if LOW_PROBABILITY_MONTHLY_HTML.exists() else ""
    low_monthly_daily_text = LOW_PROBABILITY_MONTHLY_DAILY_HTML.read_text(encoding="utf-8") if LOW_PROBABILITY_MONTHLY_DAILY_HTML.exists() else ""
    monthly_summary_text = MONTHLY_SUMMARY_HTML.read_text(encoding="utf-8") if MONTHLY_SUMMARY_HTML.exists() else ""
    site_text = (SITE_DIR / "index.html").read_text(encoding="utf-8") if (SITE_DIR / "index.html").exists() else ""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        stats = conn.execute(
            "SELECT COUNT(*) count, MIN(period) min_period, MAX(period) max_period, MIN(draw_date) min_date, MAX(draw_date) max_date FROM draws_539"
        ).fetchone()
        latest = conn.execute(
            "SELECT period, draw_date, n1, n2, n3, n4, n5 FROM draws_539 ORDER BY period DESC LIMIT 1"
        ).fetchone()
        duplicate_periods = conn.execute(
            "SELECT period, COUNT(*) count FROM draws_539 GROUP BY period HAVING COUNT(*) > 1"
        ).fetchall()
        duplicate_dates = conn.execute(
            "SELECT draw_date, COUNT(*) count FROM draws_539 GROUP BY draw_date HAVING COUNT(*) > 1"
        ).fetchall()
        invalid_rows = conn.execute(
            """
            SELECT period FROM draws_539
            WHERE n1 NOT BETWEEN 1 AND 39 OR n2 NOT BETWEEN 1 AND 39 OR n3 NOT BETWEEN 1 AND 39
               OR n4 NOT BETWEEN 1 AND 39 OR n5 NOT BETWEEN 1 AND 39
               OR n1 IN (n2,n3,n4,n5) OR n2 IN (n3,n4,n5) OR n3 IN (n4,n5) OR n4=n5
            """
        ).fetchall()
        stale_pending = conn.execute(
            """
            SELECT target_period, based_on_period
            FROM predictions_539
            WHERE status='pending' AND target_period <= ?
            """,
            (latest["period"],),
        ).fetchall()
        recent_settled = conn.execute(
            """
            SELECT target_period, status, actual_period, top5_hits, top10_hits, top15_hits
            FROM predictions_539
            WHERE target_period BETWEEN ? AND ?
            ORDER BY target_period
            """,
            (latest["period"] - 5, latest["period"]),
        ).fetchall()
        missing_recent_predictions = conn.execute(
            """
            SELECT d.period, d.draw_date
            FROM draws_539 d
            LEFT JOIN predictions_539 p ON p.target_period=d.period
            WHERE d.period BETWEEN ? AND ?
              AND p.target_period IS NULL
            ORDER BY d.period
            """,
            (latest["period"] - 5, latest["period"]),
        ).fetchall()
        latest_settlement = conn.execute(
            """
            SELECT target_period, status, actual_period, actual_date, top5_hits, top10_hits, top15_hits
            FROM predictions_539
            WHERE target_period=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (latest["period"],),
        ).fetchone()

    expected_date = expected_latest_draw_date()
    add_check(checks, "draw_count_minimum", stats["count"] >= 5800, dict(stats))
    add_check(checks, "latest_date_fresh", latest["draw_date"] >= expected_date, {"latest": latest["draw_date"], "expected": expected_date})
    add_check(checks, "no_duplicate_periods", not duplicate_periods, [dict(row) for row in duplicate_periods])
    add_check(checks, "no_duplicate_dates", not duplicate_dates, [dict(row) for row in duplicate_dates])
    add_check(checks, "no_invalid_draw_rows", not invalid_rows, [dict(row) for row in invalid_rows])
    add_check(checks, "no_stale_pending_predictions", not stale_pending, [dict(row) for row in stale_pending])
    add_check(checks, "recent_predictions_settled", all(row["status"] == "settled" for row in recent_settled), [dict(row) for row in recent_settled])
    add_check(checks, "no_missing_recent_prediction_records", not missing_recent_predictions, [dict(row) for row in missing_recent_predictions])
    add_check(checks, "latest_draw_has_settled_prediction_record", bool(latest_settlement and latest_settlement["status"] == "settled"), dict(latest_settlement) if latest_settlement else {
        "missing_target_period": latest["period"],
        "missing_draw_date": latest["draw_date"],
    })

    analysis_period = analysis.get("latest_draw", {}).get("period")
    analysis_draw = latest_draw_signature(analysis.get("latest_draw", {}))
    site_draw = latest_draw_signature(site_analysis.get("latest_draw", {}))
    analysis_prediction = prediction_signature(analysis)
    site_prediction = prediction_signature(site_analysis)
    html_expected = html_signature(analysis_prediction)
    industrial = analysis.get("industrial_engine") or {}
    unlikely = industrial.get("unlikely_number_analysis") or {}
    reverse_hit_numbers = {
        int(number)
        for number in ((unlikely.get("inversion_guard") or {}).get("recent_reverse_hit_numbers") or [])
        if number is not None
    }
    reverse_model_candidates = [
        item for item in (analysis.get("candidates") or [])[:15]
        if "low_probability_reverse_hit_recovery" in ((item.get("feature_scores") or {}))
    ]
    site_reverse_model_candidates = [
        item for item in (site_analysis.get("candidates") or [])[:15]
        if "low_probability_reverse_hit_recovery" in ((item.get("feature_scores") or {}))
    ]
    low_diagnostic_overlap = {}
    for key, pack in ((unlikely.get("avoid_packs") or {}).items()):
        diagnostic_numbers = (
            pack.get("diagnostic_candidates")
            or pack.get("withheld_numbers")
            or pack.get("diagnostic_numbers")
            or []
        )
        overlap = sorted(set(int(number) for number in diagnostic_numbers if number is not None) & reverse_hit_numbers)
        if overlap:
            low_diagnostic_overlap[key] = overlap
    add_check(checks, "analysis_matches_database", str(analysis_period) == str(latest["period"]), {"analysis": analysis_period, "database": latest["period"]})
    add_check(checks, "health_sync_passed", health.get("analysis_sync", {}).get("status") == "synced", health.get("analysis_sync", {}))
    add_check(checks, "history_has_latest_pending_or_settled", any(
        item.get("target_period") == latest["period"] + 1 for item in history.get("periods", [])
    ), {"expected_target": latest["period"] + 1})
    add_check(checks, "battle_report_mentions_latest", str(latest["period"]) in battle_text and latest["draw_date"] in battle_text, {
        "period": latest["period"],
        "draw_date": latest["draw_date"],
    })
    add_check(checks, "battle_report_has_settlement_rows", "\u5df2\u7d50\u7b97" in battle_text and "\u5f85\u7d50\u7b97" in battle_text, "settled and pending labels")
    add_check(checks, "battle_report_is_compact_precision_report", (
        "539 \u7cbe\u7b97\u9810\u6e2c\u6230\u5831" in battle_text
        and "\u5168\u6b77\u53f2\u8cc7\u6599" in battle_text
        and "\u53ea\u986f\u793a\u5b8c\u6210\u904b\u7b97\u5f8c\u7684\u7cbe\u6e96\u8cc7\u8a0a" in battle_text
    ), "compact precision report labels")
    add_check(checks, "battle_report_has_explicit_dates", "\u6700\u65b0\u958b\u734e" in battle_text and "\u9810\u6e2c\u76ee\u6a19" in battle_text and "\u4e0a\u671f\u9810\u6e2c\u6aa2\u8a0e" in battle_text, "date labels")
    add_check(checks, "battle_report_has_low_probability_link", "539\u4f4e\u6a5f\u7387\u7cbe\u6e96\u66ab\u907f.html" in battle_text, "low probability page link")
    add_check(checks, "battle_report_has_super_single_section", "\u6700\u5f37\u7368\u96bb1\u4e2d1" in battle_text and "\u7368\u96bb\u7e3d\u5206" in battle_text, "super single section")
    add_check(checks, "battle_report_has_no_mojibake_question_marks", "???" not in battle_text, "battle report must not contain mojibake question marks")
    add_check(checks, "low_probability_page_exists", LOW_PROBABILITY_HTML.exists(), str(LOW_PROBABILITY_HTML))
    add_check(checks, "low_probability_page_has_no_mojibake_question_marks", "???" not in low_probability_text, "low probability page must not contain mojibake question marks")
    add_check(checks, "low_probability_page_has_required_sections", "\u4f4e\u6a5f\u7387\u7cbe\u6e96\u66ab\u907f" in low_probability_text and "5\u4e0d\u4e2d" in low_probability_text and "15\u4e0d\u4e2d" in low_probability_text, "low probability section labels")
    add_check(checks, "low_probability_daily_record_exists", LOW_PROBABILITY_DAILY_JSON.exists() and LOW_PROBABILITY_DAILY_HTML.exists(), {
        "json": str(LOW_PROBABILITY_DAILY_JSON),
        "html": str(LOW_PROBABILITY_DAILY_HTML),
    })
    add_check(checks, "low_probability_daily_record_has_rows", bool(low_daily.get("records")), {
        "record_count": len(low_daily.get("records", [])) if isinstance(low_daily.get("records"), list) else 0,
    })
    add_check(checks, "low_probability_monthly_record_exists", LOW_PROBABILITY_MONTHLY_JSON.exists() and LOW_PROBABILITY_MONTHLY_HTML.exists(), {
        "json": str(LOW_PROBABILITY_MONTHLY_JSON),
        "html": str(LOW_PROBABILITY_MONTHLY_HTML),
    })
    add_check(checks, "low_probability_monthly_daily_summary_exists", LOW_PROBABILITY_MONTHLY_DAILY_HTML.exists(), str(LOW_PROBABILITY_MONTHLY_DAILY_HTML))
    add_check(checks, "low_probability_monthly_record_has_analysis", bool(low_monthly.get("months")), {
        "month_count": len(low_monthly.get("months", [])) if isinstance(low_monthly.get("months"), list) else 0,
    })
    add_check(checks, "battle_report_links_low_probability_daily_and_monthly", (
        "539\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304.html" in battle_text
        and "539\u4f4e\u6a5f\u7387\u6bcf\u6708\u6bcf\u65e5\u7e3d\u6574\u7406.html" in battle_text
    ), "main report must link low probability daily and monthly daily summary")
    add_check(checks, "battle_report_embeds_low_probability_daily_review", (
        "\u4f4e\u6a5f\u7387\u6bcf\u65e5\u6aa2\u8a0e\u7d00\u9304" in battle_text
        and "\u5be6\u969b\u958b\u734e" in battle_text
        and "\u9810\u6e2c\u547d\u4e2d" in battle_text
        and "\u4f4e\u6a5f\u7387\u8aa4\u4e2d" in battle_text
        and "\u4f4e\u6a5f\u8aa4\u4e2d\u865f\u78bc" in battle_text
        and "\u9054\u6a19\u72c0\u614b" in battle_text
    ), "main report must directly embed low probability daily review table")
    add_check(checks, "battle_report_has_low_probability_reverse_hit_guard", (
        "\u4f4e\u6a5f\u7387\u53cd\u5411\u547d\u4e2d\u8b66\u8a0a" in battle_text
        and "\u8fd1\u671f\u4f4e\u6a5f\u7387\u932f\u6bba\u865f" in battle_text
        and "\u66fe\u88ab\u4f4e\u6a5f\u7387\u932f\u6bba\u5f8c\u958b\u51fa\u7684\u865f\u78bc" in battle_text
    ), "main report must show low probability reverse-hit guard")
    add_check(checks, "local_mobile_has_low_probability_reverse_hit_guard", (
        "\u4f4e\u6a5f\u7387\u53cd\u5411\u547d\u4e2d\u8b66\u8a0a" in site_text
        and "\u8fd1\u671f\u4f4e\u6a5f\u7387\u932f\u6bba\u865f" in site_text
    ), "local mobile report must show low probability reverse-hit guard")
    add_check(checks, "analysis_has_low_probability_reverse_hit_recovery_model", bool(reverse_model_candidates), {
        "checked_top": 15,
        "model": "low_probability_reverse_hit_recovery",
    })
    add_check(checks, "local_mobile_has_low_probability_reverse_hit_recovery_model", bool(site_reverse_model_candidates), {
        "checked_top": 15,
        "model": "low_probability_reverse_hit_recovery",
    })
    add_check(checks, "low_probability_diagnostics_exclude_reverse_hit_numbers", not low_diagnostic_overlap, {
        "reverse_hit_numbers": sorted(reverse_hit_numbers),
        "overlap": low_diagnostic_overlap,
    })
    add_check(checks, "monthly_review_has_daily_actual_hits_and_low_hits", (
        "\u6bcf\u4e00\u5929\u5be6\u6230\u6aa2\u8a0e" in monthly_summary_text
        and "\u5be6\u969b\u958b\u734e" in monthly_summary_text
        and "\u524d\u5341\u547d\u4e2d\u865f" in monthly_summary_text
        and "\u4f4e\u6a5f\u7387\u8aa4\u4e2d" in monthly_summary_text
    ), "monthly review must show daily actual draw, hits, and low probability hits")
    add_check(checks, "low_probability_monthly_has_daily_actual_hits_and_low_hits", (
        "\u6bcf\u4e00\u5929\u5be6\u6230\u660e\u7d30" in low_monthly_text
        and "\u5be6\u969b\u958b\u734e" in low_monthly_text
        and "\u9810\u6e2c\u547d\u4e2d" in low_monthly_text
        and "\u4f4e\u6a5f\u7387\u7d50\u679c" in low_monthly_text
    ), "low probability monthly page must show daily actual draw, hits, and low probability hits")
    add_check(checks, "low_probability_monthly_daily_summary_has_daily_actual_hits_and_low_hits", (
        "\u6bcf\u4e00\u5929\u5be6\u6230\u660e\u7d30" in low_monthly_daily_text
        and "\u5be6\u969b\u958b\u734e" in low_monthly_daily_text
        and "\u9810\u6e2c\u547d\u4e2d" in low_monthly_daily_text
        and "\u4f4e\u6a5f\u7387\u7d50\u679c" in low_monthly_daily_text
    ), "low probability monthly daily summary must show daily actual draw, hits, and low probability hits")
    add_check(checks, "low_probability_daily_and_monthly_pages_have_no_mojibake", "???" not in low_daily_text and "???" not in low_monthly_text and "???" not in low_monthly_daily_text, "low probability daily/monthly pages must not contain mojibake question marks")
    add_check(checks, "local_mobile_low_probability_pages_exist", (
        (SITE_DIR / "low-probability-daily.html").exists()
        and (SITE_DIR / "low-probability-monthly.html").exists()
        and (SITE_DIR / "low-probability-monthly-daily-summary.html").exists()
    ), str(SITE_DIR))
    add_check(checks, "local_mobile_site_exists", (SITE_DIR / "index.html").exists() and SITE_ANALYSIS_JSON.exists() and SITE_VERSION_JSON.exists(), str(SITE_DIR))
    add_check(checks, "local_mobile_draw_matches_computer", site_draw == analysis_draw, {"computer": analysis_draw, "mobile": site_draw})
    add_check(checks, "local_mobile_prediction_matches_computer", site_prediction == analysis_prediction, {"computer": analysis_prediction, "mobile": site_prediction})
    add_check(checks, "local_mobile_version_mentions_latest_period", str(site_version.get("latest_period")) == str(latest["period"]), site_version)
    add_check(checks, "latest_battle_report_html_matches_current_prediction", html_has_current_prediction(latest_battle_text, html_expected), html_expected)
    add_check(checks, "main_battle_report_html_matches_current_prediction", html_has_current_prediction(battle_text, html_expected), html_expected)
    add_check(checks, "local_mobile_html_matches_current_prediction", html_has_current_prediction(site_text, html_expected), html_expected)
    add_check(checks, "latest_battle_report_has_no_stale_core", not html_has_stale_core(latest_battle_text), "stale old core must not remain")
    add_check(checks, "main_battle_report_has_no_stale_core", not html_has_stale_core(battle_text), "stale old core must not remain")
    add_check(checks, "local_mobile_html_has_no_stale_core", not html_has_stale_core(site_text), "stale old core must not remain")
    add_check(checks, "mobile_cloud_publish_status_published", cloud_status.get("status") == "published", cloud_status)
    add_check(checks, "mobile_cloud_sync_verified", mobile_sync.get("status") == "ok", mobile_sync)
    daily_task_names = [
        "TW539 " + text_from_codes([0x6BCF, 0x65E5, 0x958B, 0x734E, 0x5F8C, 0x5168, 0x81EA, 0x52D5, 0x66F4, 0x65B0]),
        "TW539 " + text_from_codes([0x6BCF, 0x65E5, 0x51CC, 0x6668, 0x5B8C, 0x6574, 0x6AA2, 0x6E2C]),
    ]
    sync_monitor_task_names = [
        "TW539 " + text_from_codes([0x6BCF, 0x0033, 0x5C0F, 0x6642, 0x6230, 0x5831, 0x624B, 0x6A5F, 0x540C, 0x6B65, 0x6AA2, 0x6E2C]),
    ]
    daily_status_rows = schedule_status.get("daily_tasks", []) if isinstance(schedule_status, dict) else []
    sync_monitor_rows = schedule_status.get("sync_monitor_tasks", []) if isinstance(schedule_status, dict) else []
    daily_rows_by_name = {str(row.get("task")): row for row in daily_status_rows if isinstance(row, dict)}
    sync_rows_by_name = {str(row.get("task")): row for row in sync_monitor_rows if isinstance(row, dict)}
    daily_rows_ok = all(
        daily_rows_by_name.get(task_name, {}).get("passed") is True
        and daily_rows_by_name.get(task_name, {}).get("exists") is True
        for task_name in daily_task_names
    )
    sync_monitor_ok = all(
        sync_rows_by_name.get(task_name, {}).get("passed") is True
        and sync_rows_by_name.get(task_name, {}).get("exists") is True
        for task_name in sync_monitor_task_names
    )
    add_check(checks, "daily_auto_schedule_status_passed", schedule_status.get("status") == "passed", schedule_status)
    add_check(checks, "daily_auto_schedule_has_two_tasks", daily_rows_ok, daily_status_rows)
    add_check(checks, "three_hour_sync_monitor_task_exists", sync_monitor_ok, sync_monitor_rows)
    add_check(checks, "startup_auto_tasks_removed", not schedule_status.get("startup_tasks_failed"), schedule_status.get("startup_tasks_failed", []))
    return finalize(checks, latest=dict(latest), expected_date=expected_date)


def finalize(checks, **extra):
    failed = [item for item in checks if not item["passed"]]
    status = "failed" if failed else "passed"
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "failed_count": len(failed),
        "checks": checks,
        **extra,
    }


def save_audit(audit):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 539 Daily Integrity Audit",
        "",
        f"- generated_at: {audit['generated_at']}",
        f"- status: {audit['status']}",
        f"- failed_count: {audit['failed_count']}",
        "",
    ]
    for item in audit["checks"]:
        mark = "PASS" if item["passed"] else "FAIL"
        lines.append(f"- {mark}: {item['name']} / {item['detail']}")
    AUDIT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    audit = build_audit()
    save_audit(audit)
    print(f"daily integrity audit: {audit['status']} ({audit['failed_count']} failed)")
    if audit["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
