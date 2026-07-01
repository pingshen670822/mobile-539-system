# 539 Daily Integrity Audit

- generated_at: 2026-07-02T07:34:35
- status: passed
- failed_count: 0

- PASS: draw_count_minimum / {'count': 5903, 'min_period': 96000001, 'max_period': 115000159, 'min_date': '2007-01-01', 'max_date': '2026-07-01'}
- PASS: latest_date_fresh / {'latest': '2026-07-01', 'expected': '2026-07-01'}
- PASS: no_duplicate_periods / []
- PASS: no_duplicate_dates / []
- PASS: no_invalid_draw_rows / []
- PASS: no_stale_pending_predictions / []
- PASS: recent_predictions_settled / [{'target_period': 115000154, 'status': 'settled', 'actual_period': 115000154, 'top5_hits': 1, 'top10_hits': 1, 'top15_hits': 1}, {'target_period': 115000155, 'status': 'settled', 'actual_period': 115000155, 'top5_hits': 1, 'top10_hits': 1, 'top15_hits': 2}, {'target_period': 115000156, 'status': 'settled', 'actual_period': 115000156, 'top5_hits': 0, 'top10_hits': 1, 'top15_hits': 2}, {'target_period': 115000157, 'status': 'settled', 'actual_period': 115000157, 'top5_hits': 1, 'top10_hits': 2, 'top15_hits': 3}, {'target_period': 115000158, 'status': 'settled', 'actual_period': 115000158, 'top5_hits': 0, 'top10_hits': 2, 'top15_hits': 3}, {'target_period': 115000159, 'status': 'settled', 'actual_period': 115000159, 'top5_hits': 0, 'top10_hits': 1, 'top15_hits': 1}]
- PASS: no_missing_recent_prediction_records / []
- PASS: latest_draw_has_settled_prediction_record / {'target_period': 115000159, 'status': 'settled', 'actual_period': 115000159, 'actual_date': '2026-07-01', 'top5_hits': 0, 'top10_hits': 1, 'top15_hits': 1}
- PASS: analysis_matches_database / {'analysis': 115000159, 'database': 115000159}
- PASS: health_sync_passed / {'database_latest_period': 115000159, 'analysis_latest_period': 115000159, 'prediction_based_on_period': 115000159, 'status': 'synced'}
- PASS: history_has_latest_pending_or_settled / {'expected_target': 115000160}
- PASS: battle_report_mentions_latest / {'period': 115000159, 'draw_date': '2026-07-01'}
- PASS: battle_report_has_settlement_rows / settled and pending labels
- PASS: battle_report_is_compact_precision_report / compact precision report labels
- PASS: battle_report_has_explicit_dates / date labels
- PASS: battle_report_has_low_probability_link / low probability page link
- PASS: battle_report_has_super_single_section / super single section
- PASS: battle_report_has_no_mojibake_question_marks / battle report must not contain mojibake question marks
- PASS: low_probability_page_exists / C:\Users\MSI\Documents\Codex\2026-06-01\539\outputs\TW539預測系統_20260701_第05版_每月總整理報表版\TW539Core\reports\539低機率精準暫避.html
- PASS: low_probability_page_has_no_mojibake_question_marks / low probability page must not contain mojibake question marks
- PASS: low_probability_page_has_required_sections / low probability section labels