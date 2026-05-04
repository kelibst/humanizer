# Interface Contracts — humanizer

> **Read this before writing any code.** These are the boundaries between modules. Honour them and the two agents working in parallel will not collide.
>
> Authoritative plan: [`/home/kelib/.claude/plans/i-now-need-a-sharded-crown.md`](/home/kelib/.claude/plans/i-now-need-a-sharded-crown.md)
> Voice spec for the default profile: [`/home/kelib/Desktop/moreprojects/Sis-Caro/researchRules.md`](/home/kelib/Desktop/moreprojects/Sis-Caro/researchRules.md)

---

## 1. Shared types (already implemented — do not change)

| Symbol | Module | Notes |
|---|---|---|
| `Profile` | `sis_caro_humanizer.profile.schema` | Pydantic v2 model. All sub-fields are also pydantic. Bluppers, sentence shape, hedge mix, etc. |
| `load_profile(path) / save_profile(profile, path)` | same | YAML round-trip. |
| `resolve_profile(name_or_path)` | `profile.loader` | Looks up by XDG-config name, then path, then bundled `default_ghanaian.yaml`. |
| `extract_profile(name, paths, dialect)` | `profile.extractor` | Builds a profile from sample text. |
| `split_paragraphs / split_sentences / iter_words / word_count / sentence_lengths / coefficient_of_variation` | `text_utils` | Zero-dep tokenization. **Use these everywhere.** Do NOT introduce spaCy, nltk, or another splitter. |

---

## 2. Stage interfaces (each agent implements its own; both must match these signatures)

### Stage 1 — pre-scan (Agent A)
```python
# sis_caro_humanizer/pipeline/stage1_prescan.py
def prescan(text: str, profile: Profile | None = None) -> ScoreReport: ...
```
Just calls `ai_risk_score`. Exists as a stage so the runner can swap it.

### Stage 2 — LLM rewrite (Agent B)
```python
# sis_caro_humanizer/pipeline/stage2_llm_rewrite.py
def llm_rewrite(text: str, profile: Profile, *, model: str | None = None,
                host: str | None = None, timeout: float = 600.0) -> str: ...
```
- Calls Ollama via `sis_caro_humanizer.ollama_client.generate(...)`.
- If Ollama is unreachable: raise `OllamaUnavailable` (defined in `ollama_client`). The runner will catch and downgrade.
- Builds a system prompt that summarizes the profile (vocab swaps, never_use, forbidden_openers, em-dash and semicolon prohibitions, sentence-shape targets).
- Returns the rewritten text only (strip surrounding chatter from the model's reply).

### Stage 3 — deterministic post-edits (Agent A)
```python
# sis_caro_humanizer/pipeline/stage3_deterministic/runner.py
@dataclass
class TransformLog:
    transform: str         # e.g. "strip_em_dashes"
    site: tuple[int, int]  # (start, end) in pre-transform text
    before: str
    after: str
    reason: str            # short human-readable why

def run_deterministic(text: str, profile: Profile, *, seed: int | None = None
                      ) -> tuple[str, list[TransformLog]]: ...
```
Each individual transform module exposes:
```python
def apply(text: str, profile: Profile, rng: random.Random,
          protected: list[tuple[int, int]]) -> tuple[str, list[TransformLog]]: ...
```
The `runner` rebuilds `protected` after every transform that changes string length.

### Stage 4 — grammar pass (Agent B)
```python
# sis_caro_humanizer/grammar/runner.py  (re-exported from sis_caro_humanizer.grammar)
@dataclass
class GrammarIssue:
    tool: Literal["languagetool", "vale", "proselint"]
    rule_id: str
    message: str
    offset: int
    length: int
    suggestions: list[str]
    suppressed: bool = False
    suppression_reason: str | None = None

@dataclass
class GrammarReport:
    issues: list[GrammarIssue]
    tool_status: dict[str, Literal["ok", "missing", "skipped", "error"]]

def run_grammar(text: str, profile: Profile) -> GrammarReport: ...
```
- Each tool runs in its own module (`grammar/languagetool.py`, `grammar/vale.py`, `grammar/proselint.py`) and returns `list[GrammarIssue]`.
- Missing dependencies (no Java for LT, no `vale` binary on PATH) are NOT errors. The tool reports status `"missing"` and contributes zero issues.
- `grammar/filters.py` post-processes the merged list and sets `suppressed=True` on issues that match deliberate bluppers from the active profile (e.g. profile has `data_singular_verb > 0.5` → suppress LT rule about `data` verb agreement).

### Stage 5 — post-scan (Agent A)
Identical signature to stage 1; lives in `pipeline/stage5_postscan.py` for symmetry.

### Pipeline runner (Agent B)
```python
# sis_caro_humanizer/pipeline/runner.py
@dataclass
class PipelineResult:
    input: str
    output: str
    pre_score: ScoreReport
    post_score: ScoreReport
    llm_used: bool
    deterministic_log: list[TransformLog]
    grammar: GrammarReport | None
    elapsed_seconds: float

def run_pipeline(text: str, profile: Profile, *,
                 stages: Iterable[str] = ("prescan", "llm", "determ", "grammar", "postscan"),
                 model: str | None = None, seed: int | None = None
                 ) -> PipelineResult: ...
```
`stages` controls which stages run; tests will pass `("prescan", "determ", "postscan")` to skip Ollama.

---

## 3. Scoring contract (Agent A)

```python
# sis_caro_humanizer/scoring/risk.py
@dataclass
class FeatureContribution:
    name: str
    value: float        # 0..1, the component's normalized output
    weight: float
    detail: str         # short explanation, e.g. "12 em-dashes / 1000 words"
    examples: list[str] = field(default_factory=list)  # up to 3 short snippets

@dataclass
class ScoreReport:
    score: float        # 0..1, after sigmoid
    raw_weighted_sum: float
    components: list[FeatureContribution]
    band: Literal["low", "medium", "high"]   # <0.34, <0.67, else

def ai_risk_score(text: str, profile: Profile | None = None) -> ScoreReport: ...
```

**Six MUST-HAVE features** (weights sum to 0.85; reserve 0.15 for v2):

| name | weight | formula |
|---|---|---|
| `burstiness_deficit` | 0.18 | `clamp(1 - sentence_length_cv / 0.7, 0, 1)` |
| `punct_signature` | 0.15 | `min(1, em_per_1k * 0.5 + semi_per_1k * 0.15)` |
| `llm_vocab_density` | 0.20 | `min(1, llm_favored_hits_per_1k / 8)` (load list from `scoring/llm_favored.txt`) |
| `triple_list_rate` | 0.12 | `min(1, triples_per_100_sentences / 25)` |
| `topic_sentence_perfection` | 0.10 | fraction of paragraphs whose first sentence is 12-22 words, NP-start, no hedge token |
| `hedge_formality_skew` | 0.10 | `clamp((formal/(formal+informal+1) - 0.6) / 0.4, 0, 1)` |

Aggregation: `score = sigmoid(6 * (weighted_sum - 0.5))`. Set `band` by score thresholds.

---

## 4. Deterministic transforms (Agent A) — exact ordering

```
DETERMINISTIC_PIPELINE = [
    em_dashes.apply,
    semicolons.apply,
    triple_lists.apply,
    vocab_swap.apply,
    bluppers.apply,
    topic_softener.apply,
    ghanaian.apply,         # only triggers if profile.dialect == "ghanaian"
    anti_cluster.apply,
]
```
After every transform that changes the text, the runner calls `build_protected_spans(text)` again before passing into the next.

### Protected spans contract
```python
# sis_caro_humanizer/pipeline/stage3_deterministic/protected.py
def build_protected_spans(text: str) -> list[tuple[int, int]]:
    """Return list of (start, end) byte ranges that no transform may modify.
    Includes: paired ASCII/curly quotes, markdown code fences and inline `code`,
    citation parentheticals (Author, 2024) / (Author et al., 2024), markdown
    table rows (lines starting with |), block quotes (lines starting with >),
    LaTeX/inline math $...$, and any line under a heading "References" or
    "Bibliography" until next heading.
    Spans MUST be sorted by start, non-overlapping (merge if needed)."""
```
A helper `is_protected(pos: int, spans) -> bool` should also live in this module.

---

## 5. Coding conventions

- Python ≥ 3.10. Use `from __future__ import annotations` at the top of every module.
- Type hints on every public function. `dataclasses` for value objects (not pydantic, except where the Profile schema requires it).
- No `print()`. Stages return values; the CLI / `reporting/report.py` is the only thing that writes to stdout (via `rich.console.Console`).
- All randomness goes through a `random.Random` seeded by `hash(text) ^ profile.seed`. Never call `random.random()` at module level.
- Use `regex` library (already in deps) for anything that needs Unicode word boundaries or variable-width lookbehinds; use stdlib `re` for simple patterns.
- No new top-level dependencies without updating `pyproject.toml` AND noting in `STATE.md`.
- Tests live under `tests/` mirroring the source layout. Use plain `pytest`, no fixtures heavier than `tmp_path`.
- Every transform module has a docstring at the top explaining its specific contract.

---

## 6. CLI surface (Agent B)

Exact subcommands and flags — keep them stable since colleagues will script around them:

```
humanize doctor
humanize profile create <name> <samples...> [--dialect ghanaian|british|american|neutral]
humanize profile show <name>
humanize profile edit <name>
humanize profile list
humanize check <input> [--profile NAME] [--why] [--json]
humanize transform <input> [-p NAME] [-o OUT] [--model M]
                          [--stages all|llm|determ|grammar]
                          [--seed N] [--json]
humanize grammar <input> [--profile NAME] [--json]
humanize calibrate    # stub for v0.1 — print "not implemented" + exit 0
```

The `humanize doctor` command checks: Ollama process reachable (`http://localhost:11434/api/tags`), required model present (`profile.model` or default), Java on PATH, `vale` binary on PATH, `proselint` importable. Prints a tick/cross table.
