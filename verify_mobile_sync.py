import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
STATUS_PATH = REPORTS / "mobile_sync_verification.json"
CLOUD_STATUS_PATH = ROOT / "\u624b\u6a5f\u96f2\u7aef\u767c\u5e03\u72c0\u614b.json"
MOBILE_REPORT_STATUS_PATH = ROOT / "\u624b\u6a5f\u6230\u5831\u66f4\u65b0\u72c0\u614b.json"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def fetch_json(url, timeout=30):
    request = Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url, timeout=30):
    request = Request(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


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
        "generated_at": analysis.get("generated_at"),
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


def mobile_base_url(cloud_url):
    if not cloud_url:
        return "https://pingshen670924-dotcom.github.io/mobile-539-system"
    parsed = urlsplit(cloud_url)
    path = parsed.path or "/mobile-539-system/"
    marker = "/clear-cache.html"
    if marker in path:
        path = path.split(marker)[0]
    path = path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def write_mobile_report_status(sync_status):
    local_draw = sync_status.get("local_latest_draw") or {}
    remote_version = sync_status.get("remote_version") or {}
    ok = sync_status.get("status") == "ok"
    payload = {
        "status": "published" if ok else "sync_failed",
        "version": sync_status.get("local_version"),
        "built_at": remote_version.get("mobile_built_at"),
        "verified_at": sync_status.get("checked_at"),
        "latest_period": local_draw.get("period"),
        "latest_draw_date": local_draw.get("draw_date"),
        "site_url": sync_status.get("cloud_url"),
        "cloud_url": sync_status.get("cloud_url"),
        "sync_policy": "\u624b\u6a5f\u96f2\u7aef\u5df2\u8207\u96fb\u8166\u7248\u540c\u6b65\u3002" if ok else "\u624b\u6a5f\u96f2\u7aef\u672a\u9054\u540c\u6b65\uff0c\u8acb\u91cd\u65b0\u57f7\u884c\u624b\u6a5f\u767c\u5e03\u3002",
    }
    MOBILE_REPORT_STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    now = datetime.now().isoformat(timespec="seconds")
    local_analysis = read_json(REPORTS / "latest_analysis.json")
    local_version = read_json(ROOT / "site" / "version.json")
    cloud_status = read_json(CLOUD_STATUS_PATH)
    local_low_daily = read_json(REPORTS / "\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304.json")
    local_low_monthly = read_json(REPORTS / "\u4f4e\u6a5f\u7387\u6bcf\u6708\u7e3d\u7d00\u9304\u5206\u6790.json")
    site_low_daily = read_json(ROOT / "site" / "low-probability-daily-record.json")
    site_low_monthly = read_json(ROOT / "site" / "low-probability-monthly-analysis.json")
    local_draw = latest_draw_signature(local_analysis.get("latest_draw", {}))
    local_prediction = prediction_signature(local_analysis)
    local_html_signature = html_signature(local_prediction)
    local_report_html = (REPORTS / "latest_battle_report.html").read_text(encoding="utf-8", errors="replace")
    local_site_html = (ROOT / "site" / "index.html").read_text(encoding="utf-8", errors="replace")
    status = {
        "status": "checking",
        "checked_at": now,
        "local_version": local_version.get("version"),
        "cloud_status": cloud_status.get("status"),
        "cloud_version": cloud_status.get("version"),
        "cloud_url": cloud_status.get("url") or cloud_status.get("prepared_cloud_url"),
        "local_latest_draw": local_draw,
        "local_prediction": local_prediction,
        "remote_latest_draw": {},
        "remote_prediction": {},
        "remote_version": {},
        "html_sync": {
            "expected": local_html_signature,
            "computer_report_contains_current_prediction": False,
            "local_mobile_contains_current_prediction": False,
            "remote_mobile_contains_current_prediction": False,
            "computer_report_has_stale_core": False,
            "local_mobile_has_stale_core": False,
            "remote_mobile_has_stale_core": False,
        },
        "low_probability_sync": {
            "local_daily_records": len(local_low_daily.get("records", [])) if isinstance(local_low_daily.get("records"), list) else 0,
            "local_month_count": len(local_low_monthly.get("months", [])) if isinstance(local_low_monthly.get("months"), list) else 0,
            "local_site_daily_same": False,
            "local_site_monthly_same": False,
            "remote_daily_same": False,
            "remote_monthly_same": False,
        },
        "rule": "\u96fb\u8166\u7248\u8207\u624b\u6a5f\u96f2\u7aef\u5fc5\u9808\u540c\u7248\u672c\u3001\u540c\u958b\u734e\u8cc7\u6599\u3001\u540c\u524d\u5341\u9810\u6e2c\u3001\u540c\u5f37\u724c\u5305\uff1b\u96f2\u7aef\u72c0\u614b\u5fc5\u9808\u70ba published\u3002",
    }
    failures = []
    status["html_sync"]["computer_report_contains_current_prediction"] = html_has_current_prediction(local_report_html, local_html_signature)
    status["html_sync"]["local_mobile_contains_current_prediction"] = html_has_current_prediction(local_site_html, local_html_signature)
    status["html_sync"]["computer_report_has_stale_core"] = html_has_stale_core(local_report_html)
    status["html_sync"]["local_mobile_has_stale_core"] = html_has_stale_core(local_site_html)
    if not status["html_sync"]["computer_report_contains_current_prediction"]:
        failures.append("\u96fb\u8166\u6230\u5831\u9801\u9762\u672a\u540c\u6b65\u6700\u65b0\u5f37\u724c\u5305")
    if not status["html_sync"]["local_mobile_contains_current_prediction"]:
        failures.append("\u624b\u6a5f\u672c\u6a5f\u9801\u9762\u672a\u540c\u6b65\u6700\u65b0\u5f37\u724c\u5305")
    if status["html_sync"]["computer_report_has_stale_core"]:
        failures.append("\u96fb\u8166\u6230\u5831\u9801\u9762\u4ecd\u6b98\u7559\u820a\u6838\u5fc3\u865f\u78bc")
    if status["html_sync"]["local_mobile_has_stale_core"]:
        failures.append("\u624b\u6a5f\u672c\u6a5f\u9801\u9762\u4ecd\u6b98\u7559\u820a\u6838\u5fc3\u865f\u78bc")
    status["low_probability_sync"]["local_site_daily_same"] = site_low_daily == local_low_daily and bool(local_low_daily.get("records"))
    status["low_probability_sync"]["local_site_monthly_same"] = site_low_monthly == local_low_monthly and bool(local_low_monthly.get("months"))
    if not local_low_daily.get("records"):
        failures.append("\u96fb\u8166\u7248\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304\u6c92\u6709\u8cc7\u6599")
    if not local_low_monthly.get("months"):
        failures.append("\u96fb\u8166\u7248\u4f4e\u6a5f\u7387\u6bcf\u6708\u7e3d\u7d00\u9304\u6c92\u6709\u8cc7\u6599")
    if not status["low_probability_sync"]["local_site_daily_same"]:
        failures.append("\u624b\u6a5f\u672c\u6a5f\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304\u672a\u540c\u6b65")
    if not status["low_probability_sync"]["local_site_monthly_same"]:
        failures.append("\u624b\u6a5f\u672c\u6a5f\u4f4e\u6a5f\u7387\u6bcf\u6708\u7e3d\u7d00\u9304\u672a\u540c\u6b65")
    if cloud_status.get("status") != "published":
        failures.append("\u624b\u6a5f\u96f2\u7aef\u5c1a\u672a\u767c\u5e03\u6210\u529f")
    remote_base = mobile_base_url(status.get("cloud_url"))
    status["remote_base"] = remote_base
    cache_token = str(int(time.time()))
    try:
        remote_version = fetch_json(f"{remote_base}/version.json?t={cache_token}")
        remote_analysis = fetch_json(f"{remote_base}/latest_analysis.json?t={cache_token}")
        remote_low_daily = fetch_json(f"{remote_base}/low-probability-daily-record.json?t={cache_token}")
        remote_low_monthly = fetch_json(f"{remote_base}/low-probability-monthly-analysis.json?t={cache_token}")
        remote_html = fetch_text(f"{remote_base}/index.html?t={cache_token}")
        remote_draw = latest_draw_signature(remote_analysis.get("latest_draw", {}))
        remote_prediction = prediction_signature(remote_analysis)
        status["remote_version"] = remote_version
        status["remote_latest_draw"] = remote_draw
        status["remote_prediction"] = remote_prediction
        status["html_sync"]["remote_mobile_contains_current_prediction"] = html_has_current_prediction(remote_html, local_html_signature)
        status["html_sync"]["remote_mobile_has_stale_core"] = html_has_stale_core(remote_html)
        if remote_draw != local_draw:
            failures.append("\u624b\u6a5f\u96f2\u7aef\u6700\u65b0\u958b\u734e\u8cc7\u6599\u8207\u96fb\u8166\u7248\u4e0d\u4e00\u81f4")
        if str(remote_version.get("latest_period")) != str(local_draw.get("period")):
            failures.append("\u624b\u6a5f\u96f2\u7aef\u7248\u672c\u6a94\u6700\u65b0\u671f\u6578\u8207\u96fb\u8166\u7248\u4e0d\u4e00\u81f4")
        if str(remote_version.get("version")) != str(local_version.get("version")):
            failures.append("\u624b\u6a5f\u96f2\u7aef\u7248\u672c\u865f\u8207\u96fb\u8166\u7248\u4e0d\u4e00\u81f4")
        if remote_prediction.get("top10") != local_prediction.get("top10"):
            failures.append("\u624b\u6a5f\u96f2\u7aef\u524d\u5341\u9810\u6e2c\u8207\u96fb\u8166\u7248\u4e0d\u4e00\u81f4")
        if remote_prediction.get("packs") != local_prediction.get("packs"):
            failures.append("\u624b\u6a5f\u96f2\u7aef\u5f37\u724c\u5305\u8207\u96fb\u8166\u7248\u4e0d\u4e00\u81f4")
        status["low_probability_sync"]["remote_daily_same"] = remote_low_daily == local_low_daily
        status["low_probability_sync"]["remote_monthly_same"] = remote_low_monthly == local_low_monthly
        if not status["low_probability_sync"]["remote_daily_same"]:
            failures.append("\u624b\u6a5f\u96f2\u7aef\u4f4e\u6a5f\u7387\u6bcf\u65e5\u7d00\u9304\u672a\u540c\u6b65")
        if not status["low_probability_sync"]["remote_monthly_same"]:
            failures.append("\u624b\u6a5f\u96f2\u7aef\u4f4e\u6a5f\u7387\u6bcf\u6708\u7e3d\u7d00\u9304\u672a\u540c\u6b65")
        if not status["html_sync"]["remote_mobile_contains_current_prediction"]:
            failures.append("\u624b\u6a5f\u96f2\u7aef\u9801\u9762\u672a\u540c\u6b65\u6700\u65b0\u5f37\u724c\u5305")
        if status["html_sync"]["remote_mobile_has_stale_core"]:
            failures.append("\u624b\u6a5f\u96f2\u7aef\u9801\u9762\u4ecd\u6b98\u7559\u820a\u6838\u5fc3\u865f\u78bc")
    except Exception as exc:
        failures.append(f"\u624b\u6a5f\u96f2\u7aef\u8b80\u53d6\u5931\u6557: {exc}")
    if failures:
        status["status"] = "failed"
        status["failures"] = failures
        STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        write_mobile_report_status(status)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 1
    status["status"] = "ok"
    status["message"] = "\u624b\u6a5f\u96f2\u7aef\u5df2\u8207\u96fb\u8166\u7248\u540c\u6b65"
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    write_mobile_report_status(status)
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

