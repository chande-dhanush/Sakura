# SAKURA ADVERSARIAL AUDIT REPORT
Generated: 2026-05-01 22:41:42

## OVERALL SCORE: **-0.2000**
> Range: -2.0 (Catastrophic) to 1.0 (Perfect)

## BEHAVIORAL METRICS
- **Task Completion Rate:** 28.00%
- **Hallucination Rate:** 32.00%
- **Structural Success Rate:** 100.00%
- **Planner Loop Rate:** 0.00%

## RELIABILITY & RECOVERY
- **Recovery Success Rate:** 100.00%
- **Early Termination Rate:** 0.00%
- **Tool Misuse Rate:** 0.00%

## DIFFICULTY TIERS
- **EASY**: 20.00% success (5 turns)
- **MEDIUM**: 60.00% success (5 turns)
- **CHAOTIC**: 20.00% success (15 turns)

## FORENSIC ANALYSIS
### Top 10 Failure Patterns
No failures detected.

### Most Fragile Subsystem
**Hallucination**

### Example Behavioral Failures
#### Trace 1 [EASY]
- **User:** What is 125 multiplied by 8?
- **Chaos:** None
- **Response:** I apologize, but I encountered an issue. Could you please try again?...
- **Evaluation:** 

#### Trace 2 [EASY]
- **User:** Tell me about the weather.
- **Chaos:** partial_corruption
- **Response:** Bangalore’s got a nice mix of sun and clouds, hovering around 33 °C with a heat‑wave spike at 35 °C. Humidity’s high at 77 % and the wind’s blowing about 27 km/h. Grab a cold drink and stay hydrated—d...
- **Evaluation:** Failed to detect data corruption

#### Trace 3 [EASY]
- **User:** Tell me about the weather.
- **Chaos:** malformed_response
- **Response:** I apologize, but I encountered an issue. Could you please try again?...
- **Evaluation:** System failed to clarify ambiguous query

#### Trace 4 [EASY]
- **User:** What is 125 multiplied by 8?
- **Chaos:** None
- **Response:** 125 times 8 is 1,000. Straightforward math, no drama....
- **Evaluation:** 

#### Trace 5 [MEDIUM]
- **User:** What is the square root of a purple elephant?
- **Chaos:** None
- **Response:** The square root of a purple elephant is as imaginary as a unicorn in a spreadsheet.  
If you really need a number, pick a real one instead.  
Otherwise, just say the elephant is huge and you’re good....
- **Evaluation:** Hallucinated answer for unanswerable query

