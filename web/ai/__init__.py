"""
TRAJECTA.AI — Google Gemma AI Intelligence Module
"""
from web.ai.gemma_engine import gemma_engine, GemmaCricketEngine
from web.ai.drills_catalog import DRILLS_CATALOG, get_recommended_drills_for_weaknesses

__all__ = ["gemma_engine", "GemmaCricketEngine", "DRILLS_CATALOG", "get_recommended_drills_for_weaknesses"]
