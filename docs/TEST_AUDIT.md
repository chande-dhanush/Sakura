# Test Suite Audit & Gap Analysis

## 1. Current Test Coverage Strength
- **Core Logic:** Excellent coverage of World Graph, Router, and Executor logic.
- **Security:** Strong tests for sandboxing (Docker & path traversal) and injection attacks (`quick_math`, standard tool routing).
- **V13 Features:** Comprehensive tests for new features (audio, code interpreter, temporal decay).

## 2. Identified Gaps (What's Missing?)

### A. Performance & Load Testing
- **Concurrent User Simulation:** Tests currently run sequentially. No stress test for 10-50 concurrent requests to the `FastAPI` server.
- **Long-Running Sessions:** No test simulates a 24-hour continuous session to check for slow memory leaks or performance degradation over thousands of entity updates.

### B. Industrial Benchmarks (Recommended)
To benchmark Sakura V13 against industry standards, we should consider implementing:

1.  **Gaia Benchmark (General AI Assistants):**
    -   *Concept:* Tests ability to find, reason, and act on information.
    -   *Application:* Test Sakura's ability to "plan a trip" or "answer questions requiring multi-step web search and tool use."

2.  **AgentBench (Tool Use & Planning):**
    -   *Concept:* Evaluates LLMs as agents in interactive environments (OS, Database, Knowledge Graph).
    -   *Application:* Test complex `execute_python` tasks (e.g., "analyze this data and plot") or multi-step file manipulations.

3.  **HumanEval (Python Coding):**
    -   *Concept:* Standard for code generation.
    -   *Application:* Verify `Code Interpreter` accuracy on standard coding problems (e.g., "Write a function to fibonacci").

### C. Bias Audit (Impartiality Check)

#### 1. Router Bias
-   **Current State:** The `Few-Shot Router` uses 15 examples.
-   **Potential Bias:** If examples skew towards specific domains (e.g., coding prompts), the router might over-trigger `Code Interpreter` for general queries.
-   **Check:** Review `router.py` examples. Ensure balanced representation of:
    -   Casual Chat ("Hello", "How are you?")
    -   General Knowledge ("Who is the president?")
    -   Tool Use ("Play music", "Check weather")

#### 2. Temporal Decay Bias
-   **Current State:** All entities decay at the same rate (half-life = 30 days).
-   **Potential Bias:** "Important" long-term facts (e.g., user name, core preferences) might decay too fast compared to ephemeral facts (e.g., "I ate pizza").
-   **Recommendation:** Verify `EntityType.USER` immunity or specific tagging for "Permanent" memories. (Tests confirm `user:self` is immune, but what about "My wife's birthday"?).

#### 3. Responder Tone Bias
-   **Current State:** `SYSTEM_PERSONALITY` defines tone.
-   **Check:** Ensure the prompt doesn't enforce a specific cultural or behavioral bias unless intended. (Sakura is "helpful", "concise").

## 3. Recommended Actions

1.  **Add Load Test:** Create `tests/stress/concurrent_load.py` using `locust` or `asyncio` to hammer endpoints.
2.  **Add Long-Haul Test:** Create `tests/stress/long_session.py` simulating 1000 interactions and monitoring RAM.
3.  **Implement Mini-AgentBench:** Create a test suite `tests/benchmarks/agent_tasks.py` with 5-10 complex, multi-step scenarios (e.g., "Find the weather in Tokyo, calculate the difference with NY, and save to a note").
4.  **Review Router Examples:** Manually check `router.py` few-shot examples for domain balance.
