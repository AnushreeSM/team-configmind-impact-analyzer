"""ConfigMind v1.0 — FastAPI application.

Single endpoint: POST /analyze
  - Reads Authorization: Bearer <token> from header
  - Forwards token to every downstream service call
  - Runs single Bedrock agentic loop
  - Returns structured ImpactReport
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from configmind.models.impact import AnalyzeRequest, ImpactReport
from configmind.agent.bedrock_agent import analyze
from configmind.config import (
    BEDROCK_MODEL_ID, BEDROCK_REGION,
    USERS_SEARCH_URL, VEHICLES_SEARCH_URL, DEVICES_SEARCH_URL, EVENTS_SEARCH_URL,
    WORKFLOW_URL,
)

_bearer = HTTPBearer(auto_error=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger("configmind")

app = FastAPI(
    title="ConfigMind",
    version="1.0.0",
    description=(
        "AI-Powered Impact Analysis — intercepts admin actions, "
        "queries downstream services with your token, predicts blast radius."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post(
    "/analyze",
    response_model=ImpactReport,
    summary="Analyze the blast radius of a proposed configuration change",
    description=(
        "Pass **Authorization: Bearer &lt;token&gt;** in the header. "
        "The token is forwarded to all downstream service calls "
        "(Groups, Device Settings, Group Options, Workflow Admin, Permissions, "
        "Feature Toggle, Vehicles*, Events*). "
        "Bedrock autonomously selects and calls tools based on the changeType."
    ),
)
def analyze_change(
    request: AnalyzeRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> ImpactReport:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required. Click 'Authorize' in Swagger UI and enter your token.",
        )
    token = credentials.credentials

    logger.info(
        "POST /analyze  changeType=%s  groupId=%s  companyId=%s",
        request.changeType,
        request.targetScope.groupId,
        request.targetScope.companyId,
    )
    return analyze(request, token)


@app.get("/health", summary="Health check")
def health() -> dict:
    return {
        "status": "ok",
        "service": "configmind",
        "version": "1.0.0",
        "bedrock": {
            "region": BEDROCK_REGION,
            "model": BEDROCK_MODEL_ID,
        },
        "tools": [
            {"name": "get_group_descendants",           "endpoint": f"{WORKFLOW_URL.replace('workflow-admin-api', 'group-api')}/groups/{{id}}/descendants",   "status": "real"},
            {"name": "get_group_users_count",           "endpoint": USERS_SEARCH_URL,     "status": "real"},
            {"name": "get_group_vehicles_count",        "endpoint": VEHICLES_SEARCH_URL,  "status": "real"},
            {"name": "get_group_devices_count",         "endpoint": DEVICES_SEARCH_URL,   "status": "real"},
            {"name": "get_group_safety_events_count",   "endpoint": EVENTS_SEARCH_URL,    "status": "real"},
            {"name": "get_workflow_for_group",          "endpoint": f"{WORKFLOW_URL}/v1.0/workflow/current/{{id}} + /v1/workflow/{{id}}/behaviors", "status": "real"},
            {"name": "get_groups_sharing_workflow",     "endpoint": f"{WORKFLOW_URL}/v1/internal/company/{{companyId}}/workflow", "status": "real"},
            {"name": "get_current_device_settings",     "endpoint": "Device Settings API /settings/group/{id}", "status": "real"},
            {"name": "get_current_group_options",       "endpoint": "Group Options API /groupOptions",          "status": "real"},
            {"name": "get_group_permissions",           "endpoint": "Permissions API /permissions/groupPermissions", "status": "real"},
            {"name": "read_feature_schema",             "endpoint": "PCS *.feature.config.json on disk",        "status": "real"},
            {"name": "find_dependent_features",         "endpoint": "PCS *.feature.config.json on disk",        "status": "real"},
        ],
    }


@app.get("/demos", summary="List example request payloads")
def list_demos() -> dict:
    return {
        "demos": [
            {
                "id": "move_group",
                "title": "Move Group to New Parent",
                "description": "18 downstream services notified via Kafka. ~8h propagation. Vehicles + events counted.",
                "changeType": "groups.move_group",
                "payloadFile": "tests/payloads/move_group.json",
            },
            {
                "id": "fatigue_add_group",
                "title": "Add Group to Fatigue Behavior",
                "description": "Workflow shared with N groups — all get the new behavior.",
                "changeType": "groups.fatigue.add_group",
                "payloadFile": "tests/payloads/fatigue_add_group.json",
            },
            {
                "id": "fatigue_remove_group",
                "title": "Remove Group from Fatigue (VOYAGE-1988)",
                "description": "Bug: removing 1 group deletes behavior for ALL groups on workflow.",
                "changeType": "groups.fatigue.remove_group",
                "payloadFile": "tests/payloads/fatigue_remove_group.json",
            },
            {
                "id": "pcs_enable_subfeature",
                "title": "Enable PCS Sub-Feature (Food & Drink Events)",
                "description": "Schema read → device settings + group options + workflow cascade.",
                "changeType": "pcs.enable_sub_feature",
                "payloadFile": "tests/payloads/pcs_enable_subfeature.json",
            },
            {
                "id": "pcs_disable_subfeature",
                "title": "Disable PCS Sub-Feature (Master Video Services)",
                "description": "Shared prerequisite cascade — breaks 6 in-cab features.",
                "changeType": "pcs.disable_sub_feature",
                "payloadFile": "tests/payloads/pcs_disable_subfeature.json",
            },
            {
                "id": "pcs_change_threshold",
                "title": "Change Alert Threshold (GO 381 Food & Drink)",
                "description": "Lower threshold = more events. Ontology: threshold_controls_volume.",
                "changeType": "pcs.change_threshold",
                "payloadFile": "tests/payloads/pcs_change_threshold.json",
            },
        ]
    }
