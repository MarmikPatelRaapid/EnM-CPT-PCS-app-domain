# PCS Code Detection — Architecture Plan

## Context

ICD-10-PCS codes are 7-character alphanumeric strings where each position encodes a specific clinical dimension (Section, Body System, Operation, etc.). This system automates detection of PCS codes from patient documents using two LLM agents:
- **Agent 1** extracts identifiable procedures (entities) from the document.
- **Agent 2** determines the next valid PCS character(s) through recursive, parallelized tree traversal driven by two TSV reference files.

The output is a set of PCS codes per entity, classified as **billable** (7-char complete) or **non-billable** (< 7-char, tree stopped before completion due to no evidence).

---

## Key Design Decisions

### 1. Agent 2 Output Schema (Updated)

Agent 2 returns **multiple valid next characters per call** (e.g., out of 5 possibilities, 3 may be confirmed by evidence). Each qualified character is its own object inside `next_character_data`:

```json
{
    "norm_procedure": "string",
    "current_code": "string",
    "next_character_data": [
        {
            "next_character_value": "1",
            "next_character_desc": "Obstetrics",
            "next_character_evidences": [
                {"text": "...", "pg_no": 1, "reftxtbefore": "...", "reftxtafter": "..."}
            ]
        },
        {
            "next_character_value": "2",
            "next_character_desc": "Placement",
            "next_character_evidences": [...]
        },
        {
            "next_character_value": "A",
            "next_character_desc": "New Technology",
            "next_character_evidences": [...]
        }
    ]
}
```

> **Prompt update needed (vault)**: Agent 2 prompt must be updated to say "Select ALL options supported by evidence" instead of "Select the most appropriate option", to enable multi-value returns.

### 2. Agent 2 Input Structure (Fixed)

From `schemas/agent_2_input_structure.json`, Agent 2 receives a fixed JSON alongside the document pages:

```json
{
    "norm_procedure": "Laparoscopic Appendectomy",
    "current_code": "001",
    "evidences": {
        "evidence_for_first_character":  [...],
        "evidence_for_second_character": [...],
        "evidence_for_third_character":  [...]
    }
}
```

- `evidences` is a cumulative map: populated up to `len(current_code)` characters
- At start (`current_code = ""`), `evidences` is an empty dict `{}`
- Each Agent 2 response adds a new entry into `evidences` before the next recursive call

### 3. Evidence Accumulation in Tree Nodes

Each tree node carries the **full accumulated evidence history**. When Agent 2 returns `next_character_evidences` for char `X`:
- `new_code = current_code + X`
- `new_evidences = copy(current_evidences) + {evidence_for_Nth_character: next_character_evidences["X"]}`
- A new branch is spawned with `(new_code, new_evidences)`

### 4. LLM Auth — Managed Identity Only (No API Keys)

Based on `onpoint_ner_extraction.py`, all LLM clients authenticate via managed identity:

| Provider | Auth mechanism |
|---|---|
| **Google Gemini** | `genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)` |
| **Azure OpenAI** | `DefaultAzureCredential` → `get_bearer_token_provider(...)` |
| **Claude via Vertex AI** | `anthropic[vertex]` SDK with Vertex AI credentials |
| **OpenAI (direct)** | `DefaultAzureCredential` or env-managed token (no hardcoded key) |

No API keys anywhere in code. Identity is resolved from the runtime environment (GCP service account, Azure managed identity).

### 5. Parallelism Model

`asyncio` + `asyncio.gather` for all concurrent Agent 2 calls. A shared `asyncio.Semaphore(MAX_CONCURRENCY)` prevents unbounded fan-out from overwhelming rate limits. Pattern is consistent with `ThreadPoolExecutor` in reference script but adapted to async since tree traversal is recursive.

---

## Directory Structure

```
PCS_Code_Detection/
├── config.py                          ← Provider, model, project, concurrency config
├── main.py                            ← Entry point: run(txt_file_path)
│
├── prompts/                           ← Prompt templates (dev; prod: vault)
│   ├── Agent 1 - ICD-10-PCS Code Suggestion Prompt.txt
│   └── Agent 2 - ICD-10-PCS Dynamic Code Detection Prompt.txt
│
├── resources/                         ← Reference data (pre-loaded once at startup)
│   ├── digit_wise_header.tsv          ← first_digit + position → digit type label
│   └── pcs_traversal.tsv             ← current_string → [(next_code, next_label)]
│
├── schemas/
│   ├── agent_1_schema.json            ← Existing, no change
│   ├── agent_2_input_structure.json   ← Existing, defines input JSON shape
│   └── agent_2_schema.json           ← UPDATE: next_character_values → list[str]
│                                         next_character_evidences → dict[str, list]
│
├── tests/                             ← pytest test suite (separate folder)
│   ├── conftest.py                    ← shared fixtures and mock factories
│   ├── fixtures/                      ← static JSON/txt test data
│   ├── unit/                          ← per-module unit tests
│   └── integration/                   ← full pipeline tests with mocked LLM
│
└── src/
    ├── prompt_loader.py               ← fetch_prompt(name) → str
    ├── document_reader.py             ← read_txt(path) → dict[int, str]
    ├── pcs_resources.py               ← PCSResources (TSV loading + lookup)
    │
    ├── llm/
    │   ├── base.py                    ← Abstract LLMProvider + get_provider() factory
    │   ├── gemini_vertex.py           ← GeminiVertexProvider (managed identity)
    │   ├── azure_openai.py            ← AzureOpenAIProvider (DefaultAzureCredential)
    │   ├── claude_vertex.py           ← ClaudeVertexProvider (Vertex AI)
    │   └── openai_provider.py         ← OpenAIProvider (env token, no hardcoded key)
    │
    ├── agents/
    │   ├── agent1.py                  ← run_agent1(pages, llm) → list[Procedure]
    │   └── agent2.py                  ← run_agent2(pages, node, resources, llm) → list[dict]
    │                                      (each dict = one next_character_data item)
    │
    ├── tree/
    │   ├── models.py                  ← PCSNode, PCSCode dataclasses
    │   └── traversal.py              ← async expand_node(...) → list[PCSCode]
    │
    └── result_collector.py            ← classify(codes) → {billable, non_billable}
```

---

## Module Responsibilities

### `config.py`
```python
LLM_PROVIDER    = "gemini_vertex"    # "azure_openai" | "claude_vertex" | "openai"
MODEL_NAME      = "gemini-2.5-flash"
PROJECT_ID      = "prod-raapid-genai"  # GCP project (Gemini / Claude on Vertex)
LOCATION        = "global"
AZURE_ENDPOINT  = ""                 # for azure_openai provider
AZURE_API_VER   = "2024-02-01"
MAX_CONCURRENCY = 20                 # shared semaphore across all Agent 2 calls
RETRY_ATTEMPTS  = 5
TEMPERATURE     = 0.30
TOP_P           = 0.20
```
> Switching providers = change `LLM_PROVIDER` + `MODEL_NAME`. Nothing else.

---

### `src/prompt_loader.py`
```python
def fetch_prompt(prompt_name: str) -> str:
    # TODO (production): replace body with Azure Key Vault / GCP Secret Manager call
    path = PROMPT_DIR / prompt_name
    return path.read_text(encoding="utf-8")
```

---

### `src/pcs_resources.py` — PCSResources
Loads both TSVs into memory dicts once at startup (192K rows, fast dict lookup):

```python
class PCSResources:
    def get_next_options(self, current_string: str) -> list[tuple[str, str]]:
        # returns [(next_code, next_label), ...] from pcs_traversal.tsv

    def get_digit_type(self, first_digit: str, position: int) -> str:
        # returns label from digit_wise_header.tsv
        # first_digit="" at position 1 → always returns "Section"
```

---

### `src/llm/base.py`
```python
class LLMProvider(ABC):
    @abstractmethod
    async def call_async(
        self,
        system_prompt: str,
        user_content: str,
    ) -> str: ...

def get_provider() -> LLMProvider:
    # reads config.LLM_PROVIDER, returns the matching implementation
```

---

### `src/llm/gemini_vertex.py`
```python
class GeminiVertexProvider(LLMProvider):
    def __init__(self):
        # Managed identity via Vertex AI — no API key
        self.client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

    async def call_async(self, system_prompt, user_content) -> str:
        config = types.GenerateContentConfig(
            temperature=TEMPERATURE, top_p=TOP_P,
            max_output_tokens=65536,
            response_mime_type="application/json",
            system_instruction=[types.Part.from_text(text=system_prompt)],
        )
        response = await self.client.aio.models.generate_content(
            model=MODEL_NAME,
            contents=[types.Content(role="user", parts=[types.Part.from_text(user_content)])],
            config=config,
        )
        return response.text
```

---

### `src/llm/azure_openai.py`
```python
class AzureOpenAIProvider(LLMProvider):
    def __init__(self):
        # Managed identity via DefaultAzureCredential — no API key
        from azure.identity.aio import DefaultAzureCredential
        from azure.identity import get_bearer_token_provider
        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        self.client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_ENDPOINT,
            azure_ad_token_provider=token_provider,
            api_version=AZURE_API_VER,
        )
```

---

### `src/agents/agent1.py`
- Fetches prompt via `fetch_prompt("Agent 1 - ...")`
- Sends `json.dumps({page_no: text, ...})` as user content
- Enforces `agent_1_schema.json` on parsed response
- Returns `list[Procedure]` (each has `norm_procedure_name` + `procedure_evidences`)

---

### `src/agents/agent2.py`

**Placeholder replacement** for Agent 2 prompt:

| Placeholder | Value source |
|---|---|
| `[##Current value = 4A0##]` | `node.current_code` |
| `[##Next Digit = 4th##]` | `ordinal(len(node.current_code) + 1)` |
| `[##next digit type = Body System##]` | `PCSResources.get_digit_type(first_digit, pos)` |
| `[##next possible list = [...]##]` | `get_next_options(current_code)` → `[X: Label, ...]` |
| `[##list##]` | char keys only → `[X, Y, Z]` |

**Input assembly** sent to LLM as user content:
```
--- CLINICAL DOCUMENT ---
{page-wise text as JSON}

--- PCS TRAVERSAL STATE ---
{agent_2_input_structure JSON with norm_procedure, current_code, evidences}
```

Returns `list[dict]` — the raw `next_character_data` array from Agent 2's response. Each dict has `next_character_value`, `next_character_desc`, and `next_character_evidences`.

---

### `src/tree/models.py`
```python
@dataclass
class PCSNode:
    procedure: Procedure
    current_code: str                 # "" → "0" → "00" → ... → "0016070"
    accumulated_evidences: dict       # {"evidence_for_first_character": [...], ...}

@dataclass
class PCSCode:
    code: str
    procedure_name: str
    status: Literal["billable", "non_billable"]
    evidences: dict                   # full 7-position evidence map
```

---

### `src/tree/traversal.py` — Async Recursive Expansion

```python
POSITION_KEYS = [
    "evidence_for_first_character", "evidence_for_second_character",
    "evidence_for_third_character", "evidence_for_fourth_character",
    "evidence_for_fifth_character", "evidence_for_sixth_character",
    "evidence_for_seventh_character",
]

async def expand_node(
    node: PCSNode, pages: dict, resources: PCSResources,
    llm: LLMProvider, semaphore: asyncio.Semaphore
) -> list[PCSCode]:

    # Terminal: 7-char code reached → billable
    if len(node.current_code) == 7:
        return [PCSCode(node.current_code, node.procedure.norm_procedure_name,
                        "billable", node.accumulated_evidences)]

    # TSV dead-end → non-billable
    next_options = resources.get_next_options(node.current_code)
    if not next_options:
        return [PCSCode(node.current_code, node.procedure.norm_procedure_name,
                        "non_billable", node.accumulated_evidences)]

    # Call Agent 2 (rate-limited)
    async with semaphore:
        branches = await run_agent2(pages, node, next_options, resources, llm)

    # No evidence found for any option → non-billable
    if not branches:
        return [PCSCode(node.current_code, node.procedure.norm_procedure_name,
                        "non_billable", node.accumulated_evidences)]

    # Spawn child nodes for each qualified char, expand in parallel
    # branches is list[dict] matching next_character_data schema:
    #   [{"next_character_value": "1", "next_character_desc": "...", "next_character_evidences": [...]}]
    child_tasks = []
    for item in branches:
        char = item["next_character_value"]
        char_evidences = item["next_character_evidences"]
        position_key = POSITION_KEYS[len(node.current_code)]
        new_evidences = {**node.accumulated_evidences, position_key: char_evidences}
        child = PCSNode(node.procedure, node.current_code + char, new_evidences)
        child_tasks.append(expand_node(child, pages, resources, llm, semaphore))

    results = await asyncio.gather(*child_tasks)
    return [code for batch in results for code in batch]
```

---

### `main.py` — Orchestrator

```python
async def run(txt_file_path: str) -> dict:
    pages     = read_txt(txt_file_path)          # {page_no: text}
    llm       = get_provider()                   # from config.LLM_PROVIDER
    resources = PCSResources()                   # TSVs loaded once

    procedures = await run_agent1(pages, llm)    # one LLM call

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    root_tasks = [
        expand_node(
            PCSNode(proc, current_code="", accumulated_evidences={}),
            pages, resources, llm, semaphore
        )
        for proc in procedures
    ]
    all_codes = await asyncio.gather(*root_tasks)
    return classify(flatten(all_codes))
```

---

## Execution Flow (Visual)

```
txt file
   │
   ▼
Document Reader ──► {1: "page1 text", 2: "page2 text", ...}
   │
   ▼
Agent 1 (1 LLM call) ──► [Procedure_A, Procedure_B, Procedure_C]
   │
   ▼  asyncio.gather (one task per procedure)
   ├── expand_node(Procedure_A, code="")
   │     Agent 2 call ──► qualified: ["0", "B"]
   │     ├── expand_node(Procedure_A, code="0")
   │     │     Agent 2 call ──► qualified: ["0"]
   │     │     └── expand_node(Procedure_A, code="00")  ...→ 7 chars → BILLABLE
   │     └── expand_node(Procedure_A, code="B")
   │           Agent 2 call ──► qualified: []  → NON-BILLABLE (no evidence)
   │
   ├── expand_node(Procedure_B, code="")
   │     Agent 2 call ──► qualified: ["1"]
   │     └── ... recurse to depth 7
   │
   └── expand_node(Procedure_C, code="")
         Agent 2 call ──► qualified: ["0", "D"]
         ├── ...
         └── ...
   │
   ▼
Result Collector
   {
     billable:     [PCSCode("0016070", "Procedure_A"), ...],
     non_billable: [PCSCode("B", "Procedure_A"), ...]
   }
```

All Agent 2 calls across all levels and all procedures share one `asyncio.Semaphore(MAX_CONCURRENCY)`.

---

## LLM Call Mode

`LLM_CALL_MODE = "on_demand"` in `config.py` — this is the only supported mode.

Each LLM request is dispatched immediately and its result is awaited before the caller proceeds. All calls go through `LLMProvider.call_async()` → `_call_once()` with exponential-backoff retry. Concurrency is controlled by `asyncio.Semaphore(MAX_CONCURRENCY)` shared across all tree nodes.

> **Future work — batch mode:** Provider batch APIs (Claude Message Batches, OpenAI/Azure Batch, Vertex AI Batch Prediction) offer ~50 % cost savings for offline workloads but have multi-minute to 24-hour turnaround times. Supporting batch mode for Agent 2 would require rewriting the tree traversal from depth-first recursion to level-by-level BFS (so all calls at the same depth can be collected and submitted together). This is deferred; the `LLM_CALL_MODE` variable is the designated hook for that future switch.

---

## Retry & Rate Limiting

Mirrors `onpoint_ner_extraction.py` pattern:
- Retry on HTTP 429 / 503 with exponential backoff (`2^attempt` seconds)
- `RETRY_ATTEMPTS = 5` configurable in `config.py`
- Semaphore caps concurrent in-flight calls at `MAX_CONCURRENCY`
- Retry logic lives in `LLMProvider.call_async` base class as a wrapper

---

## Files to Create / Modify

| File | Action |
|---|---|
| `config.py` | Create |
| `main.py` | Create |
| `schemas/agent_2_schema.json` | Update: replace single-value fields with `next_character_data` array of `{next_character_value, next_character_desc, next_character_evidences}` objects |
| `src/prompt_loader.py` | Create |
| `src/document_reader.py` | Create |
| `src/pcs_resources.py` | Create |
| `src/llm/base.py` | Create |
| `src/llm/gemini_vertex.py` | Create (pattern from `onpoint_ner_extraction.py`) |
| `src/llm/azure_openai.py` | Create |
| `src/llm/claude_vertex.py` | Create |
| `src/llm/openai_provider.py` | Create |
| `src/agents/agent1.py` | Create |
| `src/agents/agent2.py` | Create |
| `src/tree/models.py` | Create |
| `src/tree/traversal.py` | Create |
| `src/result_collector.py` | Create |
| `tests/conftest.py` | Create |
| `tests/fixtures/sample_document.txt` | Create |
| `tests/fixtures/agent1_response.json` | Create |
| `tests/fixtures/agent2_response.json` | Create |
| `tests/unit/test_pcs_resources.py` | Create |
| `tests/unit/test_placeholder_fill.py` | Create |
| `tests/unit/test_document_reader.py` | Create |
| `tests/unit/test_prompt_loader.py` | Create |
| `tests/unit/test_agent1.py` | Create |
| `tests/unit/test_agent2.py` | Create |
| `tests/unit/test_traversal.py` | Create |
| `tests/unit/test_result_collector.py` | Create |
| `tests/integration/test_pipeline.py` | Create |

> **Prompt update (vault)**: Agent 2 prompt must be updated to instruct the model to return all evidence-supported characters, not just the single best one.

---

## Test Suite

### Test Directory Structure

```
PCS_Code_Detection/
└── tests/
    ├── conftest.py                    ← shared fixtures and mock factories
    ├── fixtures/
    │   ├── sample_document.txt        ← fake clinical document (2 pages)
    │   ├── agent1_response.json       ← valid Agent 1 LLM output
    │   └── agent2_response.json       ← valid Agent 2 LLM output (next_character_data)
    ├── unit/
    │   ├── test_pcs_resources.py      ← TSV lookup logic
    │   ├── test_prompt_loader.py      ← file-based prompt loading
    │   ├── test_document_reader.py    ← txt → page dict
    │   ├── test_placeholder_fill.py   ← Agent 2 prompt placeholder replacement
    │   ├── test_agent1.py             ← Agent 1 with mocked LLM
    │   ├── test_agent2.py             ← Agent 2 with mocked LLM
    │   ├── test_traversal.py          ← tree expansion with mocked Agent 2
    │   └── test_result_collector.py   ← billable/non-billable classification
    └── integration/
        └── test_pipeline.py           ← full pipeline with fully mocked LLM
```

Dependencies: `pytest`, `pytest-asyncio`, `pytest-mock`

---

### `tests/conftest.py` — Shared Fixtures

```python
import pytest, json, asyncio
from unittest.mock import AsyncMock
from src.tree.models import PCSNode, Procedure
from src.pcs_resources import PCSResources

@pytest.fixture(scope="session")
def resources():
    return PCSResources()   # loads real TSVs once for all tests

@pytest.fixture
def sample_pages():
    return {1: "Patient underwent laparoscopic appendectomy.", 2: "No complications noted."}

@pytest.fixture
def sample_procedure():
    return Procedure(
        norm_procedure_name="Laparoscopic Appendectomy",
        procedure_evidences=[{"text": "laparoscopic appendectomy", "pg_no": 1,
                               "reftxtbefore": "underwent ", "reftxtafter": ". No comp"}]
    )

@pytest.fixture
def make_mock_llm():
    """Factory: returns a mock LLMProvider whose call_async returns the given JSON string."""
    def _make(response_json: dict):
        mock = AsyncMock()
        mock.call_async.return_value = json.dumps(response_json)
        return mock
    return _make

@pytest.fixture
def agent1_response():
    return {
        "procedures": [
            {"norm_procedure_name": "Laparoscopic Appendectomy",
             "procedure_evidences": [{"text": "appendectomy", "pg_no": 1,
                                      "reftxtbefore": "underwent ", "reftxtafter": " No comp"}]}
        ]
    }

@pytest.fixture
def agent2_single_char_response():
    """Agent 2 returns exactly one qualified character."""
    return {
        "norm_procedure": "Laparoscopic Appendectomy",
        "current_code": "",
        "next_character_data": [
            {"next_character_value": "0",
             "next_character_desc": "Medical and Surgical",
             "next_character_evidences": [{"text": "appendectomy", "pg_no": 1,
                                           "reftxtbefore": "underwent ", "reftxtafter": " No comp"}]}
        ]
    }

@pytest.fixture
def agent2_multi_char_response():
    """Agent 2 returns two qualified characters (branching scenario)."""
    return {
        "norm_procedure": "Procedure X",
        "current_code": "",
        "next_character_data": [
            {"next_character_value": "0", "next_character_desc": "Medical and Surgical",
             "next_character_evidences": [{"text": "surgical", "pg_no": 1,
                                           "reftxtbefore": "xxx", "reftxtafter": "yyy"}]},
            {"next_character_value": "B", "next_character_desc": "Imaging",
             "next_character_evidences": [{"text": "imaging", "pg_no": 2,
                                           "reftxtbefore": "aaa", "reftxtafter": "bbb"}]}
        ]
    }

@pytest.fixture
def agent2_not_found_response():
    """Agent 2 finds no evidence for any option."""
    return {"norm_procedure": "Unknown Procedure", "current_code": "001",
            "next_character_data": []}
```

---

### `tests/unit/test_pcs_resources.py`

| Test | Scenario |
|---|---|
| `test_root_returns_all_sections` | `get_next_options("")` → 17 entries including `("0", "Medical and Surgical")` |
| `test_known_string_returns_children` | `get_next_options("0")` → non-empty list of body systems |
| `test_unknown_string_returns_empty` | `get_next_options("ZZZZZZZ")` → `[]` |
| `test_digit_type_position_1_always_section` | `get_digit_type("0", 1)` → `"Section"` |
| `test_digit_type_empty_first_digit_position_1` | `get_digit_type("", 1)` → `"Section"` |
| `test_digit_type_position_2_body_system` | `get_digit_type("0", 2)` → `"Body System"` |
| `test_digit_type_imaging_section_position_3` | `get_digit_type("B", 3)` → `"Type"` |
| `test_digit_type_unknown_first_digit` | `get_digit_type("Z", 2)` → raises `KeyError` or returns fallback |
| `test_next_options_7char_code_is_empty` | `get_next_options("0016070")` → `[]` (no 8th char exists) |

---

### `tests/unit/test_placeholder_fill.py`

| Test | Scenario |
|---|---|
| `test_current_value_replaced` | `current_code="4A0"` → `[##Current value = 4A0##]` is filled |
| `test_next_digit_ordinal_first` | `current_code=""` → "Next Digit = 1st" |
| `test_next_digit_ordinal_fourth` | `current_code="001"` → "Next Digit = 4th" |
| `test_next_digit_ordinal_seventh` | `current_code="001607"` → "Next Digit = 7th" |
| `test_digit_type_filled_from_tsv` | `current_code=""` → type = "Section"; `current_code="0"` → type = "Body System" |
| `test_next_possible_list_formatted` | `[("0","Med Surg"),("1","Obs")]` → `[0: Med Surg, 1: Obs]` in prompt |
| `test_list_placeholder_filled` | `[##list##]` → `[0, 1]` (keys only) |
| `test_no_remaining_placeholders` | After fill, assert `"[##"` does not appear in prompt |

---

### `tests/unit/test_agent1.py`

| Test | Scenario |
|---|---|
| `test_agent1_returns_procedures` | Mock LLM returns `agent1_response`; `run_agent1` returns `list[Procedure]` of length 1 |
| `test_agent1_validates_schema` | Mock LLM returns JSON missing `norm_procedure_name`; expect `ValidationError` |
| `test_agent1_handles_empty_procedures` | Mock returns `{"procedures": []}`; returns `[]` |
| `test_agent1_passes_all_pages` | Assert LLM `call_async` was called with content containing both page texts |
| `test_agent1_uses_system_prompt` | Assert system prompt argument contains PCS background text |

---

### `tests/unit/test_agent2.py`

| Test | Scenario |
|---|---|
| `test_agent2_returns_single_char` | Mock returns `agent2_single_char_response`; returns list with 1 item |
| `test_agent2_returns_multiple_chars` | Mock returns `agent2_multi_char_response`; returns list with 2 items |
| `test_agent2_empty_data_returns_empty_list` | Mock returns `agent2_not_found_response`; returns `[]` |
| `test_agent2_input_json_structure` | Assert `call_async` user content includes `norm_procedure`, `current_code`, `evidences` keys |
| `test_agent2_evidences_passed_correctly` | Node with `accumulated_evidences = {"evidence_for_first_character": [...]}` → verify it appears in LLM input |
| `test_agent2_validates_output_schema` | Mock returns malformed JSON (missing `next_character_data`); expect `ValidationError` |

---

### `tests/unit/test_traversal.py`

```python
# All tests use pytest.mark.asyncio
```

| Test | Scenario | Expected |
|---|---|---|
| `test_7char_code_is_billable` | Node with `current_code="0016070"` | Returns 1 `PCSCode` with `status="billable"` |
| `test_tsv_dead_end_is_non_billable` | `get_next_options` returns `[]` for `current_code` | Returns 1 `PCSCode` with `status="non_billable"` |
| `test_not_found_stops_expansion` | Agent 2 mock returns `[]` at depth 3 | Returns `PCSCode` with 3-char code, `non_billable` |
| `test_single_branch_linear_path` | Agent 2 always returns 1 char, depth 7 | Returns 1 billable 7-char code |
| `test_two_branch_expansion` | Agent 2 returns 2 chars at depth 1, then 1 char each until depth 7 | Returns 2 billable codes |
| `test_mixed_billable_non_billable` | Branch A reaches 7 chars; Branch B gets `[]` at depth 5 | Returns 1 billable + 1 non-billable |
| `test_evidence_accumulates_per_level` | Simulate 3-level traversal | `accumulated_evidences` has `evidence_for_first/second/third_character` keys |
| `test_semaphore_limits_concurrency` | Patch `asyncio.Semaphore`, verify `acquire` called per Agent 2 call | Semaphore acquired exactly N times for N nodes |

**Mock setup pattern for traversal tests:**

```python
@pytest.mark.asyncio
async def test_single_branch_linear_path(sample_procedure, sample_pages, resources):
    # Build a mock Agent 2 that always returns one char, cycling through "0","D","T","J","4","Z","Z"
    chars = ["0", "D", "T", "J", "4", "Z", "Z"]
    call_count = 0

    async def mock_agent2(pages, node, next_options, res, llm):
        nonlocal call_count
        char = chars[len(node.current_code)]
        call_count += 1
        return [{"next_character_value": char, "next_character_desc": "Test",
                 "next_character_evidences": []}]

    with patch("src.tree.traversal.run_agent2", side_effect=mock_agent2):
        node = PCSNode(sample_procedure, "", {})
        sem = asyncio.Semaphore(10)
        results = await expand_node(node, sample_pages, resources, AsyncMock(), sem)

    assert len(results) == 1
    assert results[0].code == "0DTJ4ZZ"
    assert results[0].status == "billable"
    assert call_count == 7
```

---

### `tests/unit/test_result_collector.py`

| Test | Scenario |
|---|---|
| `test_7char_classified_billable` | `PCSCode("0DTJ4ZZ", ..., "billable")` appears in `result["billable"]` |
| `test_short_code_classified_non_billable` | `PCSCode("0DT", ..., "non_billable")` appears in `result["non_billable"]` |
| `test_grouped_by_procedure` | Two codes for "Appendectomy", one for "Bypass" → two groups |
| `test_empty_input_returns_empty` | `classify([])` → `{"billable": [], "non_billable": []}` |

---

### `tests/integration/test_pipeline.py`

Full pipeline test with all LLM calls mocked — nothing real hits the network.

| Test | Scenario |
|---|---|
| `test_end_to_end_single_procedure_billable` | Agent 1 mock returns 1 entity; Agent 2 mock returns deterministic 7-char path → 1 billable code in output |
| `test_end_to_end_multi_procedure_parallel` | Agent 1 returns 3 entities; each gets its own tree → 3 independent results |
| `test_end_to_end_non_billable_stops_at_4` | Agent 2 returns valid chars for positions 1-4, empty for position 5 → 4-char non-billable code |
| `test_provider_swap_same_result` | Run pipeline with `GeminiVertexProvider` mock, then `AzureOpenAIProvider` mock; same result structure both times |
| `test_retry_on_429_succeeds` | First `call_async` raises HTTP 429; second returns valid response → success after retry |
| `test_max_retries_exceeded_raises` | `call_async` always raises 429 → propagates exception after `RETRY_ATTEMPTS` |

**Pattern:**

```python
@pytest.mark.asyncio
async def test_end_to_end_single_procedure_billable(
    tmp_path, agent1_response, make_mock_llm
):
    # Write sample txt
    doc = tmp_path / "patient.txt"
    doc.write_text("--- Page 1 ---\nPatient underwent laparoscopic appendectomy.")

    # Agent 1 mock
    agent1_mock = make_mock_llm(agent1_response)

    # Agent 2 mock: returns one char per call, spelling out "0DTJ4ZZ"
    chars = {"": "0", "0": "D", "0D": "T", "0DT": "J", "0DTJ": "4", "0DTJ4": "Z", "0DTJ4Z": "Z"}
    def agent2_side_effect(response):
        code = json.loads(response)["current_code"]  # simplified
        return json.dumps({"norm_procedure": "...", "current_code": code,
                            "next_character_data": [{"next_character_value": chars[code],
                                                     "next_character_desc": "Test",
                                                     "next_character_evidences": []}]})
    agent2_mock = AsyncMock(side_effect=agent2_side_effect)

    with patch("src.agents.agent1.get_provider", return_value=agent1_mock), \
         patch("src.agents.agent2.get_provider", return_value=agent2_mock):
        result = await run(str(doc))

    assert len(result["billable"]) == 1
    assert result["billable"][0]["code"] == "0DTJ4ZZ"
    assert result["non_billable"] == []
```

---

## Verification

1. **TSV lookup unit test**: `get_next_options("")` returns 17 section entries; `get_digit_type("0", 2)` returns `"Body System"`
2. **Placeholder fill test**: All `[## ##]` markers replaced correctly for a known `current_code = "4A0"`
3. **Evidence accumulation test**: Simulate 3-level traversal, confirm `accumulated_evidences` has keys for positions 1-3 at depth 3
4. **Provider swap test**: Change `LLM_PROVIDER = "azure_openai"` in `config.py`, rerun, confirm identical output structure
5. **Managed identity test**: Confirm no API key present in any file; client initializes correctly in GCP/Azure runtime
6. **End-to-end test**: Run `main.py` with a real patient `.txt` file; confirm at least one 7-char billable code in output
7. **Non-billable test**: Simulate Agent 2 returning `[]` at position 5; confirm result carries the 4-char code as `non_billable`
8. **Concurrency test**: Set `MAX_CONCURRENCY = 5` with a multi-procedure document; confirm no rate-limit errors, all procedures complete
