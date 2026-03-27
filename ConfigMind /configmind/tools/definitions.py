"""Bedrock tool definitions (toolSpec format for the converse API).

Each tool maps 1-to-1 with a function in dispatcher.py.
Bedrock reads these descriptions and decides autonomously which tools to call.

ALL TOOLS ARE REAL — no mocks:
  get_group_descendants         → Groups API   GET  /groups/{id}/descendants
  get_group_users_count         → Users API    POST /api/v1/core/users/memberships/search
  get_group_vehicles_count      → Vehicles API POST /public/admin-vehicle/vehicles/search
  get_group_devices_count       → Devices API  POST /api/devicelist/devices
  get_group_safety_events_count → Events API   GET  /api/safetyevents/events/v2
  get_workflow_for_group        → Workflow API GET  /v1.0/workflow/current/{id}
                                               GET  /v1/workflow/{id}/behaviors
  get_groups_sharing_workflow   → Workflow API GET  /v1/internal/company/{companyId}/workflow
  get_current_device_settings   → DeviceSettings API
  get_current_group_options     → GroupOption API
  get_group_permissions         → Permissions API
  read_feature_schema           → PCS *.feature.config.json on disk
  find_dependent_features       → PCS *.feature.config.json on disk
  check_feature_toggle          → FeatureToggle API
"""

TOOL_DEFINITIONS = [

    # ── Groups API ────────────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_group_descendants",
            "description": (
                "Get all descendant group IDs for a group. "
                "Calls GET /groups/{groupId}/descendants?depth=0 on the Groups API. "
                "Returns the count of descendant groups and a sample of their GUIDs. "
                "Use this for any change to understand how many child groups are in scope."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"}
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    # ── Users API ─────────────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_group_users_count",
            "description": (
                "Get the count of users (role=Coach, roleId=4) in a group. "
                "Calls POST /api/v1/core/users/memberships/search with groupIds=[groupId]. "
                "Returns total user count. Use for move_group and delete_group to understand "
                "how many users are managed under this group."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"}
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    # ── Vehicles API ──────────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_group_vehicles_count",
            "description": (
                "Get the vehicle count for a group including descendant groups. "
                "Calls POST /public/admin-vehicle/vehicles/search with groupRollDown=true. "
                "Returns total vehicle count. Use for move_group to understand blast radius."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"}
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    # ── Devices API ───────────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_group_devices_count",
            "description": (
                "Get the device (DriveCam hardware) count for a group including descendants. "
                "Calls POST /api/devicelist/devices with deviceTypes=[ER, AT, GEOTAB] and groupRollDown=true. "
                "Returns total device count. Use for move_group to understand physical device scope."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"}
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    # ── Safety Events API ─────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_group_safety_events_count",
            "description": (
                "Get count of safety events for a group over the last N days. "
                "Calls GET /api/safetyevents/events/v2 with eventGroupIds={groupId}. "
                "Returns total event count. Critical for move_group to understand audit trail risk — "
                "events are permanent compliance records that must stay associated with the group."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"},
                        "days": {
                            "type": "integer",
                            "description": "Look-back window in days (default 30)",
                            "default": 30
                        }
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    # ── Workflow Admin API ────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_workflow_for_group",
            "description": (
                "Get the workflow and its behaviors for a group. Makes two calls: "
                "(1) GET /v1.0/workflow/current/{groupId} → workflowId, "
                "(2) GET /v1/workflow/{groupId}/behaviors → [{behaviorId, score}]. "
                "Use for fatigue add/remove and PCS sub-feature changes that touch workflow entries."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"}
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    {
        "toolSpec": {
            "name": "get_groups_sharing_workflow",
            "description": (
                "Find all groups in the company that share the same workflow ID. "
                "Calls GET /v1/internal/company/{companyId}/workflow to retrieve all group-workflow "
                "mappings for the company, then filters by workflowId. "
                "Returns the list of groups using the same workflow — critical for cascade analysis."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "workflowId": {
                            "type": "string",
                            "description": "The workflow UUID (from get_workflow_for_group)"
                        },
                        "companyId": {
                            "type": "integer",
                            "description": "Company ID (from targetScope.companyId)"
                        }
                    },
                    "required": ["workflowId", "companyId"]
                }
            }
        }
    },

    # ── Device Settings API ───────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_current_device_settings",
            "description": (
                "Get current device setting values for a group. "
                "Calls GET /settings/group/{groupId}?name=X&name=Y on the Device Settings API. "
                "Use to check shared prerequisite settings like 'Enable Master Video Services'. "
                "Returns {settingName: currentValue} for each requested setting."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {
                            "type": "string",
                            "description": "The group UUID"
                        },
                        "settingNames": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Device setting names to query"
                        }
                    },
                    "required": ["groupId", "settingNames"]
                }
            }
        }
    },

    # ── Group Options API ─────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_current_group_options",
            "description": (
                "Get current group option values for a group. "
                "Calls GET /groupOptions?GroupId={groupId}&Keys={k1,k2}. "
                "Use to check alert thresholds — e.g. GO 381 controls Food & Drink event rate. "
                "Lower AlertPatt value = more events (inverse). Returns {keyId: currentValue}."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {
                            "type": "string",
                            "description": "The group UUID"
                        },
                        "keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Group option key IDs (e.g. ['381', '382', '417'])"
                        }
                    },
                    "required": ["groupId", "keys"]
                }
            }
        }
    },

    # ── Permissions API ───────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "get_group_permissions",
            "description": (
                "Check PCS permissions for a group via POST /permissions/groupPermissions. "
                "Returns whether the group has VIEW_PROGRAM_CONFIGURATION and EDIT_PROGRAM_CONFIGURATION. "
                "Use to verify access before reporting PCS impact."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "groupId": {"type": "string", "description": "The group UUID"},
                        "permissionKeys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Permission keys to check",
                            "default": ["VIEW_PROGRAM_CONFIGURATION", "EDIT_PROGRAM_CONFIGURATION"]
                        }
                    },
                    "required": ["groupId"]
                }
            }
        }
    },

    # ── PCS Feature Config files (read from disk) ─────────────────────────────

    {
        "toolSpec": {
            "name": "read_feature_schema",
            "description": (
                "Read a PCS feature config JSON file from disk. Returns all settings the feature "
                "controls: subFeatures, enablementSettings, configurableSettings with settingSource "
                "(deviceSetting/groupOption/workflow), settingIds, and $comment fields. "
                "Call this FIRST for any pcs.* change to understand the full dependency graph."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "featureFileName": {
                            "type": "string",
                            "description": (
                                "Feature name without path/extension. "
                                "Options: foodanddrink, smoking, handhelddevice, inattentive, "
                                "noseatbelt, lensobstruction, criticaldistance, followingdistance, "
                                "lanedeparture, rollingstop, redlight"
                            )
                        }
                    },
                    "required": ["featureFileName"]
                }
            }
        }
    },

    {
        "toolSpec": {
            "name": "find_dependent_features",
            "description": (
                "Scan ALL PCS feature config files to find every feature using a given setting. "
                "Critical for shared prerequisites — e.g. 'Enable Master Video Services' is used "
                "by 18 sub-features across 6 features. Disabling it breaks all of them. "
                "Use when a shared device setting or group option is being changed."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "settingId": {
                            "type": "string",
                            "description": "The setting ID to search (e.g. 'Enable Master Video Services')"
                        },
                        "settingSource": {
                            "type": "string",
                            "enum": ["deviceSetting", "groupOption", "workflow"],
                            "description": "The setting source type"
                        }
                    },
                    "required": ["settingId", "settingSource"]
                }
            }
        }
    },

    # ── Feature Toggle API ────────────────────────────────────────────────────

    {
        "toolSpec": {
            "name": "check_feature_toggle",
            "description": (
                "Check whether a named feature toggle is active. "
                "Calls GET {FEATURE_TOGGLE_URL}/feature-toggles/{toggleName}. "
                "Use when a PCS feature config references an activationFeatureToggle — "
                "if the toggle is off the feature cannot be enabled regardless of other settings."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "toggleName": {
                            "type": "string",
                            "description": "The feature toggle name (from activationFeatureToggle field)"
                        },
                        "companyId": {
                            "type": "integer",
                            "description": "Optional company ID for company-scoped toggle lookup"
                        }
                    },
                    "required": ["toggleName"]
                }
            }
        }
    },

]

# Tools that require PCS feature config files on disk
_PCS_TOOL_NAMES = {"read_feature_schema", "find_dependent_features"}


def get_tool_definitions(pcs_available: bool = True) -> list:
    """Return tool definitions, excluding PCS disk tools if configs aren't present."""
    if pcs_available:
        return TOOL_DEFINITIONS
    return [t for t in TOOL_DEFINITIONS if t["toolSpec"]["name"] not in _PCS_TOOL_NAMES]
