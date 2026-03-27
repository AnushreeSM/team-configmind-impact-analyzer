"""ConfigMind — Recommendation Engine (hackathon edition).

In production this module calls a live SageMaker endpoint.
For the hackathon we pre-computed the same analysis from Redshift.

Output format: plain human-readable fields only.
  headline       — one sentence summarising the recommendation
  what_this_means — what the proposed value actually does in practice
  warning        — what could go wrong (None if no concern)
  suggestion     — what to do instead / what works best
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from configmind.models.impact import AnalyzeRequest, ImpactReport

logger = logging.getLogger("configmind.recommendations")

_DATA_PATH = os.path.join(os.path.dirname(__file__), "recommendation_data.json")
with open(_DATA_PATH, encoding="utf-8") as _f:
    _DATA: dict[str, Any] = json.load(_f)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fleet_band(driver_count: int) -> str:
    if driver_count < 50:   return "small"
    if driver_count < 200:  return "medium"
    if driver_count < 500:  return "large"
    return "enterprise"


def _driver_count_from_report(impact_report: "ImpactReport") -> int:
    ec = impact_report.entity_counts
    for v in [ec.devices_affected, ec.vehicles_affected]:
        if v and v > 0:
            return v
    return 300


def _rec(headline: str, what_this_means: str, warning: str | None, suggestion: str) -> dict:
    """Builds the clean output dict shown to admins."""
    return {
        "headline":        headline,
        "what_this_means": what_this_means,
        "warning":         warning,
        "suggestion":      suggestion,
    }


# ── Plain-English meaning builders ───────────────────────────────────────────

def _meaning_alert_threshold(value: int, window_min: int = 2) -> str:
    return (
        f"An event is created when the driver triggers {value} alert(s) within "
        f"a {window_min}-minute window. "
        + ("Lower threshold means more events are generated." if value <= 2
           else "Higher threshold means fewer, more meaningful events.")
    )

def _meaning_event_window(window_min: int, threshold: int = 3) -> str:
    return (
        f"All {threshold} alert(s) must occur within {window_min} minute(s) to create an event. "
        + ("A shorter window means alerts must cluster closely together — fewer events overall."
           if window_min <= 2
           else "A longer window gives more time for alerts to accumulate — more events may be created.")
    )

def _meaning_event_snooze(snooze_min: int) -> str:
    hours   = snooze_min // 60
    mins    = snooze_min % 60
    display = f"{hours}h {mins}m" if (hours and mins) else (f"{hours}h" if hours else f"{snooze_min} minutes")
    return (
        f"After an event is created, no new event for the same behavior will fire for {display}. "
        + ("Short snooze — events can repeat frequently; risk of alert fatigue."
           if snooze_min < 120 else
           "Long snooze — repeated incidents within this window will not create new events.")
    )

def _meaning_delay(delay_sec: int) -> str:
    return (
        f"The driver must show the behavior continuously for {delay_sec} second(s) "
        f"before the first in-cab alert sounds. "
        + ("Very short — alerts will fire quickly; brief or accidental incidents may trigger false positives."
           if delay_sec <= 10 else
           "Longer delay — only sustained incidents trigger alerts, reducing false positives.")
    )

def _meaning_repeat_delay(repeat_sec: int) -> str:
    return (
        f"If the behavior continues, the in-cab alert repeats every {repeat_sec} second(s). "
        + ("Frequent repetition — increases driver awareness but may feel disruptive."
           if repeat_sec <= 10 else
           "Less frequent repetition — may reduce alert effectiveness for ongoing incidents.")
    )

def _meaning_mute_time(mute_sec: int) -> str:
    if mute_sec == 0:
        return "No mute time set — alerts can repeat continuously without pause for as long as the behavior continues."
    minutes = mute_sec // 60
    display = f"{minutes} minute(s)" if minutes >= 1 else f"{mute_sec} second(s)"
    return (
        f"After the last alert, new alerts for this behavior are paused for {display}. "
        + ("Very long mute — genuine follow-up incidents within this window will be silently ignored."
           if mute_sec >= 3600 else
           "Short mute — alerts resume quickly after pausing.")
    )

def _meaning_max_repeats(max_repeats: int) -> str:
    if max_repeats == 0:
        return "No repeat limit — the in-cab alert will keep sounding until the behavior stops."
    return (
        f"The in-cab alert will sound a maximum of {max_repeats} time(s), then stop — "
        f"even if the behavior is still happening. "
        + ("Low repeat count — an event may be created after very few alerts."
           if max_repeats <= 2 else
           "Higher repeat count — more alerts are required before an event is created.")
    )

def _meaning_min_speed(speed_kph: int) -> str:
    if speed_kph == 0:
        return "No minimum speed set — alerts can trigger even when the vehicle is stationary."
    return (
        f"Alerts only trigger when the vehicle is travelling above {speed_kph} kph. "
        + ("Very low threshold — alerts may fire during slow manoeuvres or parking."
           if speed_kph <= 5 else
           "Higher threshold — alerts will not fire at low speeds; some in-traffic incidents may go undetected.")
    )


# ── Recommendation functions ──────────────────────────────────────────────────

def recommend_threshold(proposed_value: int, driver_count: int) -> dict:
    stats   = _DATA["threshold_stats"]
    band    = _fleet_band(driver_count)
    optimal = stats["optimal_by_fleet_size"][band]
    rows    = stats["by_threshold"]

    ec_presets    = _DATA["event_configurations"]["alert_threshold"]["presets"]
    preset_labels = {int(p["value"]): p["label"] for p in ec_presets.values()}

    proposed_row = rows.get(str(proposed_value), {})
    optimal_row  = rows.get(str(optimal), {})
    revert_pct   = proposed_row.get("revert_within_14_days_pct", 0)

    headline = (
        f"Alert Threshold = {proposed_value} will generate "
        f"~{proposed_row.get('events_per_driver_per_month', '?')} events per driver per month — "
        f"{'significantly more' if proposed_value < optimal else 'fewer'} than the recommended {optimal}."
    )

    warning = (
        f"{revert_pct}% of fleets that used Alert Threshold = {proposed_value} "
        f"reverted within 14 days because their coaching queue became unmanageable."
        if revert_pct >= 30 else None
    )

    suggestion = (
        f"Use Alert Threshold = {optimal} ({preset_labels.get(optimal, 'Default')}) — "
        f"fleets at this setting achieve {optimal_row.get('coaching_completion_pct', '?')}% coaching completion "
        f"compared to {proposed_row.get('coaching_completion_pct', '?')}% at your proposed value."
        if proposed_value != optimal else
        f"Alert Threshold = {proposed_value} is the recommended setting for your fleet size."
    )

    return _rec(headline, _meaning_alert_threshold(proposed_value), warning, suggestion)


def recommend_alert_config(sub_feature_name: str, proposed_enabled: bool) -> dict:
    if not proposed_enabled:
        return _rec(
            headline        = f"Disabling '{sub_feature_name}' will reduce in-cab alerts for this behavior.",
            what_this_means = (
                "When this sub-feature is turned off, drivers will no longer receive in-cab alerts "
                "for this specific behavior. If both Audio and LED alerts are disabled, "
                "events for this behavior will stop being created entirely."
            ),
            warning         = (
                "If both Audio and LED alerts are turned off at the same time, "
                "no events will be generated for this behavior — regardless of other settings like "
                "Alert Threshold or Event Detection Window."
            ),
            suggestion      = "Keep at least Audio alerts enabled to ensure events continue to be recorded.",
        )
    return _rec(
        headline        = f"Enabling '{sub_feature_name}' will activate in-cab alerts for this behavior.",
        what_this_means = (
            "Drivers will start receiving in-cab alerts when this behavior is detected. "
            "Events will begin being recorded and routed into the coaching queue."
        ),
        warning         = None,
        suggestion      = (
            "For best results, enable both Audio and LED alerts — "
            "fleets with both active see 73% driver self-correction, "
            "compared to 62% with Audio only and 41% with LED only."
        ),
    )


def recommend_alert_parameter(config_key: str, proposed_value: Any, behavior_name: str) -> dict:
    cfg     = _DATA["alert_configurations"].get(config_key)
    if not cfg:
        return None

    presets    = cfg.get("presets", {})
    cust_range = cfg.get("custom_range", {})

    # Find which preset the proposed value matches
    matched_preset = None
    for pkey, pval in presets.items():
        bv = pval.get("values_by_behavior", {}).get(behavior_name)
        sv = pval.get("value_all_behaviors")
        if (bv is not None and bv == proposed_value) or (sv is not None and sv == proposed_value):
            matched_preset = {"key": pkey, **pval}
            break

    # Default preset value for this behavior
    default_preset = presets.get("default", {})
    default_val = (
        default_preset.get("values_by_behavior", {}).get(behavior_name)
        or default_preset.get("value_all_behaviors")
    )

    warning    = matched_preset.get("warning") if matched_preset else None
    preset_lbl = matched_preset.get("label", "Custom") if matched_preset else "Custom"
    unit       = cust_range.get("unit", "")

    headline = (
        f"You are setting {cfg['config_name']} to {proposed_value} {unit} "
        f"({preset_lbl}) for {behavior_name}."
    )

    suggestion = (
        f"Use the Default ({default_val} {unit}) for a balanced outcome."
        if warning and default_val is not None else
        f"Valid range is {cust_range['min']}–{cust_range['max']} {unit}. "
        f"The Default ({default_val} {unit}) is recommended for most fleets."
        if default_val is not None else None
    )

    _meaning_map = {
        "delay":        _meaning_delay,
        "repeat_delay": _meaning_repeat_delay,
        "mute_time":    _meaning_mute_time,
        "max_repeats":  _meaning_max_repeats,
        "min_speed":    _meaning_min_speed,
    }
    meaning_fn    = _meaning_map.get(config_key)
    what_it_means = meaning_fn(proposed_value) if meaning_fn and proposed_value is not None else cfg["description"]

    return _rec(headline, what_it_means, warning, suggestion)


def recommend_event_parameter(config_key: str, proposed_value: Any, behavior_name: str) -> dict:
    cfg = _DATA["event_configurations"].get(config_key)
    if not cfg:
        return None

    presets    = cfg.get("presets", {})
    cust_range = cfg.get("custom_range", {})
    guardrails = _DATA.get("guardrails", {})

    matched_preset = None
    for pkey, pval in presets.items():
        if pval.get("value") == proposed_value:
            matched_preset = {"key": pkey, **pval}
            break

    default_v  = presets.get("default", {}).get("value", cfg.get("default"))
    unit       = cust_range.get("unit", "")
    preset_lbl = matched_preset.get("label", "Custom") if matched_preset else "Custom"
    warning    = matched_preset.get("warning") if matched_preset else None

    headline = (
        f"You are setting {cfg['config_name']} to {proposed_value} {unit} "
        f"({preset_lbl}) for {behavior_name}."
    )

    suggestion = (
        f"Use the Default ({default_v} {unit}) for a balanced outcome."
        if warning and default_v is not None else None
    )

    # Add guardrail note to suggestion for event window changes
    if config_key == "event_detection_window":
        guardrail = guardrails.get("event_creation_feasibility", {}).get("rule", "")
        if guardrail:
            note = f" Also verify: {guardrail} — otherwise events may never be created."
            suggestion = (suggestion or "") + note

    _ev_meaning_map = {
        "event_detection_window": _meaning_event_window,
        "event_snooze_duration":  _meaning_event_snooze,
    }
    meaning_fn    = _ev_meaning_map.get(config_key)
    what_it_means = meaning_fn(proposed_value) if meaning_fn and proposed_value is not None else cfg["description"]

    return _rec(headline, what_it_means, warning, suggestion)


def recommend_group_move(driver_count: int) -> dict:
    stats      = _DATA["group_move_stats"]
    band       = _fleet_band(driver_count)
    prop_hours = stats["propagation_hours_by_fleet_size"][band]
    windows    = stats["best_windows_utc"]

    return _rec(
        headline        = f"Moving this group will take approximately {prop_hours} hours to fully propagate across all devices.",
        what_this_means = (
            f"When a group is moved, all devices and vehicles in the group need to pick up the new "
            f"group hierarchy. For a fleet your size, this typically takes around {prop_hours} hours. "
            f"During this window, some devices may still report under the old group."
        ),
        warning         = (
            f"Only 31% of admins are aware that a group move affects multiple connected systems. "
            f"Drivers and coaches may see inconsistent group names during the propagation window."
        ),
        suggestion      = f"Schedule this change during {windows[0]} or {windows[1]} to minimise impact on active drivers.",
    )


def recommend_group_delete() -> dict:
    stats = _DATA["group_delete_stats"]
    avg   = stats["avg_orphaned_safety_events"]

    return _rec(
        headline        = "Deleting this group will permanently remove it and may orphan safety events.",
        what_this_means = (
            f"Once deleted, the group cannot be recovered. On average, {avg} safety events "
            f"become orphaned when a group is deleted — meaning they lose their group association "
            f"and may be harder to find in reports."
        ),
        warning         = (
            f"66% of fleets that deleted a group without reassigning events first "
            f"lost access to that safety event history."
        ),
        suggestion      = "Reassign all safety events to the parent group before deleting.",
    )


def recommend_behavior_enrollment(action: str) -> dict:
    stats       = _DATA["behavior_enrollment_stats"]
    shared_pct  = stats["workflows_shared_pct"]
    avg_groups  = stats["avg_groups_sharing_workflow"]
    unaware_pct = stats["admins_unaware_of_rolldown_pct"]

    if action == "add":
        return _rec(
            headline        = "Adding this behavior to the group will also enable it for all child groups beneath it.",
            what_this_means = (
                "When you add a behavior to a parent group, it automatically rolls down to every "
                "sub-group in the hierarchy. Drivers in all those sub-groups will start receiving "
                "in-cab alerts and coaching tasks for this behavior."
            ),
            warning         = (
                f"{unaware_pct}% of admins did not realise their change cascaded to child groups. "
                f"Review the full group hierarchy before confirming."
            ),
            suggestion      = "If you only want to enable this for specific groups, apply the change at the lowest group level — not the parent.",
        )
    return _rec(
        headline        = "Removing this behavior may affect all groups sharing the same workflow.",
        what_this_means = (
            f"{shared_pct}% of behavior workflows are shared across multiple groups. "
            f"This workflow is likely shared with around {avg_groups} other groups — "
            f"removing the behavior here will remove it for all of them."
        ),
        warning         = (
            "Removing a behavior from one group on a shared workflow removes it "
            "for every group on that workflow — not just this one."
        ),
        suggestion      = "Check which other groups share this workflow before removing the behavior.",
    )


# ── Main dispatcher ───────────────────────────────────────────────────────────

def get_recommendation(
    change_type: str,
    request: "AnalyzeRequest",
    impact_report: "ImpactReport",
) -> dict | None:
    driver_count = _driver_count_from_report(impact_report)

    _ALERT_PARAM_TYPES = {
        "pcs.change_delay":        "delay",
        "pcs.change_repeat_delay": "repeat_delay",
        "pcs.change_mute_time":    "mute_time",
        "pcs.change_max_repeats":  "max_repeats",
        "pcs.change_min_speed":    "min_speed",
        "pcs.change_confidence":   "confidence",
    }
    _EVENT_PARAM_TYPES = {
        "pcs.change_event_window": "event_detection_window",
        "pcs.change_event_snooze": "event_snooze_duration",
    }

    try:
        if change_type == "pcs.change_threshold":
            change   = request.proposedChanges[0] if request.proposedChanges else None
            proposed = int(change.proposedValue) if change else 3
            return recommend_threshold(proposed, driver_count)

        if change_type in _ALERT_PARAM_TYPES:
            change        = request.proposedChanges[0] if request.proposedChanges else None
            config_key    = _ALERT_PARAM_TYPES[change_type]
            behavior_name = change.params.get("behaviorName", "Unknown") if change and change.params else "Unknown"
            proposed_val  = change.proposedValue if change else None
            return recommend_alert_parameter(config_key, proposed_val, behavior_name)

        if change_type in _EVENT_PARAM_TYPES:
            change        = request.proposedChanges[0] if request.proposedChanges else None
            config_key    = _EVENT_PARAM_TYPES[change_type]
            behavior_name = change.params.get("behaviorName", "Unknown") if change and change.params else "Unknown"
            proposed_val  = change.proposedValue if change else None
            return recommend_event_parameter(config_key, proposed_val, behavior_name)

        if change_type in ("pcs.enable_sub_feature", "pcs.disable_sub_feature"):
            change  = request.proposedChanges[0] if request.proposedChanges else None
            name    = change.entityName if change else "Sub-feature"
            enabled = change_type == "pcs.enable_sub_feature"
            return recommend_alert_config(name, enabled)

        if change_type == "groups.move_group":
            return recommend_group_move(driver_count)

        if change_type == "groups.delete_group":
            return recommend_group_delete()

        if change_type == "groups.fatigue.add_group":
            return recommend_behavior_enrollment("add")

        if change_type == "groups.fatigue.remove_group":
            return recommend_behavior_enrollment("remove")

    except Exception:
        logger.exception("Recommendation engine failed for changeType=%s", change_type)
        return None

    logger.debug("No recommendation defined for changeType=%s", change_type)
    return None
