"""
Tests for Sakura V7: World Graph

These tests verify the core invariants of the World Graph:
1. User identity is immutable to tools
2. LLM_INFERRED entities never auto-promote
3. Reference resolution prioritizes focus_entity
4. Source-aware mutation enforcement
5. GC only affects ephemeral entities
"""
import pytest
from datetime import datetime, timedelta
from sakura_assistant.core.world_graph import (
    WorldGraph,
    EntityNode,
    ActionNode,
    EntityType,
    EntityLifecycle,
    EntitySource,
    ActionType,
    RecencyBucket,
    UserIntent,
)


class TestIdentityProtection:
    """Invariant 1: User identity is immutable to tools."""
    
    def test_user_identity_exists(self):
        """user:self always exists."""
        graph = WorldGraph()
        user = graph.get_user_identity()
        
        assert user is not None
        assert user.id == "user:self"
        assert user.name == "Dhanush"
    
    def test_user_immutable_to_tools(self):
        """Tools cannot update user identity."""
        graph = WorldGraph()
        
        result = graph.update_entity(
            "user:self",
            {"age": 100, "name": "Hacked"},
            EntitySource.TOOL_RESULT
        )
        
        assert result is False
        assert graph.get_user_identity().attributes["age"] == 22
    
    def test_user_mutable_by_user(self):
        """User can update their own identity."""
        graph = WorldGraph()
        
        result = graph.update_entity(
            "user:self",
            {"location": "Mumbai"},
            EntitySource.USER_STATED
        )
        
        assert result is True
        assert graph.get_user_identity().attributes["location"] == "Mumbai"
    
    def test_llm_cannot_update_user(self):
        """LLM inferences cannot update user identity."""
        graph = WorldGraph()
        
        result = graph.update_entity(
            "user:self",
            {"favorite_movie": "Inception"},
            EntitySource.LLM_INFERRED
        )
        
        assert result is False
    
    def test_negative_constraints_exist(self):
        """User has negative constraints (NOT claims)."""
        graph = WorldGraph()
        user = graph.get_user_identity()
        
        assert len(user.not_claims) > 0
        assert "NOT the actor Dhanush" in user.not_claims


class TestEntityLifecycle:
    """Invariant 2: LLM_INFERRED entities never auto-promote."""
    
    def test_llm_inferred_is_ephemeral(self):
        """LLM_INFERRED entities start as EPHEMERAL."""
        graph = WorldGraph()
        
        entity = graph.get_or_create_entity(
            type=EntityType.PERSON,
            name="Some Person",
            source=EntitySource.LLM_INFERRED
        )
        
        assert entity.lifecycle == EntityLifecycle.EPHEMERAL
        assert entity.confidence < 0.5
    
    def test_user_stated_is_promoted(self):
        """USER_STATED entities start as PROMOTED."""
        graph = WorldGraph()
        
        entity = graph.get_or_create_entity(
            type=EntityType.PERSON,
            name="My Friend",
            source=EntitySource.USER_STATED
        )
        
        assert entity.lifecycle == EntityLifecycle.PROMOTED
    
    def test_tool_result_is_ephemeral(self):
        """TOOL_RESULT entities start as EPHEMERAL."""
        graph = WorldGraph()
        
        entity = graph.get_or_create_entity(
            type=EntityType.TOPIC,
            name="AI News",
            source=EntitySource.TOOL_RESULT
        )
        
        assert entity.lifecycle == EntityLifecycle.EPHEMERAL
    
    def test_promotion_requires_references(self):
        """Ephemeral entities need multiple references to become candidates."""
        graph = WorldGraph()
        
        entity = graph.get_or_create_entity(
            type=EntityType.SONG,
            name="Test Song",
            source=EntitySource.TOOL_RESULT
        )
        
        # Reference it multiple times
        for _ in range(3):
            entity.touch()
        
        graph._check_promotions()
        
        # Should be CANDIDATE now
        assert entity.lifecycle == EntityLifecycle.CANDIDATE


class TestReferenceResolution:
    """Invariant 3: Reference resolution prioritizes focus_entity."""
    
    def test_me_resolves_to_user(self):
        """'me' always resolves to user with confidence 1.0."""
        graph = WorldGraph()
        
        result = graph.resolve_reference("me")
        
        assert result.resolved is not None
        assert result.resolved.id == "user:self"
        assert result.confidence == 1.0
        assert result.ban_external_search is True
    
    def test_myself_resolves_to_user(self):
        """'myself' always resolves to user."""
        graph = WorldGraph()
        
        result = graph.resolve_reference("myself")
        
        assert result.resolved.id == "user:self"
        assert result.confidence == 1.0
    
    def test_that_resolves_to_focus_entity(self):
        """'that' resolves to focus_entity, not the action."""
        graph = WorldGraph()
        
        # Play a song
        graph.record_action(
            tool="spotify_control",
            args={"song_name": "Shape of You"},
            result="Playing...",
            success=True
        )
        
        result = graph.resolve_reference("that")
        
        # Should resolve to the SONG, not the action
        assert result.resolved is not None
        assert hasattr(result.resolved, "name")  # Entity, not action
        assert result.resolved.name == "Shape of You"
        assert result.confidence >= 0.9
    
    def test_that_without_focus_falls_back_to_action(self):
        """'that' falls back to action if no focus_entity."""
        graph = WorldGraph()
        
        # Record a chat action (no focus entity)
        action = ActionNode(
            id="action:t-0",
            turn=0,
            action_type=ActionType.CHAT,
            summary="Just chatting"
        )
        graph.actions.append(action)
        
        result = graph.resolve_reference("that")
        
        # Should fall back to the action itself
        assert result.resolved is not None
        assert result.confidence <= 0.5  # Lower confidence for action
    
    def test_again_triggers_repeat(self):
        """'again' triggers a repeat action."""
        graph = WorldGraph()
        
        graph.record_action(
            tool="web_search",
            args={"query": "AI news"},
            result="Results...",
            success=True
        )
        
        result = graph.resolve_reference("search again")
        
        assert result.action == "repeat"
        assert result.confidence >= 0.9
    
    def test_instead_triggers_modify(self):
        """'instead' triggers tool modification."""
        graph = WorldGraph()
        
        graph.record_action(
            tool="web_search",
            args={"query": "machine learning"},
            result="Results...",
            success=True
        )
        
        result = graph.resolve_reference("use arxiv instead")
        
        assert result.action == "modify_tool"
        assert result.resolved is not None


class TestUserReferenceDetection:
    """Test is_user_reference() for search banning."""
    
    def test_who_am_i(self):
        """'who am I' is a user reference."""
        graph = WorldGraph()
        
        is_user, conf = graph.is_user_reference("who am I")
        
        assert is_user is True
        assert conf == 1.0
    
    def test_about_me(self):
        """'about me' is a user reference."""
        graph = WorldGraph()
        
        is_user, conf = graph.is_user_reference("tell me about me")
        
        assert is_user is True
        assert conf == 1.0
    
    def test_user_name_is_likely_user(self):
        """User's name with 'about' is likely user reference."""
        graph = WorldGraph()
        
        is_user, conf = graph.is_user_reference("tell me about Dhanush")
        
        assert is_user is True
        assert conf >= 0.7
    
    def test_external_query_is_not_user(self):
        """External queries are not user references."""
        graph = WorldGraph()
        
        is_user, conf = graph.is_user_reference("what is the weather")
        
        assert is_user is False
        assert conf == 0.0


class TestPlanValidation:
    """Invariant 4: Graph veto blocks identity violations."""
    
    def test_veto_search_for_user(self):
        """Veto search when query is about user."""
        graph = WorldGraph()
        
        plan = {
            "plan": [
                {"tool": "web_search", "args": {"query": "who is Dhanush"}}
            ]
        }
        
        valid, reason = graph.validate_plan(plan)
        
        assert valid is False
        assert "user" in reason.lower()
    
    def test_allow_search_for_external(self):
        """Allow search for external entities."""
        graph = WorldGraph()
        
        plan = {
            "plan": [
                {"tool": "web_search", "args": {"query": "latest AI news"}}
            ]
        }
        
        valid, reason = graph.validate_plan(plan)
        
        assert valid is True


class TestGarbageCollection:
    """Invariant 5: GC only affects ephemeral entities."""
    
    def test_gc_removes_old_ephemeral(self):
        """GC removes old ephemeral entities with low reference count."""
        graph = WorldGraph()
        
        # Create ephemeral entity
        entity = graph.get_or_create_entity(
            type=EntityType.QUERY,
            name="old query",
            source=EntitySource.TOOL_RESULT
        )
        entity_id = entity.id
        
        # Make it old
        entity.last_referenced = datetime.now() - timedelta(hours=2)
        
        # Run GC
        graph._garbage_collect()
        
        # Should be removed
        assert entity_id not in graph.entities
    
    def test_gc_keeps_promoted(self):
        """GC never removes promoted entities."""
        graph = WorldGraph()
        
        # Create promoted entity
        entity = graph.get_or_create_entity(
            type=EntityType.PERSON,
            name="Important Friend",
            source=EntitySource.USER_STATED  # Starts as PROMOTED
        )
        entity_id = entity.id
        
        # Make it old
        entity.last_referenced = datetime.now() - timedelta(hours=10)
        
        # Run GC
        graph._garbage_collect()
        
        # Should still exist
        assert entity_id in graph.entities
    
    def test_gc_never_removes_identity(self):
        """GC never removes user identity."""
        graph = WorldGraph()
        
        # Make identity old (shouldn't matter)
        graph.entities["user:self"].last_referenced = datetime.now() - timedelta(days=30)
        
        # Run GC
        graph._garbage_collect()
        
        # Should still exist
        assert "user:self" in graph.entities


class TestCompression:
    """Invariant 6: Compression preserves key_facts."""
    
    def test_key_facts_extracted(self):
        """Key facts are extracted from actions."""
        graph = WorldGraph()
        
        action = graph.record_action(
            tool="spotify_control",
            args={"song_name": "Shape of You"},
            result="Playing...",
            success=True
        )
        
        assert len(action.key_facts) > 0
        assert any("Shape of You" in fact for fact in action.key_facts)
    
    def test_focus_entity_set(self):
        """Focus entity is inferred from tool + args."""
        graph = WorldGraph()
        
        action = graph.record_action(
            tool="spotify_control",
            args={"song_name": "Blinding Lights"},
            result="Playing...",
            success=True
        )
        
        assert action.focus_entity is not None
        assert "blinding_lights" in action.focus_entity.lower()


class TestContextGeneration:
    """Test context generation for planner/responder."""
    
    def test_context_for_planner_includes_user(self):
        """Planner context always includes user identity."""
        graph = WorldGraph()
        
        context = graph.get_context_for_planner("test query")
        
        assert "Dhanush" in context
    
    def test_context_for_planner_includes_recent_action(self):
        """Planner context includes recent actions."""
        graph = WorldGraph()
        
        graph.record_action(
            tool="web_search",
            args={"query": "test"},
            result="results",
            success=True
        )
        
        context = graph.get_context_for_planner("another query")
        
        assert "web_search" in context or "RECENT" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
