"""ConfigMind — Brain 2: rule-based recommendation engine for PCS changes.

Derives actionable next-step recommendations from the completed ImpactReport.
Returns a dict matching the frontend ConfigMindRecommendation interface:
  { headline, what_this_means, warning, suggestion }
"""
from __future__ import annotations
from typing import Any, Optional


def get_recommendation(change_type: str, request: Any, report: Any) -> Optional[dict]:
    """Return a recommendation dict, or None if no recommendation applies."""
    if not change_type.startswith("pcs."):
        return None

    ec        = report.entity_counts
    approval  = report.approval
    gaps      = report.data_gaps or []
    warnings  = report.warnings or []
    risk      = report.riskLevel.value if hasattr(report.riskLevel, "value") else str(report.riskLevel)
    tier      = approval.tier.value    if hasattr(approval.tier,    "value") else str(approval.tier)
    confidence = report.confidence.value if hasattr(report.confidence, "value") else str(report.confidence)

    groups_affected  = ec.groups_affected  or 0
    devices_affected = ec.devices_affected or 0
    events_in_scope  = ec.events_in_scope  or 0

    has_workflow_gap      = any("workflow" in g.lower() for g in gaps)
    has_schema_gap        = any("schema" in g.lower() or "feature config" in g.lower() for g in gaps)
    has_toggle_gap        = any("toggle" in g.lower() or "feature toggle" in g.lower() for g in gaps)
    has_workflow_warning  = any("workflow" in (w.message or "").lower() for w in warnings)
    large_scope           = groups_affected > 1000 or devices_affected > 500
    audio_led_mismatch    = any(
        "audio" in (w.message or "").lower() and "led" in (w.message or "").lower()
        for w in warnings
    )

    # ── pcs.disable_sub_feature ───────────────────────────────────────────────
    if change_type == "pcs.disable_sub_feature":

        if has_workflow_gap and large_scope:
            return {
                "headline": (
                    f"Confirm workflow for this group."
                    f"before disabling across {groups_affected:,} groups."
                ),
                "what_this_means": (
                    f"Disabling this sub-feature will immediately stop safety event recording "
                    f"for {devices_affected:,} device{'s' if devices_affected != 1 else ''} "
                    f"across {groups_affected:,} groups. "
                    "The coaching workflow could not be retrieved, so it is unknown how many "
                    "coaches will be affected and whether shared workflows extend the blast "
                    "radius beyond this hierarchy."
                ),
                "warning": (
                    "Confirm workflow for this group. "
                    "If this workflow is shared, disabling the sub-feature may silently "
                    "affect coaching queues for groups outside the selected hierarchy."
                ) if has_workflow_warning else None,
                "suggestion": (
                    "1. Confirm workflow for this group. "
                    "2. Once the workflow is confirmed, check how many other groups share it. "
                    "3. If shared with more than 3 groups, apply the change to a single "
                    "sub-group first and monitor for 24–48 hours before rolling out to the "
                    "full hierarchy."
                ),
            }

        # if has_schema_gap:
        #     return {
        #         "headline": "Feature dependency graph is incomplete — full impact cannot be confirmed.",
        #         "what_this_means": (
        #             "The configuration file for this sub-feature could not be loaded, so it is "
        #             "unknown which device settings, alert thresholds, or shared prerequisites are "
        #             "tied to this behavior. There may be other active features that share a "
        #             "prerequisite with this one that would be inadvertently disabled."
        #         ),
        #         "warning": (
        #             "Proceeding without the feature schema means you may disable a shared "
        #             "prerequisite and break unrelated features for drivers in this group."
        #         ),
        #         "suggestion": (
        #             "Ensure the PCS feature configuration files are accessible on this host "
        #             "(set PCS_CONFIGS_PATH in your .env file), then re-run the analysis to "
        #             "get a complete dependency graph before applying this change."
        #         ),
        #     }

        if audio_led_mismatch:
            return {
                "headline": "Audio and LED alerts will remain active while event recording is turned off.",
                "what_this_means": (
                    "This change disables event recording but leaves in-cab audio and LED alerts "
                    "enabled. Drivers will continue to receive alert notifications but no safety "
                    "event will be created for coaches to review. This creates a disconnect "
                    f"between what drivers experience and what coaches see across "
                    f"{devices_affected:,} device{'s' if devices_affected != 1 else ''}."
                ),
                "warning": (
                    "Confirm this alert/event mismatch is intentional. If coaches expect to "
                    "review events for this behavior, they will find an empty queue despite "
                    "drivers receiving alerts."
                ),
                "suggestion": (
                    "Either also disable audio and LED alerts (to silence all feedback for "
                    "this behavior), or keep event recording enabled. If the goal is to "
                    "reduce coaching volume only, consider raising the detection threshold "
                    "instead of disabling the sub-feature."
                ),
            }

        if large_scope and events_in_scope > 500:
            return {
                "headline": (
                    f"High-volume active program — {events_in_scope:,} events in the last 30 days "
                    f"will stop being recorded across {groups_affected:,} groups."
                ),
                "what_this_means": (
                    f"This group has recorded {events_in_scope:,} safety events in the past "
                    "30 days. Disabling this sub-feature will cause an immediate and visible "
                    "drop in event volume on safety dashboards and compliance reports. "
                    f"All {devices_affected:,} devices will stop recording events for this "
                    "behavior once they next check in."
                ),
                "warning": (
                    "A sudden drop from an active event stream to zero will be visible in "
                    "trend reports and may raise compliance or audit concerns."
                ),
                "suggestion": (
                    "Before disabling, notify the fleet safety manager and any auditors who "
                    "rely on this event stream. Consider scheduling the change at the start "
                    "of a reporting period to minimise the impact on historical trend data."
                ),
            }

        if large_scope:
            return {
                "headline": (
                    f"Very large scope — consider a phased rollout across "
                    f"{groups_affected:,} groups."
                ),
                "what_this_means": (
                    f"This change will affect {groups_affected:,} groups and "
                    f"{devices_affected:,} devices simultaneously. "
                    "A phased approach — starting with a single sub-group — lets you "
                    "validate the outcome before it propagates to the full hierarchy."
                ),
                "warning": None,
                "suggestion": (
                    "Select a representative sub-group of 5–10 devices, apply the disable "
                    "there first, and confirm the expected behavior over 24 hours before "
                    "rolling out to the full hierarchy."
                ),
            }

    # ── pcs.enable_sub_feature ────────────────────────────────────────────────
    elif change_type == "pcs.enable_sub_feature":

        if has_toggle_gap and has_workflow_gap:
            return {
                "headline": "Two critical unknowns must be resolved before enabling this feature.",
                "what_this_means": (
                    "The platform-level feature toggle status could not be confirmed, and the "
                    "coaching workflow for this group need to be confirmed. If the feature toggle "
                    "is not active, enabling the sub-feature will have no effect on devices "
                    "or drivers. If the workflow is not configured to handle this behavior, "
                    "events will be recorded but coaches will not be assigned to review them."
                ),
                "warning": (
                    "Enabling without resolving these gaps risks a silent failure — the "
                    "feature appears enabled in configuration but has no effect in the field, "
                    "or events accumulate without coaching assignments."
                ),
                "suggestion": (
                    "1. Verify the feature toggle is active for this company with the platform team. "
                    "2. Confirm the workflow for this group is configured to handle this behavior. "
                    "3. Re-run the analysis after both gaps are resolved."
                ),
            }

        # if has_toggle_gap:
        #     return {
        #         "headline": "Feature toggle status is unknown — confirm it is active before enabling.",
        #         "what_this_means": (
        #             "A platform-level feature toggle controls whether this feature can be "
        #             "activated for this company. The toggle check returned an error, so it is "
        #             "unknown whether the toggle is on. If it is off, this configuration change "
        #             "will have no visible effect for drivers or devices."
        #         ),
        #         "warning": (
        #             "Proceeding without confirming the toggle means this change may appear "
        #             "saved but have zero effect in the field."
        #         ),
        #         "suggestion": (
        #             "Contact the platform team to verify the feature toggle is active for "
        #             f"Company ID {getattr(getattr(request, 'targetScope', None), 'companyId', 0)}. "
        #             "Once confirmed, re-run the analysis to clear this data gap."
        #         ),
        #     }

        if has_workflow_gap and large_scope:
            return {
                "headline": (
                    f"Coaching workflow must be confirmed before enabling across "
                    f"{groups_affected:,} groups."
                ),
                "what_this_means": (
                    f"Enabling this sub-feature will activate event recording for "
                    f"{devices_affected:,} devices across {groups_affected:,} groups. "
                    "However, the coaching workflow could not be retrieved. If the workflow "
                    "is not configured to route this behavior to coaches, events will be "
                    "recorded but no coaching assignments will be created."
                ),
                "warning": (
                    "Coaches may receive a surge of new events with no routing rules, "
                    "leading to an unmanaged coaching queue."
                ),
                "suggestion": (
                    "Resolve the workflow API error, confirm the behavior is included in "
                    "the coaching workflow, and if shared with other groups verify no "
                    "unintended cascade effects before enabling at this scale."
                ),
            }

        if large_scope:
            return {
                "headline": (
                    f"Very large rollout — {groups_affected:,} groups and "
                    f"{devices_affected:,} devices will be activated simultaneously."
                ),
                "what_this_means": (
                    "Enabling this sub-feature will push configuration changes to "
                    f"{devices_affected:,} devices across {groups_affected:,} groups. "
                    "Devices apply the new settings on their next check-in, which can take "
                    "several hours, creating a window where some devices are active and "
                    "others are not."
                ),
                "warning": None,
                "suggestion": (
                    "Enable on a pilot sub-group first (5–10 devices) and validate alert "
                    "and event behavior over 24–48 hours. Once confirmed, roll out to the "
                    "full hierarchy."
                ),
            }

    # ── pcs.change_threshold ──────────────────────────────────────────────────
    elif change_type == "pcs.change_threshold":

        # if has_schema_gap:
        #     return {
        #         "headline": "Threshold dependency unknown — full downstream impact could not be assessed.",
        #         "what_this_means": (
        #             "The feature configuration file for this threshold could not be loaded. "
        #             "It is unknown whether this threshold is shared with other sub-features "
        #             "or whether changing it will affect behaviors beyond the one being modified."
        #         ),
        #         "warning": (
        #             "Shared thresholds affect all features that depend on them. "
        #             "Proceeding without the schema may cause unintended changes to other "
        #             "active behaviors."
        #         ),
        #         "suggestion": (
        #             "Set PCS_CONFIGS_PATH in your .env to point to the feature configuration "
        #             "files and re-run the analysis to identify all dependent features before "
        #             "applying the threshold change."
        #         ),
        #     }

        if large_scope and events_in_scope > 0:
            direction = _infer_threshold_direction(request)
            return {
                "headline": (
                    f"Threshold change will shift event volume across "
                    f"{devices_affected:,} devices — "
                    + ("expect more events." if direction == "lower" else "expect fewer events.")
                ),
                "what_this_means": (
                    f"This group generated {events_in_scope:,} safety events in the last 30 days. "
                    + (
                        "Lowering the detection threshold means the bar for triggering an event "
                        "is reduced — event volume will increase. Coaches should expect a higher "
                        "review workload after this change takes effect."
                        if direction == "lower" else
                        "Raising the detection threshold means fewer events will be triggered — "
                        "event volume will decrease. Safety scores may improve, but genuine "
                        "incidents may be missed if the threshold is too high."
                    )
                ),
                "warning": (
                    "Threshold changes create a data discontinuity. Safety scores and trend "
                    "reports before and after this change are not directly comparable."
                ),
                "suggestion": (
                    "Apply the threshold change to a pilot sub-group and monitor event volume "
                    "for 48 hours. Compare the before/after event rate to confirm the new "
                    "threshold achieves the intended sensitivity before rolling out broadly."
                ),
            }

        return {
            "headline": "Verify threshold value before applying — lower values generate more events.",
            "what_this_means": (
                "Alert thresholds are inversely related to event volume: a lower threshold "
                "value means more events are generated (the bar to trigger is lower), while "
                "a higher value means fewer events. Confirm the new value achieves the "
                "intended detection sensitivity."
            ),
            "warning": None,
            "suggestion": (
                "Test on a small group first and review the event rate change over 24 hours "
                "before rolling out to the full hierarchy."
            ),
        }

    # ── Fallback for any other pcs.* change ───────────────────────────────────
    if risk in ("high", "critical") and tier in ("senior_csm", "hotl", "hard_block"):
        return {
            "headline": "Senior review required — resolve all data gaps before proceeding.",
            "what_this_means": (
                "This change has been flagged for senior CSM review due to its risk level "
                f"and the size of the affected fleet ({groups_affected:,} groups, "
                f"{devices_affected:,} devices). "
                "All data gaps listed below should be resolved to complete the impact picture."
            ),
            "warning": (
                f"{len(gaps)} data gap{'s' if len(gaps) != 1 else ''} remain unresolved. "
                "Proceeding with incomplete information increases the risk of unintended impact."
            ) if gaps else None,
            "suggestion": (
                "Address each data gap, re-run the analysis to confirm full coverage, "
                "then submit for senior CSM sign-off with the updated report."
            ),
        }

    return None


def _infer_threshold_direction(request: Any) -> str:
    """Infer whether the threshold is going lower (more events) or higher (fewer)."""
    try:
        for change in (request.proposedChanges or []):
            current  = change.currentValue
            proposed = change.proposedValue
            if current is not None and proposed is not None:
                if float(proposed) < float(current):
                    return "lower"
                if float(proposed) > float(current):
                    return "higher"
    except (TypeError, ValueError, AttributeError):
        pass
    return "unknown"
