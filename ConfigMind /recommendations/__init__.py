"""ConfigMind — SageMaker-backed recommendation engine (hackathon edition).

Production flow:
    Redshift → S3 → SageMaker Training → SageMaker Endpoint → this module

Hackathon flow:
    recommendation_data.json (pre-computed) → recommendation_engine.py (rule logic)
    Same output format as the production endpoint — zero changes needed to wire in
    the real SageMaker endpoint later.
"""
from configmind.recommendations.recommendation_engine import get_recommendation

__all__ = ["get_recommendation"]
