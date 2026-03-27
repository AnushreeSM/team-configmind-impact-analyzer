"""ConfigMind — centralised configuration.

All service URLs auto-derive from LYTX_ENV if the specific URL var is not set.
This matches the same env pattern used by PCS appsettings.Development.json.
"""
import os
from dotenv import load_dotenv

load_dotenv()  # load .env before reading any os.getenv calls

# Lytx environment suffix (dev / staging / prod)
_ENV = os.getenv("LYTX_ENV", "dev")


def _url(service_slug: str, env_var: str) -> str:
    """Return explicit env var value, or build from naming convention."""
    return os.getenv(env_var, f"https://{service_slug}-{_ENV}.aws.drivecaminc.xyz")


# ── PCS-sourced service URLs (from appsettings.Development.json) ──────────────
GROUP_API_URL       = _url("cloud-lytx-aws-group-api",               "GROUP_API_URL")
DEVICE_SETTINGS_URL = _url("cloud-lytx-devicesettings-api",      "DEVICE_SETTINGS_URL")
GROUP_OPTION_URL    = _url("cloud-lytx-aws-groupoption-service",  "GROUP_OPTION_URL")
WORKFLOW_URL        = _url("cloud-lytx-safety-workflow-admin-api","WORKFLOW_URL")
PERMISSIONS_URL     = _url("cloud-lytx-core-permissions-service", "PERMISSIONS_URL")
FEATURE_TOGGLE_URL  = _url("cloud-lytx-featuretoggle-handler",    "FEATURE_TOGGLE_URL")

# ── Real endpoints confirmed by user ─────────────────────────────────────────
# Users count:  POST /api/v1/core/users/memberships/search
USERS_SEARCH_URL   = os.getenv(
    "USERS_SEARCH_URL",
    "https://drivecam-int2.drivecaminc.xyz/api/v1/core/users/memberships/search",
)
# Vehicle count: POST /public/admin-vehicle/vehicles/search
VEHICLES_SEARCH_URL = os.getenv(
    "VEHICLES_SEARCH_URL",
    "https://api-dev.aws.drivecaminc.xyz/public/admin-vehicle/vehicles/search",
)
# Device count:  POST /api/devicelist/devices
DEVICES_SEARCH_URL  = os.getenv(
    "DEVICES_SEARCH_URL",
    "https://api-dev.aws.drivecaminc.xyz/api/devicelist/devices",
)
# Event count:   GET /api/safetyevents/events/v2
EVENTS_SEARCH_URL   = os.getenv(
    "EVENTS_SEARCH_URL",
    "https://api-dev.aws.drivecaminc.xyz/api/safetyevents/events/v2",
)

# ── Bedrock ───────────────────────────────────────────────────────────────────
BEDROCK_REGION   = os.getenv("BEDROCK_REGION",   "us-west-2")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6-20250514-v1:0")
MAX_AGENT_TURNS  = int(os.getenv("MAX_AGENT_TURNS", "10"))

# ── PCS feature config files (read from disk) ─────────────────────────────────
PCS_CONFIGS_PATH = os.getenv(
    "PCS_CONFIGS_PATH",
    r"c:\Repo\ProgramConfig\programconfiguration-service\src"
    r"\Lytx.ProgramConfiguration.Service\Configurations\Features",
)

# ── HTTP ──────────────────────────────────────────────────────────────────────
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "15.0"))
