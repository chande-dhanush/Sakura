import pytest
from sakura_assistant.core.context.adaptive_engine import AdaptiveInteractionEngine, FrictionDetector
from sakura_assistant.core.context.relevance_engine import ContextRelevanceEngine, ContextBudgeter
from sakura_assistant.core.context.workflow_engine import WorkflowContextEngine, SessionStateClassifier, ToolBiasingRegistry, ImplicitReferenceResolver
from sakura_assistant.core.context.confidence_engine import ConfidenceEngine
from sakura_assistant.core.context.attention_manager import AttentionManager
from sakura_assistant.core.context.failure_handler import TrustAwareFailureHandler
from sakura_assistant.core.context.telemetry import ReliabilityTelemetry
from sakura_assistant.core.context.preference_adaptation import PreferenceAdaptationEngine

def test_session_state_classifier():
    # Test session classification based on process name and window title
    state = SessionStateClassifier.classify_session(
        {"process": "code.exe", "title": "manager.py - VS Code"},
        "how do I compile this"
    )
    assert state == "CODING"
    
    state_writing = SessionStateClassifier.classify_session(
        {"process": "notepad.exe", "title": "draft.txt"},
        "summarize this article"
    )
    assert state_writing == "WRITING"
    
    state_media = SessionStateClassifier.classify_session(
        {"process": "spotify.exe", "title": "Lo-fi Beats"},
        "play next track"
    )
    assert state_media == "MEDIA"

def test_friction_detector():
    engine = AdaptiveInteractionEngine()
    detector = FrictionDetector(engine)
    # Friction detection of correction patterns
    has_friction = detector.analyze_input("no not that, wrong")
    assert has_friction is True
    
    no_friction = detector.analyze_input("hello, can you search the web?")
    assert no_friction is False

def test_adaptive_interaction_engine():
    engine = AdaptiveInteractionEngine()
    # Test posture selection under normal vs busy conditions
    posture = engine.determine_posture("open notepad", "code.exe")
    assert posture in ("SILENT", "SHORT_ACK", "NORMAL", "DETAILED", "REFLECTIVE")
    
    # Test record query turn
    engine.record_turn("run test", response_length_words=10, cancelled=False)
    assert len(engine.metrics["query_lengths"]) > 0

def test_tool_biasing_registry():
    biases = ToolBiasingRegistry.get_tool_bias("CODING")
    assert biases.get("execute_code") == 1.5
    
    biases_research = ToolBiasingRegistry.get_tool_bias("RESEARCH")
    assert biases_research.get("search_web") == 1.6

def test_implicit_reference_resolver():
    # Resolve implicit context from input
    res = ImplicitReferenceResolver.resolve_implicit_references("can you debug that error")
    assert isinstance(res, dict)

def test_confidence_engine():
    res = ConfidenceEngine.score_implicit_reference("open it", {"file_path": "nonexistent_file.py"})
    assert res["confidence"] == 0.5
    posture = ConfidenceEngine.determine_action_posture(res)
    assert posture == "HEDGE"
    
    res_success = ConfidenceEngine.score_implicit_reference("debug the exception", {"error_context": "division by zero"})
    assert res_success["confidence"] == 0.8
    posture_success = ConfidenceEngine.determine_action_posture(res_success)
    assert posture_success == "PROCEED"

def test_preference_adaptation_engine():
    engine = PreferenceAdaptationEngine()
    engine.learn_focus_hours(15)
    assert 15 in engine.prefs["focus_hours"]
    
    engine.record_app_transition("chrome.exe", "code.exe")
    assert "chrome.exe->code.exe" in engine.prefs["habit_transitions"]

def test_context_relevance_engine():
    engine = ContextRelevanceEngine()
    memories = [
        {"text": "I am working on manager.py in my_project", "confidence": 0.8},
        {"text": "I like ice cream", "confidence": 0.3}
    ]
    ranked = engine.rank_memories(memories, "code.exe", "my_project")
    assert len(ranked) == 2
    # First memory gets matched with code.exe / my_project boost
    assert ranked[0]["score"] > ranked[1]["score"]
    
    filtered = engine.suppress_memories(ranked, threshold=2.0)
    assert len(filtered) > 0

def test_context_budgeter():
    budget = ContextBudgeter.get_budget("CHAT")
    assert budget["history"] == 2500
    assert budget["memory"] == 800

def test_workflow_context_engine():
    # This queries win32 or fallbacks, should execute without crashing
    info = WorkflowContextEngine.get_active_window_info()
    assert "title" in info
    assert "process" in info

def test_trust_aware_failure_handler():
    handler = TrustAwareFailureHandler()
    res = handler.handle_tool_failure("web_search", "API rate limit exceeded")
    assert res["success"] is False
    assert "web_search" in res["explanation"]
    assert "phrasing" in res

def test_reliability_telemetry():
    telemetry = ReliabilityTelemetry()
    
    # Record some runs
    telemetry.record_run(success=True, latency=0.5, is_planner=False)
    telemetry.record_run(success=False, latency=1.2, is_planner=True)
    telemetry.record_tool_execution("web_search", success=True)
    telemetry.record_tool_execution("web_search", success=False)
    telemetry.record_context_mismatch()
    
    report = telemetry.get_report()
    assert report["total_runs"] > 0
    assert "success_rate" in report
    assert "web_search" in report["tool_reliability"]
