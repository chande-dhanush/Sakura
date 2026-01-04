import sys
import os
sys.path.append(os.getcwd())
# from core.relevance_mapper import get_tool_relevance
import pytest


def test_router_no_match():
    # Simple greetings or chats should have 0 confidence
    res = get_tool_relevance("hello there")
    assert res['tool'] is None
    assert res['confidence'] < 0.5

def test_router_explanation_is_not_note():
    # "Explain X" should NOT trigger a note tool
    res = get_tool_relevance("Explain quantum physics to me")
    assert res['tool'] is None
    assert res['confidence'] < 0.5
    assert "Pure explanation" in res['reason']

def test_router_note_explicit():
    # "Make a note" MUST trigger note tool
    res = get_tool_relevance("Make a note about the meeting")
    assert res['tool'] == "note_create"
    assert res['confidence'] > 0.8

def test_router_explanation_with_save():
    # "Explain X and save it" SHOULD trigger note tool
    res = get_tool_relevance("Explain how cars work and save the note")
    assert res['tool'] == "note_create"
    assert res['confidence'] > 0.6

def test_router_spotify():
    res = get_tool_relevance("Play some jazz music")
    assert res['tool'] == "spotify_control"
    assert res['confidence'] > 0.9

def test_router_vision():
    res = get_tool_relevance("What is on my screen right now?")
    assert res['tool'] == "read_screen"
    assert res['confidence'] > 0.9
