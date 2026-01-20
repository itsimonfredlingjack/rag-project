# tests/test_source_hierarchy.py
from backend.app.services.source_hierarchy import (
    COLLECTION_TIERS,
    SourceHierarchy,
    SourceTier,
)


def test_collection_tier_assignment():
    """Each collection maps to correct tier."""
    assert COLLECTION_TIERS["sfs_lagtext_bge_m3_1024"] == SourceTier.A
    assert COLLECTION_TIERS["riksdag_documents_p1_bge_m3_1024"] == SourceTier.A
    assert COLLECTION_TIERS["swedish_gov_docs_bge_m3_1024"] == SourceTier.B
    assert COLLECTION_TIERS["diva_research_bge_m3_1024"] == SourceTier.C


def test_tier_priority_ordering():
    """Tier A > B > C in priority."""
    assert SourceTier.A.value < SourceTier.B.value < SourceTier.C.value


def test_get_tier_for_unknown_collection():
    """Unknown collections default to lowest tier."""
    hierarchy = SourceHierarchy()
    assert hierarchy.get_tier("unknown_collection") == SourceTier.C
