"""ConfigMind — Bedrock agentic loop.

Single entry point: analyze(request, token) → ImpactReport

Flow:
  1. Build initial user message from the AnalyzeRequest
  2. Loop (up to MAX_AGENT_TURNS):
     a. Call Bedrock converse with tool definitions
     b. If stop_reason == "tool_use"  → execute each tool, feed results back
     c. If stop_reason == "end_turn"  → parse final JSON response
  3. Parse Bedrock's JSON output into a typed ImpactReport
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import boto3

from configmind.config import BEDROCK_MODEL_ID, BEDROCK_REGION, MAX_AGENT_TURNS
from configmind.models.impact import (
    AnalyzeRequest,
    ApprovalDecision,
    ApprovalTier,
    Confidence,
    EntityCounts,
    ImpactItem,
    ImpactReport,
    RiskLevel,
    Warning,
)
from configmind.tools.definitions import TOOL_DEFINITIONS
from configmind.tools.dispatcher import execute_tool
from configmind.agent.prompts import build_system_prompt
from configmind.recommendations import get_recommendation

logger = logging.getLogger("configmind.agent")


# ── Bedrock client (module-level, reused across requests) ─────────────────────
_bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


# ── User message builder ──────────────────────────────────────────────────────

def _build_user_message(request: AnalyzeRequest) -> str:
    lines = [
        f"CHANGE TYPE: {request.changeType}",
        f"GROUP: {request.targetScope.groupName} (id={request.targetScope.groupId})",
        f"COMPANY ID: {request.targetScope.companyId}",
        "",
        "PROPOSED CHANGES:",
    ]
    for c in request.proposedChanges:
        lines.append(
            f"  - {c.entityType} '{c.entityName}' (id={c.entityId}): "
            f"{c.field} {c.currentValue!r} → {c.proposedValue!r}"
        )
        if c.params:
            lines.append(f"    params: {json.dumps(c.params)}")

    if not request.proposedChanges:
        lines.append("  (no explicit changes listed — use changeType to determine what to analyse)")

    lines += [
        "",
        "Call the appropriate tools to gather real data, then return the impact report JSON.",
    ]
    return "\n".join(lines)


# ── Tool execution helper ─────────────────────────────────────────────────────

def _run_tools(tool_uses: list[dict], token: str) -> list[dict]:
    """Execute all tool_use blocks and format results for Bedrock."""
    results = []
    for block in tool_uses:
        tu = block["toolUse"]
        tool_name   = tu["name"]
        tool_input  = tu["input"]
        tool_use_id = tu["toolUseId"]

        logger.info("  → tool: %s  input: %s", tool_name, json.dumps(tool_input)[:200])
        result = execute_tool(tool_name, tool_input, token)
        logger.info("  ← result source: %s", result.get("source", "?"))

        results.append({
            "toolResult": {
                "toolUseId": tool_use_id,
                "content": [{"text": json.dumps(result, default=str)}],
            }
        })
    return results


# ── Response parser ───────────────────────────────────────────────────────────

def _parse_response(text: str) -> dict[str, Any]:
    """Extract the JSON object from Bedrock's final text response."""
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[-1] if cleaned.count("```") >= 2 else cleaned
        cleaned = cleaned.lstrip("json").strip()
    try:
        start = cleaned.index("{")
        end   = cleaned.rindex("}") + 1
        return json.loads(cleaned[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse Bedrock response as JSON: %s\nText: %s", exc, text[:500])
        return {}


def _coerce_risk(value: Any) -> RiskLevel:
    try:
        return RiskLevel(str(value).lower())
    except ValueError:
        return RiskLevel.MEDIUM


def _coerce_confidence(value: Any) -> Confidence:
    try:
        return Confidence(str(value).lower())
    except ValueError:
        return Confidence.MEDIUM


def _to_impact_report(parsed: dict[str, Any], turns: int, elapsed_ms: int) -> ImpactReport:
    """Convert the parsed dict to a typed ImpactReport."""
    impacts = [
        ImpactItem(
            area        = i.get("area", ""),
            change      = i.get("change", ""),
            effect      = i.get("effect", ""),
            risk        = _coerce_risk(i.get("risk", "medium")),
            detail      = i.get("detail", ""),
            confidence  = _coerce_confidence(i.get("confidence", "medium")),
            data_source = i.get("data_source", ""),
        )
        for i in parsed.get("impacts", [])
    ]

    warnings = [
        Warning(
            type        = w.get("type", ""),
            severity    = _coerce_risk(w.get("severity", "medium")),
            message     = w.get("message", ""),
            bug_ref     = w.get("bug_ref", ""),
            data_source = w.get("data_source", ""),
        )
        for w in parsed.get("warnings", [])
    ]

    ec_raw = parsed.get("entity_counts", {})
    entity_counts = EntityCounts(
        groups_affected    = ec_raw.get("groups_affected"),
        devices_affected   = ec_raw.get("devices_affected"),
        vehicles_affected  = ec_raw.get("vehicles_affected"),
        events_in_scope    = ec_raw.get("events_in_scope"),
        behaviors_affected = ec_raw.get("behaviors_affected"),
        workflows_sharing  = ec_raw.get("workflows_sharing"),
    )

    ap_raw = parsed.get("approval", {})
    try:
        tier = ApprovalTier(ap_raw.get("tier", "auto_execute"))
    except ValueError:
        tier = ApprovalTier.SENIOR_CSM
    approval = ApprovalDecision(
        tier   = tier,
        reason = ap_raw.get("reason", ""),
        sla    = ap_raw.get("sla", ""),
    )

    return ImpactReport(
        riskLevel        = _coerce_risk(parsed.get("riskLevel", "medium")),
        confidence       = _coerce_confidence(parsed.get("confidence", "medium")),
        summary          = parsed.get("summary", "Analysis complete."),
        impacts          = impacts,
        entity_counts    = entity_counts,
        warnings         = warnings,
        approval         = approval,
        data_gaps        = parsed.get("data_gaps", []),
        analysis_time_ms = elapsed_ms,
        bedrock_turns    = turns,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze(request: AnalyzeRequest, token: str) -> ImpactReport:
    """
    Run the Bedrock agentic loop for the given request.
    The token is forwarded to every downstream API call inside tool execution.
    """
    start_ms = int(time.time() * 1000)
    system_prompt = build_system_prompt()

    messages: list[dict] = [
        {"role": "user", "content": [{"text": _build_user_message(request)}]}
    ]

    logger.info("Starting Bedrock loop: changeType=%s groupId=%s",
                request.changeType, request.targetScope.groupId)

    turns = 0
    for turn in range(MAX_AGENT_TURNS):
        turns = turn + 1
        logger.info("Bedrock turn %d/%d", turns, MAX_AGENT_TURNS)

        response = _bedrock.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": system_prompt}],
            messages=messages,
            toolConfig={
                "tools": TOOL_DEFINITIONS,
                "toolChoice": {"auto": {}},
            },
            inferenceConfig={
                "maxTokens": 4096,
                "temperature": 0.0,   # deterministic for impact analysis
            },
        )

        stop_reason    = response["stopReason"]
        output_message = response["output"]["message"]
        messages.append(output_message)

        if stop_reason == "end_turn":
            # Extract the final text block
            final_text = "".join(
                block.get("text", "") for block in output_message["content"]
            )
            logger.info("Bedrock finished in %d turn(s). Parsing response.", turns)
            parsed       = _parse_response(final_text)
            elapsed      = int(time.time() * 1000) - start_ms
            impact_report = _to_impact_report(parsed, turns, elapsed)

            # Brain 2 — attach SageMaker recommendation
            recommendation = get_recommendation(request.changeType, request, impact_report)
            if recommendation:
                logger.info("Recommendation attached: type=%s", recommendation.get("type"))
                impact_report.recommendation = recommendation

            return impact_report

        if stop_reason == "tool_use":
            tool_use_blocks = [b for b in output_message["content"] if "toolUse" in b]
            tool_results    = _run_tools(tool_use_blocks, token)
            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        logger.warning("Unexpected stopReason: %s", stop_reason)
        break

    # Max turns exceeded
    elapsed = int(time.time() * 1000) - start_ms
    logger.error("Bedrock agent exceeded MAX_AGENT_TURNS (%d)", MAX_AGENT_TURNS)
    return ImpactReport(
        riskLevel        = RiskLevel.MEDIUM,
        confidence       = Confidence.LOW,
        summary          = f"Analysis incomplete — exceeded {MAX_AGENT_TURNS} agent turns.",
        approval         = ApprovalDecision(tier=ApprovalTier.SENIOR_CSM, reason="Incomplete analysis"),
        data_gaps        = ["Agent exceeded max turns before completing analysis"],
        analysis_time_ms = elapsed,
        bedrock_turns    = turns,
    )
