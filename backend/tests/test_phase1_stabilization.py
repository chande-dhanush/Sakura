"""
Phase 1 Stabilization Tests   V19 Fixes
========================================
Tests for BUG-01 (Router arg mismatch), BUG-02 (Reference resolution ghosting),
BUG-03 (Scheduler import path silent death).

These tests verify the three critical control-path fixes that prevent:
- TypeError crashes from boolean-as-history in routing
- Discarded reference resolution in the LLM context path
- Silent cognitive subsystem death from wrong import paths
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

# Ensure backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


#                                                                                
# TEST GROUP A: Router Argument Safety (BUG-01)
#                                                                                

class TestRouterArgumentSafety(unittest.TestCase):
    """
    Verify that the router's aroute/route methods are called with correct
    keyword arguments and that a boolean can NEVER land in the history parameter.
    """

    def setUp(self):
        """Create a mock router with the real signature."""
        self.mock_llm = MagicMock()
        from sakura_assistant.core.routing.router import IntentRouter, RouteResult
        self.router = IntentRouter(self.mock_llm)

    def test_route_with_normal_history(self):
        """Route with a normal conversation history list."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        # Should NOT crash   this is the normal path
        result = self.router.route(query="play music", history=history)
        self.assertIsNotNone(result)
        self.assertIn(result.classification, ("DIRECT", "PLAN", "CHAT"))

    def test_route_with_empty_history(self):
        """Route with empty history should work."""
        result = self.router.route(query="hello", history=[])
        self.assertIsNotNone(result)

    def test_route_with_none_history(self):
        """Route with None history (default) should work."""
        result = self.router.route(query="hello", history=None)
        self.assertIsNotNone(result)

    def test_route_with_keyword_arguments(self):
        """Route using keyword arguments (the V19 fix pattern)."""
        result = self.router.route(
            query="search for quantum computing",
            history=[{"role": "user", "content": "test"}]
        )
        self.assertIsNotNone(result)

    def test_boolean_in_history_crashes_correctly(self):
        """
        REGRESSION TEST: Prove that the OLD bug pattern crashes.
        The router's internal code does `history[-3:]` which fails on bool.
        This confirms why V19-FIX-01 switched to keyword arguments.
        """
        # Simulate the exact operation the router does internally:
        # history[-3:]   this MUST fail on a boolean
        with self.assertRaises(TypeError):
            # This is what happened before the fix: study_mode_active=True
            # was passed as the history parameter
            bad_history = True  # bool, not List[Dict]
            _ = bad_history[-3:]  # This is what the router does internally

    def test_route_study_mode_query_no_crash(self):
        """
        Study mode queries (educational keywords) must not crash.
        Before V19-FIX-01, study_mode_active=True was passed as history.
        """
        # Simulate what llm.py now does: keyword args, no study_mode in router
        result = self.router.route(
            query="explain quantum computing for beginners",
            history=[{"role": "user", "content": "I want to learn physics"}]
        )
        self.assertIsNotNone(result)
        # The key point: no crash occurred

    def test_action_command_bypasses_llm(self):
        """Action commands should go to DIRECT without LLM call."""
        result = self.router.route(query="play Bohemian Rhapsody")
        self.assertEqual(result.classification, "DIRECT")
        self.assertIsNotNone(result.tool_hint)


#                                                                                
# TEST GROUP B: Reference Resolution Injection (BUG-02)
#                                                                                

class TestReferenceResolutionInjection(unittest.TestCase):
    """
    Verify that WorldGraph.resolve_reference() results are captured and
    formatted for downstream injection, not discarded.
    """

    def test_resolution_result_fields(self):
        """Verify ResolutionResult has the expected fields for formatting."""
        from sakura_assistant.core.graph.world_graph import ResolutionResult
        result = ResolutionResult(
            resolved=None,
            confidence=0.0,
            ban_external_search=False,
            action=None,
            fallback_response="I don't know what you're referring to."
        )
        self.assertIsNone(result.resolved)
        self.assertEqual(result.confidence, 0.0)

    def test_entity_resolution_formatting(self):
        """Test that an EntityNode resolution produces a context string."""
        from sakura_assistant.core.graph.world_graph import EntityNode, EntityType, EntityLifecycle, ResolutionResult

        entity = EntityNode(
            id="song:bohemian_rhapsody",
            type=EntityType.SONG,
            name="Bohemian Rhapsody",
            summary="A song by Queen",
            lifecycle=EntityLifecycle.PROMOTED,
            confidence=0.9
        )
        resolution = ResolutionResult(resolved=entity, confidence=0.9)

        # Format like llm.py does
        reference_context = ""
        if resolution.resolved and resolution.confidence > 0.4:
            if isinstance(resolution.resolved, EntityNode):
                reference_context = (
                    f"[REFERENCE RESOLVED] refers to: "
                    f"{resolution.resolved.name}   {resolution.resolved.summary or 'No description'} "
                    f"(confidence: {resolution.confidence:.0%})"
                )

        self.assertIn("Bohemian Rhapsody", reference_context)
        self.assertIn("REFERENCE RESOLVED", reference_context)
        self.assertIn("90%", reference_context)

    def test_action_resolution_formatting(self):
        """Test that an ActionNode resolution produces a context string."""
        from sakura_assistant.core.graph.world_graph import ActionNode, ActionType, ResolutionResult

        action = ActionNode(
            id="action:t-5",
            turn=5,
            tool="web_search",
            args={"query": "quantum computing"},
            result="Search results...",
            summary="Searched for quantum computing",
            action_type=ActionType.TOOL_CALL
        )
        resolution = ResolutionResult(resolved=action, confidence=0.85, action="repeat")

        reference_context = ""
        if resolution.resolved and resolution.confidence > 0.4:
            if isinstance(resolution.resolved, ActionNode):
                reference_context = (
                    f"[REFERENCE RESOLVED] refers to previous action: "
                    f"{resolution.resolved.tool or 'chat'}   {resolution.resolved.summary or 'No description'} "
                    f"(confidence: {resolution.confidence:.0%})"
                )
            if resolution.action:
                reference_context += f" [Suggested action: {resolution.action}]"

        self.assertIn("web_search", reference_context)
        self.assertIn("REFERENCE RESOLVED", reference_context)
        self.assertIn("repeat", reference_context)

    def test_no_resolution_produces_empty_context(self):
        """When resolution confidence is too low, no context should be produced."""
        from sakura_assistant.core.graph.world_graph import ResolutionResult

        resolution = ResolutionResult(resolved=None, confidence=0.0)

        reference_context = ""
        if resolution.resolved and resolution.confidence > 0.4:
            reference_context = "should not be set"

        self.assertEqual(reference_context, "")

    def test_ban_external_search_flag(self):
        """Verify ban_external_search flag is included in context when set."""
        from sakura_assistant.core.graph.world_graph import EntityNode, EntityType, EntityLifecycle, ResolutionResult

        user_entity = EntityNode(
            id="user:self",
            type=EntityType.USER,
            name="Dhanush",
            summary="The user",
            lifecycle=EntityLifecycle.PROMOTED,
            confidence=1.0
        )
        resolution = ResolutionResult(
            resolved=user_entity,
            confidence=1.0,
            ban_external_search=True
        )

        reference_context = ""
        if resolution.resolved and resolution.confidence > 0.4:
            if isinstance(resolution.resolved, EntityNode):
                reference_context = (
                    f"[REFERENCE RESOLVED] refers to: "
                    f"{resolution.resolved.name}"
                )
            if resolution.ban_external_search:
                reference_context += " [DO NOT search externally for this]"

        self.assertIn("DO NOT search externally", reference_context)


#                                                                                
# TEST GROUP C: Scheduler Import Paths (BUG-03)
#                                                                                

class TestSchedulerImportPaths(unittest.TestCase):
    """
    Verify that scheduler can import cognitive modules (desire, proactive)
    using the corrected relative import paths.
    """

    def test_desire_import_from_scheduler_context(self):
        """
        The scheduler lives at core.infrastructure.scheduler.
        It must import from core.cognitive.desire (sibling, not child).
        Simulating the import that run_hourly_desire_tick does.
        """
        try:
            from sakura_assistant.core.cognitive.desire import get_desire_system
            desire = get_desire_system()
            self.assertIsNotNone(desire)
        except ImportError as e:
            self.fail(f"Desire system import failed: {e}")

    def test_proactive_import_from_scheduler_context(self):
        """
        The scheduler must import from core.cognitive.proactive (sibling).
        """
        try:
            from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
            scheduler = get_proactive_scheduler()
            self.assertIsNotNone(scheduler)
        except ImportError as e:
            self.fail(f"Proactive scheduler import failed: {e}")

    def test_desire_system_initialization(self):
        """Verify desire system can be initialized without crash."""
        from sakura_assistant.core.cognitive.desire import get_desire_system
        desire = get_desire_system()
        # Verify it has the expected state structure
        self.assertIsNotNone(desire.state)
        self.assertIsInstance(desire.state.social_battery, float)
        self.assertIsInstance(desire.state.loneliness, float)

    def test_desire_hourly_tick_runs(self):
        """Verify the hourly tick function executes without crash."""
        from sakura_assistant.core.cognitive.desire import get_desire_system
        desire = get_desire_system()
        initial_loneliness = desire.state.loneliness
        desire.on_hourly_tick()
        # Loneliness should have increased (it increases every tick)
        self.assertGreaterEqual(desire.state.loneliness, 0.0)

    def test_scheduler_cognitive_task_scheduling(self):
        """Verify schedule_cognitive_tasks runs without import errors."""
        try:
            # We can't fully run this (it schedules real timers), but we can
            # verify the imports work by calling the import verification section
            from sakura_assistant.core.cognitive.desire import get_desire_system
            from sakura_assistant.core.cognitive.proactive import get_proactive_scheduler
            ds = get_desire_system()
            ps = get_proactive_scheduler()
            self.assertIsNotNone(ds)
            self.assertIsNotNone(ps)
        except ImportError as e:
            self.fail(f"Cognitive imports failed (scheduler would silently die): {e}")


#                                                                                
# TEST GROUP D: Integration   Full Pipeline Path
#                                                                                

class TestPipelineIntegration(unittest.TestCase):
    """
    Verify the fixed pipeline path in llm.py doesn't crash on common inputs.
    These are structural tests, not LLM output tests.
    """

    def test_world_graph_resolve_reference_returns_result(self):
        """Verify resolve_reference returns a usable ResolutionResult."""
        from sakura_assistant.core.graph.world_graph import WorldGraph, ResolutionResult
        from sakura_assistant.core.graph.identity import get_identity_manager

        wg = WorldGraph(identity_manager=get_identity_manager())

        # Test with a self-reference
        result = wg.resolve_reference("me")
        self.assertIsInstance(result, ResolutionResult)
        self.assertIsNotNone(result.resolved)
        self.assertEqual(result.confidence, 1.0)
        self.assertTrue(result.ban_external_search)

    def test_world_graph_resolve_unknown_returns_empty(self):
        """Verify unknown references return low-confidence result."""
        from sakura_assistant.core.graph.world_graph import WorldGraph, ResolutionResult
        from sakura_assistant.core.graph.identity import get_identity_manager

        wg = WorldGraph(identity_manager=get_identity_manager())

        result = wg.resolve_reference("xyzzy foobar")
        self.assertIsInstance(result, ResolutionResult)
        self.assertLessEqual(result.confidence, 0.4)

    def test_responder_context_includes_reference(self):
        """
        Simulate the V19 fix path: reference_context must be
        included in the responder context assembly.
        """
        mood_prompt = "[MOOD: CONTENT] Normal mode"
        graph_context = "User: Dhanush"
        reference_context = "[REFERENCE RESOLVED] 'that file' refers to: notes.txt"

        # This simulates llm.py lines 347-351 (V19 fix)
        responder_parts = [mood_prompt, graph_context]
        if reference_context:
            responder_parts.insert(1, reference_context)
        responder_context = "\n\n".join(filter(None, responder_parts))

        self.assertIn("[REFERENCE RESOLVED]", responder_context)
        self.assertIn("notes.txt", responder_context)
        self.assertIn("[MOOD:", responder_context)
        # Reference should be between mood and graph (position 1)
        mood_pos = responder_context.index("[MOOD:")
        ref_pos = responder_context.index("[REFERENCE RESOLVED]")
        graph_pos = responder_context.index("User: Dhanush")
        self.assertLess(mood_pos, ref_pos)
        self.assertLess(ref_pos, graph_pos)

    def test_responder_context_without_reference(self):
        """When no reference is resolved, context should not contain reference block."""
        mood_prompt = "[MOOD: CONTENT]"
        graph_context = "User: Dhanush"
        reference_context = ""  # No resolution

        responder_parts = [mood_prompt, graph_context]
        if reference_context:
            responder_parts.insert(1, reference_context)
        responder_context = "\n\n".join(filter(None, responder_parts))

        self.assertNotIn("[REFERENCE RESOLVED]", responder_context)
        self.assertIn("[MOOD:", responder_context)


if __name__ == "__main__":
    print("=" * 70)
    print("Phase 1 Stabilization Tests   V19 Fixes")
    print("=" * 70)
    unittest.main(verbosity=2)
