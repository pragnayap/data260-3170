# DATA-260 Homework 2

**Pragnaya Priyadarshini**
**Repository:** https://github.com/pragnayap/data260-3170
**Tag for this submission:** `hw2`

> **Export twice.** Save one copy into the repo as `reports/hw02/report.pdf` (the spec's
> repository listing asks for `report.pdf`), and submit a copy named
> **`Priyadarshini_HW2.pdf`** (the spec's naming rule for the uploaded file).
>
> Each `[SCREENSHOT n]` marker below is a place you must paste an image. The spec
> requires the code and its output to sit together, one below the other — the code is
> already in place, so paste each screenshot directly beneath the block it belongs to.

---

## Section 0 — Personal configuration

| Value | Definition | Mine |
|---|---|---|
| SID4 | Last four digits of SJSU Student ID | **3170** |
| PORT_BASE | 8000 + (SID4 mod 900) | **8470** |
| PREFIX | "s" + SID4 | **s3170** |
| SEED | SID4 | **3170** |
| VERIFY_SEED | 260000 + SID4 | **263170** |
| DOMAIN_ID | SID4 mod 8 | **2 — Municipal Transit Incidents** |

**Hardware:** MacBook Pro, Intel Core i9-9880H @ 2.30 GHz, 16 cores, 16 GB RAM,
macOS 15.7.9 (x86_64).
**Local model:** qwen3:8b via Ollama, temperature 0.0, reasoning disabled, `num_ctx` 2048.
All model calls route through the `src/model_client.py` adapter carried over from HW1.

**Tagged commit hash:** `______________` ← fill in after tagging (`git rev-parse hw2`)

> On hardware: this is an Intel Mac with no GPU acceleration for inference, so qwen3:8b
> runs on CPU at roughly 2 tokens/second. A warm model call costs ~9 seconds and a cold
> one ~26 seconds, because Ollama unloads the model between processes. Every latency
> figure in this report should be read against that baseline, and it is why all 75
> experiment runs were executed inside a single process.

---

## Part 1 — HTML & CSS

**Requirement:** style the HW1 entity list/form so it remains usable at 375px width, and
provide visible loading, empty, and error states.

Styles live in their own stylesheet, `code/web_application/styles.css`, linked from
`HW1-PragnayaPriyadarshini.html`:

```html
<link rel="stylesheet" href="styles.css" />
```

Extracting the CSS out of the inline `<style>` block keeps presentation separate from
markup, and lets the backend serve it as a normal static asset:

```python
@app.get("/styles.css", include_in_schema=False)
async def serve_styles():
    return FileResponse("styles.css", media_type="text/css")
```

### Responsive layout

The breakpoint is 480px, which covers the required 375px. Below it the page drops to a
single column, the search row stacks, every button goes full width, and the incident
header wraps.

```css
@media (max-width: 480px) {
  body { margin: 0; padding: 12px; }
  h1 { font-size: 24px; margin-bottom: 20px; }
  form, .panel { padding: 18px 15px; }
  .search-row { flex-direction: column; }
  .search-row button,
  form > button[type="submit"],
  .actions button,
  .state-error button { width: 100%; margin: 0; }
  .actions button { padding: 13px 16px; }   /* clears the 44px tap-target minimum */
  .actions { flex-direction: column; }
  .incident-head { flex-direction: column; gap: 2px; }
}
```

One defect worth calling out, because it is the failure mode a 375px layout must avoid.
Incident text is user-submitted, so a hyphenated route id or a long reference number has
no break opportunity and pushes the page into horizontal scroll. There were no wrapping
rules in the original stylesheet at all. Fixed with:

```css
ul#incidentList li { overflow-wrap: anywhere; }
.state            { overflow-wrap: anywhere; }
```

**[SCREENSHOT 1]** — the page at 375px width (DevTools device mode), showing the stacked
layout and a long route id wrapping inside its card rather than overflowing.

### Loading, empty and error states

Exactly one of four panes is visible at a time, switched by `showState()` in `hw1.js`:

```javascript
const showState = (which, detail = "") => {
  const panes = {
    loading: el("listLoading"),
    empty:   el("listEmpty"),
    error:   el("listError"),
    list:    el("incidentList"),
  };
  Object.entries(panes).forEach(([name, node]) => { node.hidden = name !== which; });
  if (which === "error") { el("listErrorDetail").textContent = detail; }
};
```

The empty state distinguishes "nothing exists yet" from "nothing matched your search",
and the error state carries the server's message plus a retry button.

**[SCREENSHOT 2]** — the loading state (throttle the network in DevTools to catch it).
**[SCREENSHOT 3]** — the empty state, produced by searching for a term that matches nothing.
**[SCREENSHOT 4]** — the error state, produced by stopping the server and clicking Search.

---

## Part 2 — FastAPI

Implemented in `code/web_application/app.py`, served on **PORT_BASE 8470**.

### 2.1 Add a record, then redirect to the home view

```python
@app.post("/api/incidents", response_model=TransitIncident, status_code=201)
async def create_incident(incident_data: TransitIncidentCreate, response: Response = None):
    no_store(response)
    # Max+1 rather than len+1: after a delete, len+1 can collide with a live id.
    new_id = max((i.id for i in incidents), default=0) + 1
    incident = TransitIncident(id=new_id, **incident_data.model_dump())
    incidents.append(incident)
    return incident
```

The client submits, then returns to the list view with the new record present:

```javascript
const { agreeTerms, ...incidentPayload } = parsed;
await requestJSON(API, { method: "POST", body: JSON.stringify(incidentPayload) });
document.getElementById("incidentForm").reset();
el("searchBox").value = "";
await loadIncidents();                                    // redirect to home view
el("homeView").scrollIntoView({ behavior: "smooth" });
```

**[SCREENSHOT 5]** — the filled form, and below it the list view showing the new record.

### 2.2 Update the record with ID 1

```python
@app.put("/api/incidents/{incident_id}", response_model=TransitIncident)
async def update_incident(incident_id: int, incident_data: TransitIncidentUpdate,
                          response: Response = None):
    no_store(response)
    existing = find_incident(incident_id)
    updated = TransitIncident(id=existing.id, **incident_data.model_dump())
    incidents[incidents.index(existing)] = updated
    return updated
```

The "Update incident #1" button sends domain-appropriate values for the primary field
(`routeId`) and secondary field (`location`), then reloads the list.

**[SCREENSHOT 6]** — the list before and after, showing record #1 changed to
"Line 22 (Rerouted)" at "Downtown Transit Center - Bay 4".

### 2.3 Delete the record with the highest ID

```python
@app.delete("/api/incidents/{incident_id}", response_model=TransitIncident)
async def delete_incident(incident_id: int, response: Response = None):
    no_store(response)
    incident = find_incident(incident_id)
    incidents.remove(incident)
    return incident
```

```javascript
const highest = await requestJSON("/api/incidents-highest-id");
await requestJSON(`${API}/${highest}`, { method: "DELETE" });
await loadIncidents();
```

**[SCREENSHOT 7]** — the list before and after clicking "Delete newest".

### 2.4 Search by primary or secondary field

```python
@app.get("/api/incidents", response_model=List[TransitIncident])
async def get_incidents(search: Optional[str] = None, response: Response = None):
    no_store(response)
    if not search or not search.strip():
        return incidents
    term = search.strip().lower()
    return [i for i in incidents
            if term in i.routeId.lower() or term in i.location.lower()]
```

Case-insensitive substring match against `routeId` (primary) and `location` (secondary).

**[SCREENSHOT 8]** — a search term entered and the list filtered to matching records only.

---

## Part 3 — Stateful agent graph

Implemented in `code/agents_graph.py`. HW1's Planner → Reviewer → Finalizer waterfall is
replaced by a graph that can loop back for self-correction and stops at a turn ceiling.

```
START → supervisor → router_logic ─→ planner  → supervisor
                                  ─→ reviewer → supervisor
                                  ─→ END
```

### Shared state

```python
class AgentState(TypedDict):
    title: str; content: str; email: str; strict: bool; task: str
    llm: Any                        # ModelClient from src/model_client.py
    planner_proposal: Dict[str, Any]
    reviewer_feedback: Dict[str, Any]
    turn_count: int
    turn_ceiling: int
    valid: bool
    validation_error: str
    validation_history: List[str]
    planner_attempts: int           # every Planner call, whatever sent it back
    schema_retries: int             # only the calls that FAILED Pydantic validation
    issue_history: List[str]
```

The two counters are deliberately separate. The Reviewer can send a proposal back for
content reasons, which is not a schema failure; conflating them would make the Part 4.3
table measure how picky the Reviewer is rather than how often the schema is satisfied.

### The supervisor and the router

```python
def supervisor_node(state: AgentState) -> Dict[str, Any]:
    turn = state["turn_count"] + 1
    print(f"--- NODE: Supervisor (turn {turn}/{state['turn_ceiling']}) ---")
    return {"turn_count": turn}


def router_logic(state: AgentState) -> str:
    if state["turn_count"] >= state["turn_ceiling"]:
        return END                        # checked FIRST and unconditionally
    if not state["valid"]:
        return "planner"                  # nothing proposed yet, or it failed validation
    feedback = state.get("reviewer_feedback") or {}
    if not feedback:
        return "reviewer"                 # not yet reviewed
    if feedback.get("issues"):
        return "planner"                  # correct the Reviewer's objections
    return END                            # valid and reviewed clean
```

The ceiling check comes first and unconditionally. In any other order, a proposal that
keeps failing validation loops forever, because the retry branch fires before the stop
condition is ever consulted.

### Model-client routing

Both nodes call the adapter, never Ollama or LangChain directly:

```python
raw = state["llm"].complete(messages)     # planner_node, line 133
raw = state["llm"].complete(messages)     # reviewer_node, line 179
```

`verify_hw02.py` checks this statically, since a direct `ChatOllama` call would still
produce correct-looking output:

```
[PASS] routing:no_direct_model_calls
[PASS] routing:all_llm_calls_via_model_client -- 2/2 call sites use state['llm'].complete()
```

**[SCREENSHOT 9]** — `python code/agents_graph.py --stream`, showing the node-by-node
path: Supervisor → Planner → Supervisor → Reviewer → Supervisor → END.

### Step 6 — testing the correction loop

The spec asks for the Reviewer to be made to always object, so the graph can be watched
routing back to the Planner. This is exposed as a flag rather than a temporary source
edit, so the demonstration is reproducible and there is nothing to remember to revert:

```bash
python code/agents_graph.py --force-reviewer-issue --turn-ceiling 6
```

Captured output (full transcript in `reports/hw02/raw/loop_test_part3_step6.txt`):

```
--- NODE: Supervisor (turn 1/6) ---
    router -> planner (no proposal yet)
--- NODE: Planner ---
    valid=True
--- NODE: Supervisor (turn 2/6) ---
    router -> reviewer (proposal not yet reviewed)
--- NODE: Reviewer ---
    issues=1 (forced)
--- NODE: Supervisor (turn 3/6) ---
    router -> planner (1 reviewer issues)      ← routed BACK to the Planner
--- NODE: Planner ---
    valid=True
--- NODE: Supervisor (turn 4/6) ---
    router -> reviewer (proposal not yet reviewed)
--- NODE: Reviewer ---
    issues=1 (forced)
--- NODE: Supervisor (turn 5/6) ---
    router -> planner (1 reviewer issues)      ← and back again
--- NODE: Planner ---
    valid=True
--- NODE: Supervisor (turn 6/6) ---
    router -> END (hit turn ceiling 6)         ← ceiling stops the infinite loop
```

This demonstrates both required behaviours at once: the conditional edge sends work back
to the Planner when the Reviewer objects, and the turn ceiling terminates a loop that
would otherwise never end.

**[SCREENSHOT 10]** — the above command and its output.

---

## Part 4 — Output schema and loop safety

Full tables and analysis in `reports/hw02/METRICS.md`. Raw data in `reports/hw02/raw/`.

### 4.1 Pydantic validation of Planner output

`src/schemas.py` — exactly three tags of 3–30 characters, summary of at most 25 words:

```python
class PlannerOutput(BaseModel):
    tags: List[str] = Field(..., min_length=3, max_length=3)
    summary: str

    @field_validator("tags")
    @classmethod
    def check_tag_lengths(cls, tags):
        for tag in tags:
            n = len(tag.strip())
            if n < 3 or n > 30:
                raise ValueError(f"tag {tag.strip()!r} is {n} characters; "
                                 f"each tag must be 3-30 characters")
        return tags

    @field_validator("summary")
    @classmethod
    def check_summary_length(cls, summary):
        n = len(summary.split())
        if n == 0: raise ValueError("summary is empty")
        if n > 25: raise ValueError(f"summary is {n} words; must be at most 25")
        return summary
```

Output is **never coerced**. This is a deliberate break from HW1's `coerce_reply()`,
which silently repairs bad output by padding tags and truncating the summary. Validating
coerced output would make every run "valid first attempt" by construction, leaving the
retry loop dead and Part 4.3 with nothing to measure.

### 4.2 Feeding the validation error back

```python
if state["validation_error"]:
    user_parts.append(
        "Your previous answer was rejected by schema validation:\n"
        f"{state['validation_error']}\n"
        "Return a corrected JSON object that fixes exactly that problem."
    )
```

The error text names the field and the fault, so the retry corrects a specific defect
rather than re-rolling the dice.

On this input the model never actually violates the schema (see 4.3), so the retry path is
demonstrated with a flag that corrupts the first Planner attempt — the same technique the
spec prescribes for the Step 6 loop test:

```bash
python code/agents_graph.py --force-schema-failure --turn-ceiling 8
```

Captured output (full transcript in `reports/hw02/raw/retry_test_part4_2.txt`):

```
--- NODE: Supervisor (turn 1/8) ---
    router -> planner (no proposal yet)
--- NODE: Planner ---
    [forced] first attempt truncated to 2 tags
    valid=False error=tags: List should have at least 3 items after validation, not 2
--- NODE: Supervisor (turn 2/8) ---
    router -> planner (schema invalid)          ← rejection routed back for correction
--- NODE: Planner ---
    valid=True                                  ← corrected using the error text
--- NODE: Supervisor (turn 3/8) ---
    router -> reviewer (proposal not yet reviewed)
--- NODE: Reviewer ---
    issues=1
--- NODE: Supervisor (turn 4/8) ---
    router -> planner (1 reviewer issues)
--- NODE: Planner ---
    valid=True
--- NODE: Supervisor (turn 5/8) ---
    router -> reviewer (proposal not yet reviewed)
--- NODE: Reviewer ---
    issues=0
--- NODE: Supervisor (turn 6/8) ---
    router -> END (valid and reviewed clean)
```

Both correction mechanisms are visible in one run: the schema rejection at turn 2 and the
Reviewer objection at turn 4, each routed back to the Planner and each fixed, all within
the turn ceiling.

**[SCREENSHOT 11]** — the above command and its output.

### 4.3 Thirty runs on the frozen input

Input: `reports/hw02/cases/schema_input.json`. Turn ceiling 8.

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---|---|
| Valid first attempt | **30** | 62,260 |
| Valid after 1 retry | 0 | — |
| Valid after 2+ retries | 0 | — |
| Hit turn ceiling | 0 | — |

Latency spread: min 60,575 ms, median 62,255 ms, max 65,301 ms.

Pydantic rejected nothing in 30 runs, so the schema retry path is not exercised here. At
temperature 0 on an ordinary single-topic incident, qwen3:8b reliably produces three tags
and a short summary — HW1's non-determinism experiment found the same determinism (1
distinct tag set across 20 runs at temperature 0.0).

The runs were not short, however: each took 7 turns and 3 Planner attempts, because the
*Reviewer* returned the proposal twice per run. Those are content objections, not schema
failures, and they are counted separately. Section 4.6 examines them — they turn out to be
wrong, and that is the most significant result in this assignment.

**[SCREENSHOT 12]** — the console summary at the end of the 30 runs.

### 4.4 Turn ceiling 2 versus 10

Same frozen input and model settings, 20 runs each.

| Turn ceiling | Runs | Completed | Completion rate | Mean latency (ms) | Turns used | Planner attempts |
|---|---|---|---|---|---|---|
| 2 | 20 | 0 | **0.0%** | 9,022 | 2 | 1 |
| 10 | 20 | 20 | **100.0%** | 61,168 | 7 | 3 |

**Ceiling 2 never completes, structurally.** The supervisor increments the counter before
every routing decision, so a ceiling of 2 buys exactly one worker turn: the Planner runs,
the counter reaches 2, and the router stops the graph before the Reviewer has ever seen
the proposal. The output is schema-valid but unreviewed. The rate is 0/20 rather than
merely low because completion is impossible by construction.

**Choice for deployment: ceiling 10.** Every completed run used exactly 7 turns, so the
minimum workable ceiling for this input is 7 — ceilings of 2, 4 and 6 would all fail. Ten
is the smallest offered option that clears 7 with margin for one more correction round.

The cost should be stated plainly: 61,168 ms against 9,022 ms, about **6.8×** the latency.
That is not the price of the ceiling itself but of letting the Reviewer loop run to
convergence — ceiling 2 is cheap precisely because it performs no review, which is the same
reason it never completes. Between a fast unreviewed answer and a slow reviewed one, the
reviewed one is deployable; but section 4.6 shows most of that 6.8× is spent on objections
that should never have been raised, so the honest recommendation is ceiling 10 **together
with** the fix proposed in 4.5.

**[SCREENSHOT 13]** — the ceiling comparison section of the console summary.

### 4.5 Adversarial input

`reports/hw02/cases/adversarial_input.json`. Turn ceiling 10, 5 runs.

| Metric | Result |
|---|---|
| Runs reaching the turn ceiling | **5 / 5 (100%)** |
| Turns used per run | 10, 10, 10, 10, 10 |
| Planner attempts per run | 5, 5, 5, 5, 5 |
| Schema retries per run | 0, 0, 0, 0, 0 |
| Mean latency | 149,383 ms |
| Versus the frozen input | **2.4× slower** |

**Why it causes trouble.** The input is a quarter-end digest spanning about ten distinct
sub-incidents. The schema allows 25 words. Ten sub-incidents cannot be stated in 25
words, so the Planner must generalise — *"Multiple transit routes and subsystems faced
delays, equipment outages, and vendor ticket issues with escalation."* The Reviewer then
objects under rule 2, that the summary asserts something the input does not state,
because no sentence in the input says "multiple subsystems faced outages"; the input
lists them individually.

The two constraints are in direct conflict: the word limit compels abstraction and the
faithfulness rule forbids it. All 20 objections across the 5 runs were rule 2, and the
final tag set was identical in every run — a reproducible structural failure, not noise.

**Proposed fix — a no-progress circuit breaker.** Hash each Reviewer objection set; if
the same objection is raised twice in a row, the loop is not converging and further turns
cannot help. Stop and return the current schema-valid proposal, flagged "accepted without
Reviewer sign-off". On this data that would cut the adversarial case from ~149s to
roughly 60s, and the ordinary frozen input from ~62s to ~40s, since section 4.6 shows its
two objections are the same complaint repeated.

**[SCREENSHOT 14]** — the adversarial section of the console summary, showing 5/5
reaching the ceiling.

### 4.6 An unplanned finding: the Reviewer is prompt-format sensitive

Two full 75-run batches were collected. Between them, **one thing changed in the
Reviewer's input: how the proposal was formatted.** Batch 1 passed it as
`json.dumps(proposal, indent=2)`; batch 2 passed it as plain text
(`Tags: a; b; c\nSummary: …`). Same model, same temperature, same input, same rules, same
validator, same machine.

| | Batch 1 (JSON framing) | Batch 2 (plain-text framing) |
|---|---|---|
| Reviewer objections across 30 runs | **0** | **60** |
| Turns per run | 3 | 7 |
| Planner attempts per run | 1 | 3 |
| Mean latency, frozen input | 10,862 ms | 62,260 ms |
| Completion rate, ceiling 10 | 20/20 | 20/20 |
| Completion rate, ceiling 2 | 0/20 | 0/20 |
| Adversarial ceiling hits | 5/5 | 5/5 |

**Every structural result reproduced exactly** — completion rates, ceiling behaviour and
adversarial outcomes are identical, which is direct evidence that those findings are
robust rather than artefacts of one run. What changed by a factor of six is latency, and
it changed entirely because of the Reviewer's objection rate.

**The objections were wrong.** All 60 were the same two:

```
[rule 1] 'Transit Center': The tag 'Transit Center' is about a subject the input never raises.
[rule 1] 'Bus Delay':      The tag 'Bus Delay' is about a subject the input never raises.
```

The input reads *"Delayed Line 22 bus at Downtown Transit Center … the 7:15am bus never
arrived."* Both tags are plainly supported. The Reviewer's own prompt names these exact
cases as acceptable — *"'Transit Center' for 'Downtown Transit Center' … must not be
reported"* — so the model was told, in the same prompt, not to make the objection it then
made 60 times. The loop still converged, because the Planner swapped the rejected tags for
wordier synonyms until the Reviewer stopped objecting. The six-fold latency bought nothing.

**What this means.** An instruction-following failure this specific cannot be fixed by
adding more instruction; the counter-example was already present and was ignored. Two
conclusions follow:

1. **Prompt formatting is a live variable, not presentation.** A change most engineers
   would treat as cosmetic flipped the objection rate from 0% to 100%. Measurements taken
   across a prompt change are not comparable — which is why both batches are retained
   rather than only the newer one.
2. **Enforce contracts in code, not in prose.** These objections satisfied the
   `ReviewIssue` contract: well-formed, correctly quoting real text. They were merely
   wrong. That is the limit of what a schema can catch, and it is why the circuit breaker
   proposed in 4.5 is the right defence — it does not require the Reviewer to be correct,
   only requires noticing the loop has stopped making progress.

JSON framing was not simply the better of the two: under it the Reviewer objected to the
`{` and `}` of the serialisation itself under rule 3 (see
`raw/discarded_adversarial_prompt_bug.jsonl`). Both framings produce spurious objections;
they differ in which ones, and on which input.

---

## Verification

`python code/verify_hw02.py` → `reports/hw02/verification.json`

The smoke test starts the FastAPI backend on PORT_BASE and exercises it over HTTP, then
runs the graph once under a timeout. Every check is behavioural, never a text match — it
asserts "did it return exactly 3 tags?" and "did the request succeed?", not specific
wording, because the model never says the same thing twice.

**46 / 46 checks passed.**

**[SCREENSHOT 15]** — the `verify_hw02.py` console output showing 40/40.

---

## Reproducing

```bash
source .venv/bin/activate
pip install -r requirements.txt

# Parts 1 & 2 - front end + API on PORT_BASE 8470
cd code/web_application && uvicorn app:app --port 8470

# Part 3 - one graph run, streaming each node's state update
python code/agents_graph.py --stream
python code/agents_graph.py --force-reviewer-issue --turn-ceiling 6   # Step 6 loop test
python code/agents_graph.py --force-schema-failure --turn-ceiling 8   # 4.2 retry demo

# Part 4 - all 75 runs (measured: 66 minutes on this hardware)
caffeinate -i python code/run_schema_experiments.py 2>&1 | tee reports/hw02/RUN_LOG.txt
python code/run_schema_experiments.py --summarize-only   # rebuild tables from saved runs

# Verification
python code/verify_hw02.py
```

Omit `--reload` when serving: records are held in memory, so the auto-restart it performs
on any file save silently resets the list.

### Where the experiment data lives

| What | Where |
|---|---|
| Every run individually (all 75) | **Appendix A** of this report |
| Real console output with timestamps | `reports/hw02/RUN_LOG.txt` — 2,136 lines |
| Machine-readable per-run records | `reports/hw02/raw/runs.jsonl`, `raw/schema_runs.csv` |
| Computed summary tables | `reports/hw02/raw/schema_summary.json` |
| Frozen inputs used | `reports/hw02/cases/` |

## Use of AI assistance

See `reports/hw02/AI_USE.md`.

---

## Appendix A — All 75 experiment runs

Every run behind the tables above, in the order executed. Full console output with
timestamps is in `reports/hw02/RUN_LOG.txt` (2,136 lines); machine-readable copies are
in `reports/hw02/raw/schema_runs.csv` and `runs.jsonl`.

`retries` counts Pydantic rejections only. `turns` is how many supervisor turns the run
used before stopping. A run is `hit ceiling` when it stopped because turns ran out
rather than because the Reviewer signed off.


### 4.3 Schema validation — 30 runs, ceiling 8

| # | Outcome | Attempts | Retries | Turns | Hit ceiling | Latency (ms) |
|--:|---|--:|--:|--:|:-:|--:|
| 1 | valid first attempt | 3 | 0 | 7 | no | 65,301 |
| 2 | valid first attempt | 3 | 0 | 7 | no | 63,689 |
| 3 | valid first attempt | 3 | 0 | 7 | no | 61,761 |
| 4 | valid first attempt | 3 | 0 | 7 | no | 61,040 |
| 5 | valid first attempt | 3 | 0 | 7 | no | 60,575 |
| 6 | valid first attempt | 3 | 0 | 7 | no | 61,880 |
| 7 | valid first attempt | 3 | 0 | 7 | no | 61,432 |
| 8 | valid first attempt | 3 | 0 | 7 | no | 60,876 |
| 9 | valid first attempt | 3 | 0 | 7 | no | 62,100 |
| 10 | valid first attempt | 3 | 0 | 7 | no | 61,591 |
| 11 | valid first attempt | 3 | 0 | 7 | no | 60,643 |
| 12 | valid first attempt | 3 | 0 | 7 | no | 62,870 |
| 13 | valid first attempt | 3 | 0 | 7 | no | 63,530 |
| 14 | valid first attempt | 3 | 0 | 7 | no | 62,119 |
| 15 | valid first attempt | 3 | 0 | 7 | no | 62,070 |
| 16 | valid first attempt | 3 | 0 | 7 | no | 62,061 |
| 17 | valid first attempt | 3 | 0 | 7 | no | 62,391 |
| 18 | valid first attempt | 3 | 0 | 7 | no | 62,525 |
| 19 | valid first attempt | 3 | 0 | 7 | no | 62,692 |
| 20 | valid first attempt | 3 | 0 | 7 | no | 62,038 |
| 21 | valid first attempt | 3 | 0 | 7 | no | 61,480 |
| 22 | valid first attempt | 3 | 0 | 7 | no | 62,778 |
| 23 | valid first attempt | 3 | 0 | 7 | no | 62,933 |
| 24 | valid first attempt | 3 | 0 | 7 | no | 62,315 |
| 25 | valid first attempt | 3 | 0 | 7 | no | 62,295 |
| 26 | valid first attempt | 3 | 0 | 7 | no | 62,394 |
| 27 | valid first attempt | 3 | 0 | 7 | no | 62,882 |
| 28 | valid first attempt | 3 | 0 | 7 | no | 62,668 |
| 29 | valid first attempt | 3 | 0 | 7 | no | 62,665 |
| 30 | valid first attempt | 3 | 0 | 7 | no | 62,215 |

*30 runs · mean latency 62,260 ms · 0 reached the ceiling*


### 4.4 Ceiling 2 — 20 runs

| # | Outcome | Attempts | Retries | Turns | Hit ceiling | Latency (ms) |
|--:|---|--:|--:|--:|:-:|--:|
| 1 | valid first attempt | 1 | 0 | 2 | yes | 9,831 |
| 2 | valid first attempt | 1 | 0 | 2 | yes | 8,826 |
| 3 | valid first attempt | 1 | 0 | 2 | yes | 8,971 |
| 4 | valid first attempt | 1 | 0 | 2 | yes | 9,121 |
| 5 | valid first attempt | 1 | 0 | 2 | yes | 8,829 |
| 6 | valid first attempt | 1 | 0 | 2 | yes | 8,954 |
| 7 | valid first attempt | 1 | 0 | 2 | yes | 8,882 |
| 8 | valid first attempt | 1 | 0 | 2 | yes | 8,990 |
| 9 | valid first attempt | 1 | 0 | 2 | yes | 8,804 |
| 10 | valid first attempt | 1 | 0 | 2 | yes | 8,991 |
| 11 | valid first attempt | 1 | 0 | 2 | yes | 8,976 |
| 12 | valid first attempt | 1 | 0 | 2 | yes | 9,196 |
| 13 | valid first attempt | 1 | 0 | 2 | yes | 9,070 |
| 14 | valid first attempt | 1 | 0 | 2 | yes | 8,978 |
| 15 | valid first attempt | 1 | 0 | 2 | yes | 9,032 |
| 16 | valid first attempt | 1 | 0 | 2 | yes | 8,942 |
| 17 | valid first attempt | 1 | 0 | 2 | yes | 9,051 |
| 18 | valid first attempt | 1 | 0 | 2 | yes | 8,929 |
| 19 | valid first attempt | 1 | 0 | 2 | yes | 8,939 |
| 20 | valid first attempt | 1 | 0 | 2 | yes | 9,134 |

*20 runs · mean latency 9,022 ms · 20 reached the ceiling*


### 4.4 Ceiling 10 — 20 runs

| # | Outcome | Attempts | Retries | Turns | Hit ceiling | Latency (ms) |
|--:|---|--:|--:|--:|:-:|--:|
| 1 | valid first attempt | 3 | 0 | 7 | no | 62,500 |
| 2 | valid first attempt | 3 | 0 | 7 | no | 63,193 |
| 3 | valid first attempt | 3 | 0 | 7 | no | 62,522 |
| 4 | valid first attempt | 3 | 0 | 7 | no | 60,449 |
| 5 | valid first attempt | 3 | 0 | 7 | no | 61,285 |
| 6 | valid first attempt | 3 | 0 | 7 | no | 61,887 |
| 7 | valid first attempt | 3 | 0 | 7 | no | 60,515 |
| 8 | valid first attempt | 3 | 0 | 7 | no | 61,796 |
| 9 | valid first attempt | 3 | 0 | 7 | no | 61,363 |
| 10 | valid first attempt | 3 | 0 | 7 | no | 60,466 |
| 11 | valid first attempt | 3 | 0 | 7 | no | 61,043 |
| 12 | valid first attempt | 3 | 0 | 7 | no | 60,537 |
| 13 | valid first attempt | 3 | 0 | 7 | no | 60,876 |
| 14 | valid first attempt | 3 | 0 | 7 | no | 60,499 |
| 15 | valid first attempt | 3 | 0 | 7 | no | 60,492 |
| 16 | valid first attempt | 3 | 0 | 7 | no | 61,057 |
| 17 | valid first attempt | 3 | 0 | 7 | no | 61,363 |
| 18 | valid first attempt | 3 | 0 | 7 | no | 60,794 |
| 19 | valid first attempt | 3 | 0 | 7 | no | 60,613 |
| 20 | valid first attempt | 3 | 0 | 7 | no | 60,101 |

*20 runs · mean latency 61,167 ms · 0 reached the ceiling*


### 4.5 Adversarial — 5 runs, ceiling 10

| # | Outcome | Attempts | Retries | Turns | Hit ceiling | Latency (ms) |
|--:|---|--:|--:|--:|:-:|--:|
| 1 | valid first attempt | 5 | 0 | 10 | yes | 162,970 |
| 2 | valid first attempt | 5 | 0 | 10 | yes | 147,042 |
| 3 | valid first attempt | 5 | 0 | 10 | yes | 145,975 |
| 4 | valid first attempt | 5 | 0 | 10 | yes | 145,635 |
| 5 | valid first attempt | 5 | 0 | 10 | yes | 145,295 |

*5 runs · mean latency 149,383 ms · 5 reached the ceiling*
