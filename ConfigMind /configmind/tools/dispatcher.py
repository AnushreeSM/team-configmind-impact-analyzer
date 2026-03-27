"""ConfigMind — Tool dispatcher.

Maps every Bedrock tool name to a real downstream API call.
The caller's Bearer token is forwarded on every request.

ENDPOINT REFERENCE
──────────────────
Groups:
  GET  {GROUP_API_URL}/groups/{groupId}/descendants?depth=0
       → [guid, guid, ...]   (descendant group IDs)

Users:
  POST {USERS_SEARCH_URL}
       body: {groupIds:[id], roleIds:[4], pageNumber:1, pageSize:1, ...}
       → {totalRecords: N, ...}

Vehicles:
  POST {VEHICLES_SEARCH_URL}
       body: {groupIds:[id], groupRollDown:true, pageSize:1, ...}
       → {totalRecords: N, ...}  or  {total: N}

Devices:
  POST {DEVICES_SEARCH_URL}
       body: {groupIds:[id], deviceTypes:[ER,AT,GEOTAB], groupRollDown:true, pageSize:1}
       → {totalRecords: N, ...}  or  {total: N}

Safety Events:
  GET  {EVENTS_SEARCH_URL}?eventGroupIds={id}&startDate=YYYY-M-D&endDate=YYYY-M-D
       &pageNumber=1&pageSize=1&includeAllDriverAndCoachEvents=true
       &sortField=RecordDateLocal&sortDirection=desc&userLanguage=en-GB
       → {totalRecords: N, ...}

Workflow Admin (from swagger):
  GET  {WORKFLOW_URL}/v1.0/workflow/current/{groupId}
       → {WorkflowId, WorkflowRulesCoachingSetId, WorkflowBehaviorsSetId}
  GET  {WORKFLOW_URL}/v1/workflow/{groupId}/behaviors
       → [{BehaviorId: int, Score: float}]
  GET  {WORKFLOW_URL}/v1/internal/company/{companyId}/workflow
       → [{WorkflowId, GroupId, WorkflowName, WorkflowBehaviors, WorkflowCoachingRules, ...}]

Device Settings:
  GET  {DEVICE_SETTINGS_URL}/settings/group/{groupId}?name=X&name=Y
       → [{Name, Value}]

Group Options:
  GET  {GROUP_OPTION_URL}/groupOptions?GroupId={id}&Keys={k1,k2}
       → [{Key, Value}]

Permissions:
  POST {PERMISSIONS_URL}/permissions/groupPermissions
       body: {PermissionKeys:[...], GroupIds:[id], ExplicitUserGroupsOnly:false}
       → {groupId: [permissionKey, ...]}

Feature Toggle:
  GET  {FEATURE_TOGGLE_URL}/feature-toggles/{name}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import httpx

from configmind.config import (
    DEVICE_SETTINGS_URL,
    DEVICES_SEARCH_URL,
    EVENTS_SEARCH_URL,
    FEATURE_TOGGLE_URL,
    GROUP_API_URL,
    GROUP_OPTION_URL,
    HTTP_TIMEOUT,
    PCS_CONFIGS_PATH,
    PERMISSIONS_URL,
    USERS_SEARCH_URL,
    VEHICLES_SEARCH_URL,
    WORKFLOW_URL,
)

logger = logging.getLogger("configmind.dispatcher")

_PCS_PERMISSION_KEYS = ["VIEW_PROGRAM_CONFIGURATION", "EDIT_PROGRAM_CONFIGURATION"]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(url: str, token: str, params: Any = None) -> Any:
    with httpx.Client(timeout=HTTP_TIMEOUT) as c:
        r = c.get(url, params=params, headers=_headers(token))
        r.raise_for_status()
        return r.json()


def _post(url: str, token: str, body: Any) -> Any:
    with httpx.Client(timeout=HTTP_TIMEOUT) as c:
        r = c.post(url, json=body, headers=_headers(token))
        r.raise_for_status()
        return r.json()


def _extract_total(data: Any, source_label: str) -> Optional[int]:
    """Extract a total/count from various response shapes."""
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("totalRecords", "total", "count", "totalCount", "Total", "TotalRecords", "itemCount", "eventCount"):
            if key in data and data[key] is not None:
                return int(data[key])
        # Try items/data array length as fallback
        for key in ("items", "data", "records", "results"):
            if key in data and isinstance(data[key], list):
                return len(data[key])
    logger.warning("_extract_total: could not parse count from %s response: %s",
                   source_label, str(data)[:200])
    return None


# ── Groups API ────────────────────────────────────────────────────────────────

def get_group_descendants(group_id: str, token: str) -> dict[str, Any]:
    """GET /groups/{groupId}/descendants?depth=0 → list of descendant GUIDs."""
    url = f"https://cloud-lytx-aws-group-api-dev.aws.drivecaminc.xyz/groups/{group_id}/descendants"
    logger.info("Calling Groups API for groupId=%s", group_id)
    try:
        guid_list: list[str] = _get(url, token, params={"depth": 0})
        logger.info("Groups API returned %d descendants for groupId=%s", len(guid_list), group_id)
        logger.debug("Descendant URL: %s", url)
        return {
            "groupId": group_id,
            "descendantGroupCount": len(guid_list),
            "descendantGroupIds": guid_list[:20],
            "source": "group_api",
        }
    except Exception as exc:
        logger.warning("get_group_descendants(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "group_api_error"}


# ── Users API ─────────────────────────────────────────────────────────────────

def get_group_users_count(group_id: str, token: str) -> dict[str, Any]:
    """
    POST /api/v1/core/users/memberships/search
    body: {groupIds:[groupId], roleIds:[4], pageSize:1, ...}
    """
    body = {
        "groupIds": [group_id],
        "roleIds": [4],
        "userStatusId": "",
        "searchText": "",
        "pageNumber": 1,
        "pageSize": 1,
        "sortDirection": "asc",
        "isUserCSVExport": False,
    }
    try:
        data = _post(USERS_SEARCH_URL, token, body)
        total = _extract_total(data, "users_search")
        return {
            "groupId": group_id,
            "userCount": total,
            "source": "users_api",
        }
    except Exception as exc:
        logger.warning("get_group_users_count(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "users_api_error"}


# ── Vehicles API ──────────────────────────────────────────────────────────────

def get_group_vehicles_count(group_id: str, token: str) -> dict[str, Any]:
    """
    POST /public/admin-vehicle/vehicles/search
    body: {groupIds:[groupId], groupRollDown:true, pageSize:1, ...}
    """
    body = {
        "groupRollDown": True,
        "sortType": "name",
        "sortDirection": "ASC",
        "groupIds": [group_id],
        "pageSize": 1,
    }
    try:
        data = _post(VEHICLES_SEARCH_URL, token, body)
        total = _extract_total(data, "vehicles_search")
        return {
            "groupId": group_id,
            "vehicleCount": total,
            "includesDescendants": True,
            "source": "vehicles_api",
        }
    except Exception as exc:
        logger.warning("get_group_vehicles_count(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "vehicles_api_error"}


# ── Devices API ───────────────────────────────────────────────────────────────

def get_group_devices_count(group_id: str, token: str) -> dict[str, Any]:
    """
    POST /api/devicelist/devices
    body: {groupIds:[groupId], deviceTypes:[ER,AT,GEOTAB], groupRollDown:true, pageSize:1}
    """
    body = {
        "pageSize": 1,
        "sortType": "lastCommunicationDate",
        "sortDirection": "desc",
        "groupIds": [group_id],
        "deviceTypes": ["ER", "AT", "GEOTAB"],
        "groupRollDown": True,
        "showCloudDevices": False,
    }
    try:
        data = _post(DEVICES_SEARCH_URL, token, body)
        total = _extract_total(data, "devices_search")
        return {
            "groupId": group_id,
            "deviceCount": total,
            "deviceTypes": ["ER", "AT", "GEOTAB"],
            "includesDescendants": True,
            "source": "devices_api",
        }
    except Exception as exc:
        logger.warning("get_group_devices_count(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "devices_api_error"}


# ── Safety Events API ─────────────────────────────────────────────────────────

def get_group_safety_events_count(group_id: str, days: int, token: str) -> dict[str, Any]:
    """
    GET /api/safetyevents/events/v2
    ?eventGroupIds={groupId}&startDate=YYYY-M-D&endDate=YYYY-M-D
    &pageNumber=1&pageSize=1&includeAllDriverAndCoachEvents=true
    &sortField=RecordDateLocal&sortDirection=desc&userLanguage=en-GB
    """
    end_date   = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    # API uses YYYY-M-D (no zero-padding) as shown in the example URL
    fmt = lambda d: f"{d.year}-{d.month}-{d.day}"

    params = {
        "eventGroupIds": group_id,
        "startDate": fmt(start_date),
        "endDate": fmt(end_date),
        "pageNumber": 1,
        "pageSize": 1,
        "includeAllDriverAndCoachEvents": "true",
        "sortField": "RecordDateLocal",
        "sortDirection": "desc",
        "userLanguage": "en-GB",
    }
    try:
        data = _get(EVENTS_SEARCH_URL, token, params=params)
        total = _extract_total(data, "events_v2")
        return {
            "groupId": group_id,
            "eventCount": total,
            "periodDays": days,
            "startDate": fmt(start_date),
            "endDate": fmt(end_date),
            "source": "events_api",
        }
    except Exception as exc:
        logger.warning("get_group_safety_events_count(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "events_api_error"}


# ── Workflow Admin API ────────────────────────────────────────────────────────

def get_workflow_for_group(group_id: str, token: str) -> dict[str, Any]:
    """
    1. GET /v1.0/workflow/current/{groupId}
       → {WorkflowId, WorkflowRulesCoachingSetId, WorkflowBehaviorsSetId}
    2. GET /v1/workflow/{groupId}/behaviors
       → [{BehaviorId: int, Score: float}]
    """
    try:
        # Step 1: get workflow IDs
        logger.info("Calling Workflow Admin API for url=%s", f"{WORKFLOW_URL}/v1.0/workflow/current/{group_id}")
        ids = _get(f"{WORKFLOW_URL}/v1.0/workflow/current/{group_id}", token)
        workflow_id: str = ids.get("WorkflowId") or ids.get("workflowId") or ids.get("workflow_id") or ids.get("Id") or ids.get("id")
        if not workflow_id:
            raise KeyError("WorkflowId")

        # Step 2: get behaviors (swagger: GET /v{version}/workflow/{groupId}/behaviors)
        behaviors_raw: list[dict] = _get(
            f"https://cloud-lytx-safety-workflow-admin-api-dev.aws.drivecaminc.xyz/v1/workflow/{group_id}/behaviors", token
        )
        behaviors = [
            {
                "behaviorId": f"Behavior-{b.get('BehaviorId', 'unknown')}",
                "score": b.get("Score"),
            }
            for b in behaviors_raw
            if b.get("BehaviorId") is not None
        ]

        return {
            "groupId": group_id,
            "workflowId": workflow_id,
            "workflowRulesCoachingSetId": ids.get("WorkflowRulesCoachingSetId"),
            "workflowBehaviorsSetId": ids.get("WorkflowBehaviorsSetId"),
            "behaviorCount": len(behaviors),
            "behaviors": behaviors,
            "source": "workflow_api",
        }
    except Exception as exc:
        logger.warning("get_workflow_for_group(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "workflow_api_error"}


def get_groups_sharing_workflow(workflow_id: str, company_id: int, token: str) -> dict[str, Any]:
    """
    GET /v1/internal/company/{companyId}/workflow
    Returns all group-workflow mappings for the company.
    We filter by workflowId to find all groups sharing it.
    """
    url = f"{WORKFLOW_URL}/v1/internal/company/{company_id}/workflow"
    try:
        data = _get(url, token)

        # Response may be a list or paginated object
        all_mappings: list[dict] = []
        if isinstance(data, list):
            all_mappings = data
        elif isinstance(data, dict):
            all_mappings = (
                data.get("items") or data.get("data") or
                data.get("workflows") or data.get("results") or []
            )

        # Filter to groups sharing this exact workflowId
        sharing = [
            {
                "groupId":      m.get("GroupId") or m.get("groupId"),
                "workflowName": m.get("WorkflowName") or m.get("workflowName"),
            }
            for m in all_mappings
            if (m.get("WorkflowId") or m.get("workflowId")) == workflow_id
        ]

        return {
            "workflowId": workflow_id,
            "companyId": company_id,
            "sharingGroupCount": len(sharing),
            "sharingGroups": sharing,
            "totalMappingsScanned": len(all_mappings),
            "source": "workflow_api",
        }
    except Exception as exc:
        logger.warning("get_groups_sharing_workflow(%s, company=%s) failed: %s",
                       workflow_id, company_id, exc)
        return {
            "error": str(exc),
            "workflowId": workflow_id,
            "companyId": company_id,
            "source": "workflow_api_error",
        }


# ── Device Settings API ───────────────────────────────────────────────────────

def get_current_device_settings(group_id: str, setting_names: list[str], token: str) -> dict[str, Any]:
    """GET /settings/group/{groupId}?name=X&name=Y → [{Name, Value}]."""
    url = f"{DEVICE_SETTINGS_URL}/settings/group/{group_id}"
    try:
        params = [("name", n) for n in setting_names]
        with httpx.Client(timeout=HTTP_TIMEOUT) as c:
            r = c.get(url, params=params, headers=_headers(token))
            r.raise_for_status()
            raw: list[dict] = r.json()
        current_values = {item["Name"]: item["Value"] for item in raw}
        return {
            "groupId": group_id,
            "currentValues": current_values,
            "notFound": [n for n in setting_names if n not in current_values],
            "source": "device_settings_api",
        }
    except Exception as exc:
        logger.warning("get_current_device_settings(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "device_settings_api_error"}


# ── Group Options API ─────────────────────────────────────────────────────────

def get_current_group_options(group_id: str, keys: list[str], token: str) -> dict[str, Any]:
    """GET /groupOptions?GroupId={groupId}&Keys={k1,k2} → [{Key, Value}]."""
    url = f"{GROUP_OPTION_URL}/groupOptions"
    try:
        params = {"GroupId": group_id, "Keys": ",".join(str(k) for k in keys)}
        raw: list[dict] = _get(url, token, params=params)
        current_values = {str(item["Key"]): item["Value"] for item in raw}
        return {
            "groupId": group_id,
            "currentValues": current_values,
            "note": "0 = feature disabled / threshold not set",
            "source": "group_option_api",
        }
    except Exception as exc:
        logger.warning("get_current_group_options(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "group_option_api_error"}


# ── Permissions API ───────────────────────────────────────────────────────────

def get_group_permissions(group_id: str, permission_keys: list[str], token: str) -> dict[str, Any]:
    """POST /permissions/groupPermissions → {groupId: [permissionKey, ...]}."""
    url = f"{PERMISSIONS_URL}/permissions/groupPermissions"
    keys = permission_keys or _PCS_PERMISSION_KEYS
    try:
        body = {
            "PermissionKeys": keys,
            "GroupIds": [group_id],
            "ExplicitUserGroupsOnly": False,
        }
        raw: dict = _post(url, token, body)
        granted = raw.get(group_id) or raw.get(group_id.lower()) or []
        return {
            "groupId": group_id,
            "grantedPermissions": granted,
            "hasViewAccess": "VIEW_PROGRAM_CONFIGURATION" in granted,
            "hasEditAccess": "EDIT_PROGRAM_CONFIGURATION" in granted,
            "source": "permissions_api",
        }
    except Exception as exc:
        logger.warning("get_group_permissions(%s) failed: %s", group_id, exc)
        return {"error": str(exc), "groupId": group_id, "source": "permissions_api_error"}


# ── PCS Feature Config files ──────────────────────────────────────────────────

def _load_pcs_configs() -> dict[str, dict]:
    configs: dict[str, dict] = {}
    p = Path(PCS_CONFIGS_PATH)
    if not p.exists():
        logger.warning("PCS_CONFIGS_PATH does not exist: %s", p)
        return configs
    for f in p.glob("*.feature.config.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8-sig"))
            key = f.stem.replace(".feature.config", "").lower()
            configs[key] = raw
        except Exception as exc:
            logger.warning("Failed to load %s: %s", f, exc)
    return configs


def read_feature_schema(feature_file_name: str) -> dict[str, Any]:
    configs = _load_pcs_configs()
    name = (feature_file_name
            .replace(".feature.config.json", "")
            .replace(".feature.config", "")
            .lower())
    raw = configs.get(name)
    if raw:
        sub_features = raw.get("subFeatures", [])
        all_settings = []
        for sf in sub_features:
            sf_name = sf.get("displayLabelKey", sf.get("id", ""))
            for s in sf.get("enablementSettings", []) + sf.get("configurableSettings", []):
                all_settings.append({
                    "subFeature":    sf_name,
                    "settingSource": s.get("settingSource"),
                    "settingId":     s.get("settingId"),
                    "comment":       s.get("$comment", ""),
                    "isConst":       s.get("const"),
                })
        return {
            "found": True,
            "featureName": raw.get("displayLabelKey", name),
            "featureId": raw.get("featureId"),
            "productPermission": raw.get("productPermission"),
            "activationFeatureToggle": raw.get("activationFeatureToggle"),
            "subFeatureCount": len(sub_features),
            "subFeatures": [sf.get("displayLabelKey", sf.get("id")) for sf in sub_features],
            "allSettings": all_settings,
            "availableFeatures": list(configs.keys()),
            "source": "pcs_feature_configs",
        }
    return {
        "found": False,
        "requestedName": feature_file_name,
        "error": f"Feature '{name}' not found",
        "availableFeatures": list(configs.keys()),
        "source": "pcs_feature_configs",
    }


def find_dependent_features(setting_id: str, setting_source: str) -> dict[str, Any]:
    try:
        configs = _load_pcs_configs()
        if not configs:
            return {
                "settingId": setting_id,
                "settingSource": setting_source,
                "dependentFeatureCount": 0,
                "dependentFeatures": [],
                "note": "PCS feature config files not available on this host",
                "source": "pcs_feature_configs_unavailable",
            }
        hits = []
        for file_name, raw in configs.items():
            feature_name = raw.get("displayLabelKey", file_name)
            for sf in raw.get("subFeatures", []):
                sf_name = sf.get("displayLabelKey", "")
                for s in sf.get("enablementSettings", []) + sf.get("configurableSettings", []):
                    if (s.get("settingId") == setting_id and
                            s.get("settingSource") == setting_source):
                        hits.append({
                            "featureName":    feature_name,
                            "subFeatureName": sf_name,
                            "featureFile":    file_name,
                            "isConst":        s.get("const"),
                        })
        return {
            "settingId": setting_id,
            "settingSource": setting_source,
            "dependentFeatureCount": len(hits),
            "dependentFeatures": hits,
            "note": "All listed features are affected if this shared setting is changed",
            "source": "pcs_feature_configs",
        }
    except Exception as exc:
        return {"error": str(exc), "settingId": setting_id, "source": "pcs_feature_configs_error"}


# ── Feature Toggle API ────────────────────────────────────────────────────────

def check_feature_toggle(toggle_name: str, company_id: Optional[int], token: str) -> dict[str, Any]:
    patterns = [
        f"{FEATURE_TOGGLE_URL}/feature-toggles/{toggle_name}",
        f"{FEATURE_TOGGLE_URL}/v1/feature-toggles/{toggle_name}",
        f"{FEATURE_TOGGLE_URL}/toggles/{toggle_name}",
    ]
    last_exc: Exception | None = None
    for url in patterns:
        try:
            params = {"companyId": company_id} if company_id else None
            data = _get(url, token, params=params)
            return {
                "toggleName": toggle_name,
                "isActive": data.get("isActive") or data.get("active") or data.get("value"),
                "raw": data,
                "source": "feature_toggle_api",
            }
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                last_exc = exc
                continue
            return {"error": f"HTTP {exc.response.status_code}", "toggleName": toggle_name,
                    "source": "feature_toggle_api_error"}
        except Exception as exc:
            last_exc = exc
    return {"error": str(last_exc), "toggleName": toggle_name, "source": "feature_toggle_api_error"}


# ── Master dispatcher ─────────────────────────────────────────────────────────

def execute_tool(tool_name: str, tool_input: dict, token: str) -> dict[str, Any]:
    """Route a Bedrock tool_use call to the correct downstream function."""
    try:
        if tool_name == "get_group_descendants":
            return get_group_descendants(tool_input["groupId"], token)

        if tool_name == "get_group_users_count":
            return get_group_users_count(tool_input["groupId"], token)

        if tool_name == "get_group_vehicles_count":
            return get_group_vehicles_count(tool_input["groupId"], token)

        if tool_name == "get_group_devices_count":
            return get_group_devices_count(tool_input["groupId"], token)

        if tool_name == "get_group_safety_events_count":
            return get_group_safety_events_count(
                tool_input["groupId"], tool_input.get("days", 30), token
            )

        if tool_name == "get_workflow_for_group":
            return get_workflow_for_group(tool_input["groupId"], token)

        if tool_name == "get_groups_sharing_workflow":
            return get_groups_sharing_workflow(
                tool_input["workflowId"], tool_input["companyId"], token
            )

        if tool_name == "get_current_device_settings":
            return get_current_device_settings(
                tool_input["groupId"], tool_input["settingNames"], token
            )

        if tool_name == "get_current_group_options":
            return get_current_group_options(
                tool_input["groupId"], tool_input["keys"], token
            )

        if tool_name == "get_group_permissions":
            return get_group_permissions(
                tool_input["groupId"],
                tool_input.get("permissionKeys", _PCS_PERMISSION_KEYS),
                token,
            )

        if tool_name == "read_feature_schema":
            return read_feature_schema(tool_input["featureFileName"])

        if tool_name == "find_dependent_features":
            return find_dependent_features(
                tool_input["settingId"], tool_input["settingSource"]
            )

        if tool_name == "check_feature_toggle":
            return check_feature_toggle(
                tool_input["toggleName"],
                tool_input.get("companyId"),
                token,
            )

        return {"error": f"Unknown tool: {tool_name}"}

    except KeyError as exc:
        return {"error": f"Missing required parameter {exc} for tool '{tool_name}'"}
    except Exception as exc:
        logger.error("execute_tool(%s) unexpected error: %s", tool_name, exc)
        return {"error": f"Tool '{tool_name}' raised: {exc}"}
