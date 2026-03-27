"""ConfigMind — request / response models."""
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


class Confidence(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class ApprovalTier(str, Enum):
    AUTO_EXECUTE = "auto_execute"
    SENIOR_CSM   = "senior_csm"
    HOTL         = "hotl"
    HARD_BLOCK   = "hard_block"


# ── Request ───────────────────────────────────────────────────────────────────

class TargetScope(BaseModel):
    groupId:   str
    groupName: str = ""
    companyId: int = 0


class ProposedChange(BaseModel):
    """A single atomic change within the request."""
    entityType:  str  = ""   # e.g. subFeature, configurableSetting, group
    entityId:    str  = ""
    entityName:  str  = ""
    field:       str  = ""   # e.g. isEnabled, value, parentId
    currentValue: Any = None
    proposedValue: Any = None
    params:      dict = {}   # extra context (featureFileName, behaviorName, etc.)


class AnalyzeRequest(BaseModel):
    """
    Payload posted to POST /analyze.

    changeType examples:
      groups.move_group
      groups.fatigue.add_group
      groups.fatigue.remove_group
      pcs.enable_sub_feature
      pcs.disable_sub_feature
      pcs.change_threshold
    """
    changeType:      str
    targetScope:     TargetScope
    proposedChanges: list[ProposedChange] = []


# ── Response ──────────────────────────────────────────────────────────────────

class ImpactItem(BaseModel):
    area:        str
    change:      str
    effect:      str
    risk:        RiskLevel
    detail:      str
    confidence:  Confidence = Confidence.HIGH
    data_source: str        = ""


class Warning(BaseModel):
    type:       str
    severity:   RiskLevel
    message:    str
    bug_ref:    str = ""
    data_source: str = ""


class EntityCounts(BaseModel):
    groups_affected:   Optional[int] = None
    devices_affected:  Optional[int] = None
    vehicles_affected: Optional[int] = None
    events_in_scope:   Optional[int] = None
    behaviors_affected: Optional[int] = None
    workflows_sharing: Optional[int] = None


class ApprovalDecision(BaseModel):
    tier:    ApprovalTier
    reason:  str
    sla:     str = ""


class ImpactReport(BaseModel):
    riskLevel:       RiskLevel
    confidence:      Confidence
    summary:         str
    impacts:         list[ImpactItem]    = []
    entity_counts:   EntityCounts        = EntityCounts()
    warnings:        list[Warning]       = []
    approval:        ApprovalDecision
    data_gaps:       list[str]           = []
    analysis_time_ms: int               = 0
    bedrock_turns:   int                = 0
    # Brain 2 — SageMaker recommendation (hackathon: pre-computed from Redshift)
    recommendation:  Optional[dict]     = None
