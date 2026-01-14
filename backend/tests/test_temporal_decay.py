"""
Temporal Decay Test Suite
=========================
Tests for EntityNode confidence decay and lifecycle demotion.

Run: pytest sakura_assistant/tests/test_temporal_decay.py -v
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Add parent path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from sakura_assistant.core.world_graph import (
    EntityNode, EntityType, EntityLifecycle, EntitySource, RecencyBucket
)


class TestConfidenceDecay:
    """Test exponential confidence decay."""
    
    def test_fresh_entity_no_decay(self):
        """Entity referenced today should have no decay."""
        entity = EntityNode(
            id="entity:test:fresh",
            type=EntityType.TOPIC,
            name="Fresh Entity",
            confidence=0.8,
            last_referenced=datetime.now()
        )
        
        current = entity.get_current_confidence()
        assert current == 0.8, f"Expected 0.8, got {current}"
    
    def test_30_day_decay_halves_confidence(self):
        """Confidence should halve after 30 days (half-life)."""
        entity = EntityNode(
            id="entity:test:old",
            type=EntityType.TOPIC,
            name="Old Entity",
            confidence=1.0,
            last_referenced=datetime.now() - timedelta(days=30)
        )
        
        current = entity.get_current_confidence()
        # Should be approximately 0.5 (within 5% tolerance)
        assert 0.45 <= current <= 0.55, f"Expected ~0.5, got {current}"
    
    def test_60_day_decay(self):
        """After 60 days (2 half-lives), should be ~0.25."""
        entity = EntityNode(
            id="entity:test:older",
            type=EntityType.TOPIC,
            name="Older Entity",
            confidence=1.0,
            last_referenced=datetime.now() - timedelta(days=60)
        )
        
        current = entity.get_current_confidence()
        # Should be approximately 0.25
        assert 0.2 <= current <= 0.3, f"Expected ~0.25, got {current}"
    
    def test_minimum_confidence(self):
        """Confidence should never go below 0.1."""
        entity = EntityNode(
            id="entity:test:ancient",
            type=EntityType.TOPIC,
            name="Ancient Entity",
            confidence=0.5,
            last_referenced=datetime.now() - timedelta(days=365)  # 1 year
        )
        
        current = entity.get_current_confidence()
        assert current >= 0.1, f"Expected >= 0.1, got {current}"


class TestConfidenceBoost:
    """Test touch() confidence boost."""
    
    def test_touch_increases_confidence(self):
        """touch() should increase confidence by 0.05."""
        entity = EntityNode(
            id="entity:test:boost",
            type=EntityType.TOPIC,
            name="Boost Test",
            confidence=0.5
        )
        
        old_conf = entity.confidence
        entity.touch()
        
        assert entity.confidence == old_conf + 0.05
    
    def test_touch_caps_at_1(self):
        """Confidence should not exceed 1.0."""
        entity = EntityNode(
            id="entity:test:cap",
            type=EntityType.TOPIC,
            name="Cap Test",
            confidence=0.98
        )
        
        entity.touch()
        assert entity.confidence == 1.0
    
    def test_touch_updates_recency(self):
        """touch() should update recency_bucket to NOW."""
        entity = EntityNode(
            id="entity:test:recency",
            type=EntityType.TOPIC,
            name="Recency Test",
            recency_bucket=RecencyBucket.FORGOTTEN
        )
        
        entity.touch()
        assert entity.recency_bucket == RecencyBucket.NOW


class TestLifecycleDemotion:
    """Test automatic lifecycle demotion."""
    
    def test_no_demotion_for_user_entity(self):
        """User identity should never be demoted."""
        entity = EntityNode(
            id="user:self",
            type=EntityType.USER,
            name="User",
            lifecycle=EntityLifecycle.PROMOTED,
            source=EntitySource.SYSTEM,
            confidence=0.1,  # Very low but shouldn't demote
            last_referenced=datetime.now() - timedelta(days=365)
        )
        
        demoted = entity.check_lifecycle_demotion()
        assert demoted == False
        assert entity.lifecycle == EntityLifecycle.PROMOTED
    
    def test_promoted_to_candidate_demotion(self):
        """PROMOTED should demote to CANDIDATE when confidence < 0.3."""
        entity = EntityNode(
            id="entity:test:demote1",
            type=EntityType.TOPIC,
            name="Demotion Test 1",
            lifecycle=EntityLifecycle.PROMOTED,
            source=EntitySource.TOOL_RESULT,
            confidence=0.5,
            last_referenced=datetime.now() - timedelta(days=60)  # Will decay to ~0.25
        )
        
        demoted = entity.check_lifecycle_demotion()
        assert demoted == True
        assert entity.lifecycle == EntityLifecycle.CANDIDATE
    
    def test_candidate_to_ephemeral_demotion(self):
        """CANDIDATE should demote to EPHEMERAL when confidence < 0.15."""
        entity = EntityNode(
            id="entity:test:demote2",
            type=EntityType.TOPIC,
            name="Demotion Test 2",
            lifecycle=EntityLifecycle.CANDIDATE,
            source=EntitySource.LLM_INFERRED,
            confidence=0.3,
            last_referenced=datetime.now() - timedelta(days=90)  # Will decay to ~0.1
        )
        
        demoted = entity.check_lifecycle_demotion()
        assert demoted == True
        assert entity.lifecycle == EntityLifecycle.EPHEMERAL
    
    def test_no_demotion_when_fresh(self):
        """Fresh entities should not be demoted."""
        entity = EntityNode(
            id="entity:test:fresh",
            type=EntityType.TOPIC,
            name="Fresh Promoted",
            lifecycle=EntityLifecycle.PROMOTED,
            source=EntitySource.USER_STATED,
            confidence=0.9,
            last_referenced=datetime.now()
        )
        
        demoted = entity.check_lifecycle_demotion()
        assert demoted == False
        assert entity.lifecycle == EntityLifecycle.PROMOTED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
