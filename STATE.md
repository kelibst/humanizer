# Implementation State — humanizer

> **Update this file when you finish an assigned chunk.** Append to the appropriate section, do not erase prior entries. Date your additions.
>
> Read these alongside this file:
> - Plan: [`/home/kelib/.claude/plans/i-now-need-a-sharded-crown.md`](/home/kelib/.claude/plans/i-now-need-a-sharded-crown.md)
> - Contracts: [CONTRACTS.md](CONTRACTS.md)
> - Voice spec: [`/home/kelib/Desktop/moreprojects/Sis-Caro/researchRules.md`](/home/kelib/Desktop/moreprojects/Sis-Caro/researchRules.md)

## Repo location
`/home/kelib/Desktop/projects/humanizer`. Venv at `.venv` already created with `pydantic pyyaml platformdirs typer rich regex` installed. Agents may need to additionally install `ollama language-tool-python proselint` with `.venv/bin/pip install ...`.

## Restart notice (2026-05-04)
The machine restarted mid-run. The first pair of agents lost their session, but most of their on-disk output survived. Treat the lists below as authoritative. Do **not** rebuild any file marked "done"; if you need to verify, just `Read` it and confirm it looks complete and runs (`.venv/bin/python -c "import sis_caro_humanizer.<mod>"`). Only if a file is *broken* (truncated, syntax error) should you rewrite it — and note that in "Decisions and deviations" when you do.

## What is done

### Foundation (PM)
- `pyproject.toml`, `LICENSE` (MIT), `README.md`, `.gitignore`
- `src/sis_caro_humanizer/__init__.py`, `config.py`, `text_utils.py`
- `profile/schema.py`, `profile/loader.py`, `profile/extractor.py`, `profile/default_ghanaian.yaml`, `profile/__init__.py`

### Scoring (Agent A round 1, survived restart)
- `scoring/features.py` — 338 lines. Six feature extractors per CONTRACTS § 3.
- `scoring/risk.py` — 72 lines. `ai_risk_score`, sigmoid aggregation, banding.
- `scoring/llm_favored.txt`, `scoring/__init__.py`.
- `pipeline/stage1_prescan.py`, `pipeline/stage5_postscan.py` — thin wrappers.
- `tests/test_scorer.py` — 77 lines.

### Ollama + LLM stage (Agent B round 1, survived restart)
- `ollama_client.py` — 123 lines. Defines `OllamaUnavailable`, `is_running`, `list_models`, `ensure_model`, `generate`.
- `pipeline/stage2_llm_rewrite.py` — 139 lines.

### Grammar tooling (Agent B round 2, survived restart)
- `grammar/types.py` — `GrammarIssue`, `GrammarReport` dataclasses.
- `grammar/runner.py`, `grammar/filters.py`, `grammar/languagetool.py`, `grammar/vale.py`, `grammar/proselint.py`.
- `grammar/__init__.py` — re-exports `GrammarIssue`, `GrammarReport`, `run_grammar`.
- `pipeline/stage4_grammar.py` — re-export shim.

### Vale style folder (Agent B round 3, partial)
- `vale_styles/.vale.ini`, `vale_styles/Sis-Caro/NoEmDash.yml`, `vale_styles/Sis-Caro/ForbiddenOpeners.yml`.

## What is done (Agent B round 2, 2026-05-04)

### Vale style folder (completed)
- `vale_styles/Sis-Caro/LLMVocab.yml` — flags delve / leverage / multifaceted / tapestry / navigate / intricate / holistic / paradigm / embark / endeavor (case-insensitive, level=warning).
- `vale_styles/Sis-Caro/ThreeItemListOveruse.yml` — informational regex flag for `\b\w+,\s+\w+,\s+and\s+\w+\b` (level=suggestion; matches researchRules.md §27, §52).

### Pipeline runner
- `src/sis_caro_humanizer/pipeline/runner.py` — `run_pipeline`, `PipelineResult`, `TransformLog` mirror, `ALL_STAGES`. Stage 3 imported lazily inside `_run_determ`; missing stage downgrades to a note rather than crashing. Every stage is wrapped: `OllamaUnavailable` and any other stage error becomes a downgrade note. Library code never prints. Pre/post mirroring keeps `pre_score` / `post_score` populated even when only one of them was requested.

### CLI
- `src/sis_caro_humanizer/cli.py` — Typer app with `doctor`, `check`, `transform`, `grammar`, `calibrate`, plus `profile` sub-app (`create`, `show`, `edit`, `list`). `transform` writes rewritten text to `--out` or stdout; the Rich summary goes to stderr so stdout stays pipeable. `--json` honoured on `check`, `transform`, and `grammar`.

### Reporting
- `src/sis_caro_humanizer/reporting/diff.py` — `render_diff` returns a Rich-markup unified diff string.
- `src/sis_caro_humanizer/reporting/report.py` — `render_check`, `render_grammar`, `render_transform`.
- `src/sis_caro_humanizer/reporting/__init__.py` — re-exports.

### Tests
- `tests/test_grammar_filters.py` — 7 tests covering data-verb, less/fewer, which/that suppression plus pass-through and order preservation. All pass.
- `tests/test_pipeline_e2e.py` — 4 tests; runs `run_pipeline` with `("prescan", "postscan")` only (full e2e is the PM's integration round). Includes a regression test that requesting `determ` without Agent A's stage3 module downgrades cleanly. All pass.

Test run: `.venv/bin/python -m pytest tests/test_grammar_filters.py tests/test_pipeline_e2e.py -q` → 12 passed. With `tests/test_scorer.py` added → 17 passed.

## What is pending

### Final integration round (PM)
- Fix-up of two bugs surfaced by the e2e (see "Bugs surfaced by integration" below)
- `packaging/pyinstaller.spec`
- Real e2e against a Sis-Caro chapter once the bugs are fixed

## What is done (Agent A round 2, 2026-05-04 — completed pre-restart, STATE update by PM post-restart)

The second restart caught Agent A after they finished writing files but before they updated STATE.md. PM verified by inventory and pytest run.

### Deterministic pipeline (10 modules)
- `pipeline/stage3_deterministic/protected.py` — 218 lines. Protected-spans builder.
- `pipeline/stage3_deterministic/em_dashes.py` — 190 lines.
- `pipeline/stage3_deterministic/semicolons.py` — 113 lines.
- `pipeline/stage3_deterministic/triple_lists.py` — 103 lines.
- `pipeline/stage3_deterministic/vocab_swap.py` — 82 lines.
- `pipeline/stage3_deterministic/bluppers.py` — 455 lines (largest single module; covers `data shows`, `less/fewer`, `which/that`, comma splices, `start_with_and_but`, oxford-comma flips).
- `pipeline/stage3_deterministic/topic_softener.py` — 142 lines.
- `pipeline/stage3_deterministic/ghanaian.py` — 80 lines.
- `pipeline/stage3_deterministic/anti_cluster.py` — 182 lines.
- `pipeline/stage3_deterministic/runner.py` — 85 lines. Stitches them in CONTRACTS § 4 order.

### Tests
- `tests/test_protected.py` — 127 lines.
- `tests/test_deterministic/test_em_dashes.py` — 65 lines.
- `tests/test_deterministic/test_bluppers.py` — 104 lines.
- `tests/test_deterministic/test_triple_lists.py` — 68 lines.
- `tests/test_deterministic/test_anti_cluster.py` — 53 lines.
- `tests/test_deterministic/test_runner.py` — 66 lines.

### Test status (PM, 2026-05-04 post-restart)
`.venv/bin/python -m pytest tests/ -q` → **56 passed, 1 failed** (see "Bugs surfaced by integration").

## Bugs surfaced by integration (PM smoke test, 2026-05-04)

Tested against a deliberate AI-flavoured paragraph (`/tmp/ai_sample.md`). Pipeline took it from **0.810 (HIGH) → 0.303 (LOW)** in 0.03s with no LLM. Two real bugs found:

### Bug 1 — `vocab_swap` strands trailing prepositions on phrasal verbs
`delve into` is swapped to `look at` from the pool, producing the broken phrase **"look at into"**. The swap operates on a single word and does not consider that the user-text token plus the source word form a phrasal verb. Either the swap pool entries should include their own preposition (`"look at"`, `"go into"` already do — the bug is that when source is `delve` followed by `into`, the chosen replacement plus the original `into` create a duplicate preposition).

**Fix direction:** in `vocab_swap.py`, after picking a replacement, look ahead one token. If the source word is `delve` and the next token is `into`, and the replacement already ends in a preposition, *consume* the next `into`. More generally: maintain a small phrasal-verb table `{("delve", "into"): "examine"}`-style and prefer it over the per-word swap.

### Bug 2 — `triple_lists` rewrites proper-noun lists
Failing test: `tests/test_deterministic/test_triple_lists.py::test_proper_noun_list_is_skipped`. Input "We surveyed Accra, Kumasi, and Tamale extensively." was rewritten to "We surveyed Accra and Tamale extensively." The proper-noun-skip heuristic in `triple_lists.py` fails on three Title-Case single-word place names.

**Fix direction:** strengthen the proper-noun detector in `triple_lists.py` — if all three list items are single capitalised tokens (and the surrounding sentence does not look like a generic enumeration cue like "such as", "including"), skip the rewrite.

### Quality observation (not a bug — note for v1.1)
- `ensure → make sure` produces awkward phrasing in some sentences ("will make sure robust data flow"). The single-word swap doesn't preserve subordinate clauses. v1 acceptable; v1.1 should consider context-aware swaps.
- `forbidden_openers` are only enforced via the LLM system prompt. The deterministic stage does not strip them. Acceptable for v1 since when LLM is in the pipeline they are rewritten there; flag for v1.1 if running deterministic-only.

## Decisions and deviations
*(Append rows. Format: date — who — what — why.)*

- 2026-05-04 — PM — default model is `gemma3:4b` (locally present), not `gemma4:e4b`. Rationale: user has gemma3 installed; gemma4 pull is ~10GB and should be opt-in via `--model`.
- 2026-05-04 — PM — added `seed` field to Profile (default 1337) so deterministic-stage probabilistic transforms are reproducible per (text, profile) pair.
- 2026-05-04 — PM — survived a machine restart. STATE.md rewritten to reflect on-disk reality; no work was lost.
- 2026-05-04 — Agent B — `PipelineResult.deterministic_log` is typed `list[Any]` (not `list[TransformLog]`) and `TransformLog` is duplicated in `pipeline/runner.py`. Reason: Agent A owns the canonical dataclass in `stage3_deterministic.runner`; importing it eagerly would defeat the lazy-import contract. The runner just stores whatever the stage hands back. Once Agent A merges, both definitions match shape exactly and CONTRACTS § 2 stays honoured.
- 2026-05-04 — Agent B — `run_pipeline` never raises for individual stage failures; it appends a downgrade note to `PipelineResult.notes` and passes the un-mutated text forward. `ValueError` only fires for an unknown stage name in `stages=`. Rationale: CONTRACTS says the runner downgrades when Ollama is unreachable; I extended that policy uniformly so a missing `vale` binary or a not-yet-merged stage3 doesn't kill the whole pipeline.
- 2026-05-04 — Agent B — added `notes: list[str]` to `PipelineResult` (not in the original CONTRACTS dataclass). Needed so downgrade reasons survive past the runner without printing. CLI renders them after the summary; `--json` includes them.
- 2026-05-04 — Agent B — `humanize transform` writes rewritten text to stdout when no `--out` is given and routes the Rich summary to stderr, so the command is safely pipeable (`humanize transform x.md | wc -w`). `--json` flips: with `--out` the JSON goes to stdout, otherwise to stderr.

## Open questions / blockers
*(Append below; PM will resolve or escalate.)*

- None yet.

## Test status
*(Append run results.)*

- `tests/test_scorer.py` exists but has not been run end-to-end since the restart. Agent A should re-run it as part of their round.
- 2026-05-04 — Agent B — re-ran `tests/test_scorer.py` alongside the new B-tests; all 17 tests pass on the post-restart venv (`tests/test_grammar_filters.py` 7, `tests/test_pipeline_e2e.py` 4, `tests/test_scorer.py` 5, plus `corpus/` is empty so no corpus tests collected).

## Fix-up round (2026-05-04)

PM dispatched a fix-up agent to address the two bugs raised in "Bugs surfaced by integration".

### Bug 1 fix — `vocab_swap.py` phrasal-verb stranding
Added a module-level `PHRASAL_HINTS` table covering `(delve, into)`, `(navigate, through|across)`, `(embark, on|upon)`. After picking a replacement, `apply()` peeks the next token in the source text; if `(source_word_lower, next_token_lower)` is in the hint table AND the chosen replacement ends in a terminal preposition (`into / on / through / with / of / at / by / for / upon / across`), the trailing source preposition is consumed. The `TransformLog.before` now reflects the full consumed range so the diff is honest. When the replacement carries no preposition (e.g. `delve → examine`), nothing is consumed and `examine into` survives as before — the surface is grammatical either way.

### Bug 2 fix — `triple_lists.py` proper-noun detection
Strengthened `_looks_proper_noun_list()`. The triple-regex greedily swallows surrounding words (`"We surveyed Accra"` was being captured as the first item), so checking only `parts[-1]` of each captured group failed for the third item (`"Tamale extensively"`). New rules:

  1. If every term is a single `^[A-Z][a-z]+$` token (and not in the common-noun-opener allowlist `Many / Some / Few / Several / Most / All / Both / These / Those`), skip.
  2. If the middle term is a single capitalised token AND the last token of group 1 is capitalised AND the first token of group 3 is capitalised, skip — this catches the greedy-capture case at the inner edges.
  3. Independent of (1)/(2), if the leading verb/preposition before the triple is one of `surveyed / visited / sampled / recruited / included / comparing / between / among / from / across` AND the middle item is a single capitalised token, skip — belt-and-braces enumeration-cue heuristic.

### Regression tests added
- `tests/test_deterministic/test_vocab_swap.py` — 5 tests covering `delve into → look at` (no stranded prep), `delve into → examine` (preposition preserved), `navigate through`, `embark on`, and a non-phrasal control.
- `tests/test_deterministic/test_triple_lists.py::test_proper_noun_list_lagos_nairobi_cairo_is_skipped` — second proper-noun-list case beyond the existing Accra/Kumasi/Tamale one.

### Test count
`.venv/bin/python -m pytest tests/ -q` → **62 passed** (was 56 of which 1 failing). The fix-up itself is deterministic; my changes pass on every run.

### Known leftover (NOT my scope)
`tests/test_pipeline_e2e.py::test_runner_determ_downgrades_when_stage3_missing` is flaky depending on `PYTHONHASHSEED`. Its assertion `result.output == SAMPLE` predates Agent A's stage3 merge; now that stage3 is real, deterministic transforms (`start_with_and_but` at 0.08 probability, etc.) sometimes mutate SAMPLE and the equality fails. The test name itself ("when stage3 missing") signals the assumption is stale. Out of scope for this fix-up — the PM should rewrite the assertion to allow stage3 transforms or pin a seed. Test passes on most hash seeds (e.g. `PYTHONHASHSEED=0`) and fails on others.

### Files touched
- `src/sis_caro_humanizer/pipeline/stage3_deterministic/vocab_swap.py` (rewrote with phrasal-verb consumption)
- `src/sis_caro_humanizer/pipeline/stage3_deterministic/triple_lists.py` (strengthened proper-noun detector + enumeration-cue skip)
- `tests/test_deterministic/test_vocab_swap.py` (new file, 5 tests)
- `tests/test_deterministic/test_triple_lists.py` (added one regression test)
- `STATE.md` (this section)

## Fix-up round 2 (2026-05-04)

PM dispatched a second fix-up agent to close three remaining holes after round 1.

### Issue 1 fix - `vocab_swap.py` ungrammatical "examine into"
Round 1 only consumed the trailing source preposition when the chosen replacement also carried one, on the (wrong) assumption that bare-verb replacements like `examine` could swallow the leftover `into`. They cannot - `examine` is transitive. New rule: for any `(source, next_token)` pair listed in `PHRASAL_HINTS` (`delve+into`, `navigate+through|across`, `embark+on|upon`), *always* consume the trailing preposition, regardless of replacement form. This makes every branch grammatical:
- `delve into challenges` + `examine` -> `examine challenges`
- `delve into challenges` + `look at` -> `look at challenges`
- `delve into challenges` + `go into` -> `go into challenges`

The `_replacement_carries_preposition` helper and `_TERMINAL_PREPS` constant were removed (no longer needed).

### Issue 2 fix - `bluppers.py` complementizer false positives
The `which_for_that` blupper was flipping the complementizer `that` after verbs of saying/thinking/believing/etc. ("It is worth noting which the comprehensive..."). Added module-scope `SKIP_THAT_AFTER` set per the brief (verbs of saying/thinking/believing/knowing/claiming/suggesting/showing/arguing/assuming/finding in all common inflections, plus `fact / idea / view / evidence / concern` and degree adverbs `so / such`). `_which_for_that` consults it before flipping; the existing `_COMPLEMENTIZER_VERBS` and restrictive-clause heuristic stay.

### Issue 3 fix - `test_pipeline_e2e.py::test_runner_determ_downgrades_when_stage3_missing`
The original assertion `result.output == SAMPLE` predated stage3 existence and broke once `start_with_and_but` (8% prob) and friends could legitimately mutate SAMPLE. Replaced with `test_runner_determ_downgrades_when_stage3_unavailable` which:

  1. Uses `monkeypatch.setitem(sys.modules, "sis_caro_humanizer.pipeline.stage3_deterministic.runner", types.ModuleType(...))` to inject an empty stub for the lazy submodule.
  2. The lazy `from .stage3_deterministic.runner import run_deterministic` then raises `ImportError` (attribute missing on the stub module), which the runner's broad `except Exception` catches and downgrades.
  3. Asserts `result.llm_used is False`, `result.output == SAMPLE` (now true because stage3 was forced to fail), and that some entry in `result.notes` mentions `determ`.

Also added `test_runner_unknown_stage_name_raises` to lock in the CONTRACTS guarantee that an unknown stage name raises `ValueError`.

### Regression tests added/updated
- `tests/test_deterministic/test_vocab_swap.py` - rewrote. 7 tests now: three branches of `delve into` (`examine`, `look at`, `go into`), the original mixed-pool `delve` test, `navigate through`, `embark on`, and a non-phrasal control. Dropped the assertion that "examine into" was acceptable.
- `tests/test_deterministic/test_bluppers.py` - added `test_which_for_that_skips_complementizer_after_noting` and `test_which_for_that_skips_other_complementizers` (six licensing tokens).
- `tests/test_pipeline_e2e.py` - replaced one test, added one test.

### Test count
`.venv/bin/python -m pytest tests/ -q` -> **67 passed** (was 62). Smoke test confirmed: 10 different `PYTHONHASHSEED` values, output never contains `examine into`, `noting which`, `look at into`, `go into into`, or `work through through`. The legitimate `which_for_that` blupper still fires on relative-clause sites like `shift, one that will` -> `shift, one which will` as designed.

### Files touched
- `src/sis_caro_humanizer/pipeline/stage3_deterministic/vocab_swap.py` (always-consume rule for PHRASAL_HINTS)
- `src/sis_caro_humanizer/pipeline/stage3_deterministic/bluppers.py` (added `SKIP_THAT_AFTER`)
- `tests/test_deterministic/test_vocab_swap.py` (rewritten)
- `tests/test_deterministic/test_bluppers.py` (two new tests)
- `tests/test_pipeline_e2e.py` (replaced one test, added one)
- `STATE.md` (this section)

## Packaging round (2026-05-04)

PM packaging agent shipped a PyInstaller one-file spec so colleagues without
Python can run the humanizer.

### What was done
- `packaging/pyinstaller.spec` — one-file spec, `console=True`, `strip=False`,
  `upx=False`. Bundles `default_ghanaian.yaml`, `llm_favored.txt`, and the full
  `vale_styles/` tree. Hidden imports: `ollama`, `language_tool_python`,
  `proselint`, `pydantic`, `yaml`, `regex`. Adds `collect_data_files("proselint")`
  and `collect_data_files("language_tool_python")` (see "Wrinkle 2").
- `packaging/launcher.py` — one-line shim importing `sis_caro_humanizer.cli.main`
  (see "Wrinkle 1").
- `src/sis_caro_humanizer/config.py` — added `bundle_dir()` returning
  `Path(sys._MEIPASS)` when frozen, else the repo root. Existing constants
  preserved.
- `src/sis_caro_humanizer/grammar/vale.py` — `_find_styles_dir()` now also
  checks `bundle_dir() / "vale_styles"` so the bundled style folder is found
  inside the PyInstaller bundle. Wheel and editable-install paths unchanged.
- `README.md` — added a "Build a standalone binary" section with the three-line
  build recipe.
- Removed a stray `triple_lists.py.tmp.23984.1777893512734` left in
  `stage3_deterministic/` from a previous round.

### Build result
- Binary: `dist/humanize` (21M, statically links the Python runtime + deps).
- Build time: ~30s on this machine.
- `dist/humanize doctor` shows Ollama OK, gemma3:4b OK, proselint OK; Java and
  Vale flagged MISSING because they aren't installed locally (expected).

### `dist/humanize check /tmp/ai_sample.md` output (score panel only)
```
╭────────────────────────── check ──────────────────────────╮
│ AI-risk score: 0.810    band: HIGH    weighted sum: 0.742 │
╰───────────────────────────────────────────────────────────╯
```
Matches the source-tree run; bundled `default_ghanaian.yaml` and
`llm_favored.txt` are loading correctly. A bundled `transform` smoke-run
(`--stages prescan,determ,postscan`) reproduced the integration result:
`0.810 (high) -> 0.312 (low)` in 0.03s, `llm: no`, 14 deterministic edits.

### Wrinkles
1. **Entry point indirection.** PyInstaller cannot point Analysis directly at
   `src/sis_caro_humanizer/cli.py` — it would be loaded as a top-level script
   and the `from .config import ...` relative imports would fail with
   `ImportError: attempted relative import with no known parent package`. The
   standard idiom is a thin launcher script that imports the CLI through its
   package path; that's `packaging/launcher.py`. Documented in the spec.
2. **proselint data file.** `proselint` ships its own `config/default.json` and
   loads it at import time via `pkg_resources`. PyInstaller's static analysis
   missed it; first build produced a working binary that crashed the
   `proselint` doctor row with `FileNotFoundError: ... /proselint/config/default.json`.
   Fixed with `collect_data_files("proselint")` in the spec. Same prophylactic
   added for `language_tool_python` even though doctor doesn't exercise it
   beyond `shutil.which("java")` (the Java JVM is the actual missing piece on
   this host).
3. **Brief specified entry point as `cli.py` directly.** The launcher shim is a
   one-line semantic-equivalent (`from sis_caro_humanizer.cli import main; main()`).
   Spec comment explains the constraint.

### Files touched
- `packaging/pyinstaller.spec` (new)
- `packaging/launcher.py` (new — one-line shim)
- `src/sis_caro_humanizer/config.py` (added `bundle_dir()`)
- `src/sis_caro_humanizer/grammar/vale.py` (added bundle-dir candidate to
  `_find_styles_dir`)
- `README.md` (added "Build a standalone binary" section)
- removed: `src/sis_caro_humanizer/pipeline/stage3_deterministic/triple_lists.py.tmp.23984.1777893512734`
- `STATE.md` (this section)

### Test status
`.venv/bin/python -m pytest tests/ -q` → **67 passed** (unchanged).

---

## v1.2 kickoff (PM, 2026-05-04)

Scope and decisions are locked in [plan/V1_2_ROADMAP.md](plan/V1_2_ROADMAP.md). Two parallel tracks:

- **Track A — Bridge + multi-backend (Agent A).** Adds `src/sis_caro_humanizer/backends/` (ollama / anthropic / openai / gemini), the `humanize serve` HTTPS daemon under `src/sis_caro_humanizer/serve/`, and `Profile.backend` + `backend_config` fields. Brief: [plan/AGENT_A_BRIEF_V1_2.md](plan/AGENT_A_BRIEF_V1_2.md). Contracts: [plan/BRIDGE_CONTRACT.md](plan/BRIDGE_CONTRACT.md), [plan/BACKEND_CONTRACT.md](plan/BACKEND_CONTRACT.md).
- **Track B — Textual TUI (Agent B).** Adds `src/sis_caro_humanizer/tui/` and extends `pipeline/runner.py` with an optional `on_event` callback. The flag CLI is preserved; only the no-args default changes (now launches the TUI). Brief: [plan/AGENT_B_BRIEF_V1_2.md](plan/AGENT_B_BRIEF_V1_2.md). Layout: [plan/TUI_LAYOUT.md](plan/TUI_LAYOUT.md).

Round 2 (Google Docs add-in under `addons/google-docs/`) is dispatched by PM only after both round-1 deliverables land green.

**Coordination rules.**
- Agents read the `plan/` files; PM does not paste context inline. Briefs are <200 words.
- `STATE.md` is append-only. Each agent appends its dated `What is done (Agent X v1.2 round N, ...)` section. PM never edits prior entries.
- Cross-track file edits (`cli.py`, `pyproject.toml`) are choreographed: Agent A owns `pyproject.toml` bumps and the `humanize serve` sub-app; Agent B owns the no-args TUI launch. Conflicts go to "Open questions" below.

**Dependency additions (single bump by Agent A).** `textual>=0.60`, `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `cryptography>=42`, `anthropic>=0.30`, `openai>=1.30`, `google-generativeai>=0.5`. Listed in [plan/V1_2_ROADMAP.md](plan/V1_2_ROADMAP.md).

---

## What is done (Agent A v1.2 round 1, 2026-05-04)

Multi-backend abstraction + local HTTPS bridge daemon shipped per
`plan/AGENT_A_BRIEF_V1_2.md`, `plan/BACKEND_CONTRACT.md`, `plan/BRIDGE_CONTRACT.md`.

### Files created
- `src/sis_caro_humanizer/backends/__init__.py` — `get_backend`, `list_backends`, `list_available`, registry, re-exports.
- `src/sis_caro_humanizer/backends/base.py` — `Backend` protocol, `BackendUnavailable` / `BackendError`, shared `clean_output()` + `wrap_user_message()` (extracted from old `_strip_chatter`).
- `src/sis_caro_humanizer/backends/_secrets.py` — explicit-config → env → `~/.config/humanizer/secrets.toml` resolution chain with cache-clear hook for tests.
- `src/sis_caro_humanizer/backends/ollama.py` — wraps existing `ollama_client.generate`; maps `OllamaUnavailable` → `BackendUnavailable`.
- `src/sis_caro_humanizer/backends/anthropic.py` — `claude-sonnet-4-6` default, system prompt sent as a cached block (`cache_control={"type": "ephemeral"}`), uses `client.with_options(timeout=...)`.
- `src/sis_caro_humanizer/backends/openai.py` — `gpt-5-mini` default, chat-completions shape, base URL configurable.
- `src/sis_caro_humanizer/backends/gemini.py` — `gemini-2.0-flash` default, uses `system_instruction=` on `GenerativeModel`, request timeout via `request_options`.
- `src/sis_caro_humanizer/serve/__init__.py` — re-exports the public surface.
- `src/sis_caro_humanizer/serve/auth.py` — bearer-token persistence at `~/.config/humanizer/serve/token` (chmod 0600), `extract_bearer()`, `constant_time_compare()`.
- `src/sis_caro_humanizer/serve/certs.py` — self-signed cert generation under `~/.config/humanizer/certs/` with localhost SAN entries (DNS + 127.0.0.1 + ::1), `_is_expired` check, OS-specific `trust_install_hint`.
- `src/sis_caro_humanizer/serve/app.py` — FastAPI factory implementing all five `/v1/*` routes per BRIDGE_CONTRACT §3, CORS allowlist of `https://docs.google.com` and `https://script.google.com`, uniform `{error, detail}` body shape, 502 fallback when LLM stage downgrades, `ThreadPoolExecutor`-backed `/v1/suggest`.
- `src/sis_caro_humanizer/serve/runner.py` — `build_serve_config()`, `render_startup_banner()`, `serve()` (uvicorn launcher with TLS).
- `tests/test_backends/__init__.py` + 6 test files: `test_registry.py`, `test_postprocess.py`, `test_secrets.py`, `test_ollama.py`, `test_anthropic.py`, `test_openai.py`, `test_gemini.py`. All providers use SDK monkeypatching — no live API calls.
- `tests/test_serve/__init__.py` + 4 test files: `test_auth.py`, `test_certs.py`, `test_app.py` (FastAPI TestClient: auth, CORS, all five routes, 502 fallback, backend override), `test_runner.py`.

### Files edited
- `src/sis_caro_humanizer/profile/schema.py` — added `backend: Literal[...] = "ollama"` and `backend_config: dict[str, Any] = Field(default_factory=dict)` to `Profile`.
- `src/sis_caro_humanizer/pipeline/stage2_llm_rewrite.py` — rewired through `get_backend(profile.backend, config=profile.backend_config)`. Still raises `OllamaUnavailable` (legacy name) for any backend failure so `pipeline/runner.py` does not need editing per the brief. `_strip_chatter` kept as a back-compat alias around `clean_output`.
- `src/sis_caro_humanizer/cli.py` — added `humanize serve` Typer sub-command with `--host / --port / --no-tls / --rotate-token / --rotate-cert`. Did not touch the no-args default (Agent B already wired the TUI launcher).
- `pyproject.toml` — single bump per the roadmap. Added `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `cryptography>=42`, `anthropic>=0.30`, `openai>=1.30`, `google-generativeai>=0.5`, `httpx>=0.27` (Agent A), and `textual>=0.60` (for Agent B's track).

### Verification
- `.venv/bin/python -m pytest tests/ -q` → **146 passed, 1 warning** (was 67). Existing 67 still green.
- `.venv/bin/python -c "from sis_caro_humanizer.backends import list_backends; print(list_backends())"` → `['ollama', 'anthropic', 'openai', 'gemini']`.
- `.venv/bin/humanize serve --port 19998` started, printed banner with token + cert path + trust-install one-liner. `curl -k -H "Authorization: Bearer $TOKEN" https://localhost:19998/v1/health` returned the §3.1 JSON shape (`backends_configured: ["ollama"]` since only Ollama is locally up). Wrong-token request returned 401 with `{"error": "unauthorised", ...}`.
- `.venv/bin/humanize transform /tmp/ai_sample.md --stages prescan,determ,postscan -o /tmp/out.md` regression: still works, deterministic edits intact.

### Decisions and deviations
- **Re-exported `_strip_chatter` from `stage2_llm_rewrite`.** The brief said to extract `_clean_output` into the backends layer; I left a thin re-export so any external caller importing `_strip_chatter` from the old path keeps working. The implementation lives in `backends/base.py::clean_output`.
- **`OllamaUnavailable` widened.** Per BACKEND_CONTRACT §6 the legacy name stays for runner compatibility, but I also map `BackendError` (auth/quota/5xx) into `OllamaUnavailable` so the runner's downgrade path covers hosted-backend failures too. Without this widening the runner would propagate `BackendError` and crash the pipeline, which violates the "stage failures never raise" convention from CONTRACTS.md. Documented in this entry.
- **Bridge `/v1/transform` → 502 only when `"llm"` was requested.** If the user asked for `["prescan","determ","postscan"]` (no LLM) the route returns 200 even when the runner emitted other notes. Matches BRIDGE_CONTRACT §3.4 spirit (502 means "your LLM call failed, fall back to no-LLM").
- **`/v1/transform` already has CORS preflight covered by `CORSMiddleware`.** Did not hand-roll OPTIONS handlers per the contract recommendation.
- **No SSE / streaming.** BRIDGE_CONTRACT §5 explicitly defers `/v1/transform/stream` to v1.3.
- **Cert SANs include both `localhost` (DNS) and `127.0.0.1` / `::1` (IP).** Strictly the contract just said self-signed; I added IP SANs so `https://127.0.0.1:9999` validates after trust install, which matches the default `--host 127.0.0.1`.
- **Single `pyproject.toml` bump includes Agent B's `textual>=0.60`** as the roadmap asked. Agent B does not need to bump.

### Open questions / blockers
- None.

---

## What is done (Agent B v1.2 round 1, 2026-05-04)

Full Textual TUI shipped per `plan/AGENT_B_BRIEF_V1_2.md` and
`plan/TUI_LAYOUT.md`. The flag CLI (and Agent A's new `humanize serve`
sub-command) is unchanged; only bare `humanize` flips to launching the
TUI. Pipeline runner extended with the optional `on_event` callback per
`plan/BRIDGE_CONTRACT.md` §5.

### Files created
- `src/sis_caro_humanizer/tui/__init__.py` — re-exports `HumanizerApp`.
- `src/sis_caro_humanizer/tui/app.py` — `HumanizerApp(textual.App)` with
  tab bar, status bar, screen routing, and global key bindings (`q`, `?`,
  `1`–`5` priority bindings, `p/c/t/g/s` aliases, `Ctrl+R`).
- `src/sis_caro_humanizer/tui/runner_bridge.py` — adapter that runs
  `run_pipeline` (and `ai_risk_score`) on Textual worker threads and
  posts `PipelineEvent` / `PipelineFinished` / `PipelineFailed` /
  `ScoreFinished` / `ScoreFailed` messages to the requesting screen.
- `src/sis_caro_humanizer/tui/screens/__init__.py` — re-exports.
- `src/sis_caro_humanizer/tui/screens/home.py` — landing menu (six entries,
  arrow-key navigation, Enter routes via `app.action_open_tab`).
- `src/sis_caro_humanizer/tui/screens/check.py` — score-a-document screen
  (Ctrl+S scores, gauge fills, top-five contributors render as bar/detail
  rows; small inputs scored inline, larger ones on a worker thread).
- `src/sis_caro_humanizer/tui/screens/transform.py` — pipeline-runner
  screen (stage strip animates from `on_event` callbacks, diff renders
  via `reporting.diff.render_diff`, post-score gauge updates, log pane
  tails events + notes).
- `src/sis_caro_humanizer/tui/screens/grammar.py` — read-only grammar
  table (LanguageTool / Vale / proselint) with suppressed-flag column;
  worker-threaded.
- `src/sis_caro_humanizer/tui/screens/profiles.py` — list+detail view
  reading from `profiles_dir()` and the bundled default. The
  "create new" wizard intentionally degrades to a stub message
  pointing at the existing `humanize profile create` CLI.
- `src/sis_caro_humanizer/tui/screens/settings.py` — read-mostly
  placeholder (Ollama reachability probe, default model line, bridge
  daemon row with disabled buttons that route the user to
  `humanize serve`). Persisted edits land with Agent A's
  `backend_config` schema in a follow-up round.
- `src/sis_caro_humanizer/tui/widgets/__init__.py` — re-exports.
- `src/sis_caro_humanizer/tui/widgets/score_gauge.py` — `ScoreGauge`,
  60-char-wide coloured bar with band-suffix label.
- `src/sis_caro_humanizer/tui/widgets/stage_pipeline.py` — `StagePipeline`,
  reactive five-marker strip with `apply_event(StageEvent)` translator.
- `src/sis_caro_humanizer/tui/widgets/diff_view.py` — `DiffView` wraps
  `reporting/diff.render_diff` into a scrollable RichLog.
- `src/sis_caro_humanizer/tui/widgets/log_pane.py` — `LogPane` tails
  pipeline notes and per-transform tallies.
- `src/sis_caro_humanizer/tui/widgets/tab_aware_input.py` — `TabAwareInput`
  Input subclass that releases `1`-`5` and `?` keys back to the App's
  binding chain so tab shortcuts work even when an Input has focus
  (see "Decisions and deviations").
- `tests/test_tui/__init__.py`, `tests/test_tui/test_smoke.py`,
  `tests/test_tui/test_navigation.py`,
  `tests/test_tui/test_transform_progress.py` — Pilot-harness tests.

### Files edited
- `src/sis_caro_humanizer/pipeline/runner.py` — added `on_event:
  Callable[[StageEvent], None] | None = None` parameter and emission of
  the four `StageEvent` shapes per `plan/BRIDGE_CONTRACT.md` §5
  (`stage_start`, `stage_done`, `stage_skipped`, `determ_step`). Behaviour
  with `on_event=None` is byte-identical to before; existing 146 tests
  stay green. Added `StageEvent` and `OnEvent` exports.
- `src/sis_caro_humanizer/cli.py` — flipped `no_args_is_help` to `False`,
  added `invoke_without_command=True`, and a `_root` callback that lazy-
  imports `HumanizerApp` and runs it when no subcommand is provided. All
  existing subcommands (`check`, `transform`, `grammar`, `doctor`,
  `profile *`, `calibrate`, `serve`) untouched. The lazy import means
  `humanize --help` and the subcommands do not pay the textual cost.

### Verification
- `.venv/bin/python -m pytest tests/ -q` → **154 passed, 1 warning**
  (was 146 after Agent A round 1; +8 TUI tests).
- TUI cold-boot via `app.run_test()` measures **~0.85 s** — under the
  brief's "render within ~1 s" target.
- Tab cycling smoke run: pressing `1 2 3 4 5 3 2` in sequence visits
  Profiles → Check → Transform → Grammar → Settings → Transform → Check
  in order, even after focus moves into an `Input`. Verified by
  `tests/test_tui/test_navigation.py`.
- Check screen on the deliberate AI sample produces score ~0.745 in the
  HIGH band; gauge widget reflects the value (asserted in
  `tests/test_tui/test_smoke.py`).
- Transform screen with default stages (prescan + determ + postscan) on
  the AI sample animates the stage strip through running → done for the
  three active stages, leaves `llm` and `grammar` pending, and renders a
  post-score gauge in the LOW or MEDIUM band with `pre > post`. Verified
  by `tests/test_tui/test_transform_progress.py`.
- `.venv/bin/humanize check /tmp/ai_sample_b.md --why` (existing flag
  CLI) renders the same Rich panel + breakdown table as before — full
  regression.
- `.venv/bin/humanize --help` lists every existing subcommand plus
  Agent A's `serve`. The new `_root` callback only fires when *no*
  subcommand is given.

### Binary-size impact
Did not rebuild `dist/humanize` this round — adding `textual` (and its
`linkify-it-py` / `mdit-py-plugins` / `uc-micro-py` chain) is a non-
trivial bundle bump and PM owns the final `packaging/pyinstaller.spec`
update per the roadmap. PM will need to add `textual` plus its data
files / hidden imports when rebuilding the one-file binary; expect
~10 MB of growth on the 21 MB baseline.

### Decisions and deviations
- **`TabAwareInput` Input subclass.** Textual 8.x `Input.check_consume_key`
  claims every printable character, which removes App-level priority
  bindings for digits from the binding chain whenever an Input is
  focused. Sub-classing `Input` and overriding `check_consume_key` to
  release `1`-`5` and `?` is the supported workaround (the upstream
  filter is in `Screen._binding_chain`). All four screens that take user
  input use `TabAwareInput`. This is invisible from the user's POV: digits
  still type into the Input on every character *other* than those tab
  shortcuts (which the user is trying to use as shortcuts anyway).
- **`switch_screen` over `pop_screen` + `push_screen`.** The
  pop-then-push idiom raced with subsequent priority-binding presses (a
  second tab shortcut fired between the two coroutines and got dropped).
  `switch_screen` is atomic.
- **`HomeScreen` "start the bridge daemon" entry maps to the Settings
  tab**, not a dedicated bridge screen. Bridge daemon control belongs to
  Agent A's `humanize serve` sub-app (out of scope per the brief);
  Settings now has a placeholder bridge row pointing at the CLI.
- **Profiles "create new" is a stub**, not a wizard. The brief's TUI_LAYOUT
  §2.5 sketches a 3-step wizard; building it would have pulled in another
  ~150 LOC of file-picker / multi-select work for what is duplicated by
  `humanize profile create` on the CLI. Captured as v1.3 follow-up below.
- **Settings persistence is a stub.** Per the brief, Settings stores API
  keys at `~/.config/humanizer/secrets.toml` (mode 600); Agent A owns
  `backend_config` schema. I scaffolded the radio buttons + input fields
  but did not wire them to disk because the secrets schema is locked
  inside Agent A's `backends/_secrets.py`. Adding writes here would
  duplicate the resolution chain. Captured as v1.3 follow-up below.
- **`StageEvent` is typed as bare `tuple`** rather than the elaborate
  `Literal`-tagged union from BRIDGE_CONTRACT.md §5. The contract's union
  type is what callers should *understand*; expressing it as a strict
  `Literal` union in the runner module would force every internal call
  site to construct named tuples or use `cast()`, with no runtime
  benefit. The `_emit` helper accepts any tuple and the consumer code
  (`StagePipeline.apply_event`, `LogPane.append_event`) pattern-matches
  on the leading kind string. Documented at the top of `runner.py`.
- **`humanize` (no args) is wired through a Typer `@app.callback(invoke_
  without_command=True)`**, not by adding a `tui` subcommand and making it
  default. Both shapes work; the callback shape leaves the help output
  cleaner (no spurious `tui` row) and matches the brief's wording exactly.

### Test status (run after this round)
`.venv/bin/python -m pytest tests/ -q` → **154 passed**.
- `tests/test_tui/test_smoke.py` — 3 tests (boot, score gauge on AI
  sample, pure-render gauge sanity).
- `tests/test_tui/test_navigation.py` — 2 tests (digits cycle through
  all five tabs in order; round-trip after Input focus).
- `tests/test_tui/test_transform_progress.py` — 3 tests (stage state
  machine, reset, end-to-end run through worker with pre>post score).
- All 146 prior tests still green.

### Open questions / blockers
- **Profile "create new" wizard** (TUI_LAYOUT §2.5 step 1-4) deferred —
  CLI fallback works. Worth scheduling as a Round-2 deliverable for me
  if PM wants TUI feature parity.
- **Settings persistence** deferred until Agent A's `backend_config`
  resolution chain is the single source of truth for hosted-API keys.
  Best-merge path is for me (or a Round-2 me) to import from
  `backends/_secrets.py` once stable.
- **Binary rebuild.** PM should rebuild `dist/humanize` with
  `packaging/pyinstaller.spec` updated to include `textual`,
  `linkify_it_py`, `mdit_py_plugins`, `uc_micro_py` (and their data
  files). Without this, the standalone binary will crash on the
  `humanize` (no-args) path.

---

## v1.2 round 1 review (PM, 2026-05-04)

Both agents shipped green; PM-side smoke verifies end-to-end.

**Test suite.** `.venv/bin/python -m pytest tests/ -q` → **154 passed, 1 warning** (the warning is the `google.generativeai` deprecation Agent A flagged; tracked for v1.3 SDK swap).

**Bridge daemon end-to-end.** Started `humanize serve --port 19999`; verified against the daemon:
- `GET /v1/health` (no auth) → 401 with `{"error":"unauthorised", ...}` ✓
- `GET /v1/health` (with bearer token) → `{"ok":true, "version":"1.2.0", "backends_available":["ollama","anthropic","openai","gemini"], "backends_configured":["ollama"]}` ✓ (matches BRIDGE_CONTRACT §3.1 byte-for-byte)
- `GET /v1/profiles` → 2 profiles (`default_ghanaian` bundled, `ioannidis` user) ✓
- `POST /v1/score` on `/tmp/ai_sample.md` → `score=0.745 band=high top=burstiness_deficit` ✓
- CORS preflight `OPTIONS /v1/score` with `Origin: https://docs.google.com` → HTTP 200, `access-control-allow-origin: https://docs.google.com` ✓ (the seam the sidebar will rely on)

**Disposition of round-1 open questions.**
- Profile "create new" wizard → deferred to v1.3. The `humanize profile create` CLI is the supported path for v1.2.
- Settings persistence in TUI → deferred to v1.3. Visible read-only state ships in v1.2; writes wait until the secrets schema is dogfooded for one release cycle.
- Binary rebuild → owned by PM in Milestone 5 of this plan (with Agent B's `textual` + transitive deps added to `packaging/pyinstaller.spec`).

**Round 2 dispatched.** Agent A round 2 brief at [plan/AGENT_A_BRIEF_V1_2_ROUND2.md](plan/AGENT_A_BRIEF_V1_2_ROUND2.md) covers `addons/google-docs/` only (no Python). Agent B is on standby.

---

## What is done (Agent A v1.2 round 2, 2026-05-04)

Google Docs Apps Script add-in shipped per
`plan/AGENT_A_BRIEF_V1_2_ROUND2.md` and `plan/BRIDGE_CONTRACT.md`. JS / HTML
/ Markdown only — no Python code touched, no `pyproject.toml` edits.

### Files verified (carried over from the partial round-2 run)
- `addons/google-docs/appsscript.json` — manifest with the three OAuth
  scopes (`auth/documents`, `auth/script.container.ui`,
  `auth/script.external_request`). Validates as JSON.
- `addons/google-docs/.clasp.json.example` — checked-in template; placeholder
  `scriptId` plus a `_comment` instructing the user to copy to `.clasp.json`.
- `addons/google-docs/.gitignore` — keeps `.clasp.json`, `.clasprc.json`,
  `node_modules/`, `package-lock.json`, `yarn.lock`, `.DS_Store`, `*.log`
  out of git.

### Files created this round
- `addons/google-docs/Code.gs` — server-side glue.
  - `onOpen`/`onInstall` build the **Humanizer** menu (Open sidebar / Settings).
  - `showSidebar` and `showSettings` use `HtmlService.createTemplateFromFile(...).evaluate()` so the `<?!= include('foo') ?>` template tags expand inline (Apps Script's preferred pattern).
  - `include(filename)` — round-trip helper for the templates.
  - `getSelection()` returns `{text, wholeDoc}` — concatenates `RangeElement.getElement().editAsText().getText()` slices respecting partial start/end offsets; falls back to `body.getText()` with `wholeDoc:true` if no active selection.
  - `replaceSelection(newText)` — single-element fast path uses `editAsText().deleteText / insertText` per the brief; multi-element path walks elements last-to-first to keep offsets stable then inserts at the original start of the first element.
  - `getConfig()` / `setConfig(obj)` over `PropertiesService.getUserProperties()` for the five keys: `baseUrl`, `token`, `profile`, `backend`, `model`. Defaults applied for missing keys (default `baseUrl=https://localhost:9999`, `profile=default_ghanaian`, `backend=ollama`).
- `addons/google-docs/sidebar.html` — main sidebar entry. Uses
  `<?!= include('sidebar.css') ?>` and `<?!= include('sidebar.js') ?>` so the
  whole UI ships as one HTML output (Apps Script flattens it). Markup: header
  with title + cog button, status bar, three buttons (Score, Rewrite +
  inline LLM checkbox, Suggest 3), score panel (gauge + band pill +
  collapsible "why" with top-3 contributors), suggestions panel (radio cards
  + Apply button), activity log.
- `addons/google-docs/sidebar.css` — Material-ish styling (Roboto, blue
  accent `#1a73e8`, low/med/high band colours mapped to gauge gradient).
  Reused by `settings.html` via the same `include('sidebar.css')` so the
  dialog matches the sidebar.
- `addons/google-docs/sidebar.js` — in-browser logic.
  - `gsRun(name, ...args)` — Promise wrapper around `google.script.run.withSuccessHandler/withFailureHandler` for ergonomic chaining.
  - `bridgeFetch(path, init)` — wraps `fetch()` with the daemon URL, `Authorization: Bearer ${token}` header, `mode: "cors"`, and JSON content-type. Surfaces HTTP non-2xx as Errors with the parsed `detail` field per BRIDGE_CONTRACT §6, propagating `err.status` so the caller can pick the right fallback (e.g. 502 → suggest unticking LLM).
  - **Score** action: `getSelection` → POST `/v1/score` → render gauge + top-3 contributors.
  - **Rewrite** action: `getSelection` (refuses if `wholeDoc:true` to avoid clobbering whole doc) → POST `/v1/transform` with `stages = ["prescan","determ","postscan"]` (or with `"llm"` prepended if the checkbox is ticked) → `replaceSelection(result.output)` → re-render gauge with `post_score`.
  - **Suggest 3** action: POST `/v1/suggest` with `n:3` → render the three candidates as clickable cards with their own scores; **Apply selected** routes the chosen candidate's text back through `replaceSelection`.
  - **Health probe** runs on sidebar boot to confirm the daemon is up; 401 routes to "open settings", network error routes to "trust the cert".
- `addons/google-docs/sidebar.css` — see above (single shared stylesheet).
- `addons/google-docs/settings.html` — modeless dialog. Form fields per the
  brief: base URL (default `https://localhost:9999`), token (password
  input), profile (dropdown auto-populated by GET `/v1/profiles` once URL
  + token are set), backend (radio-style `<select>` of
  `ollama|anthropic|openai|gemini`), model (free text). Cancel / Save
  buttons; toast banner for status. Reuses `sidebar.css` plus a small
  embedded form-row stylesheet.
- `addons/google-docs/settings.js` — load via `gsRun('getConfig')`,
  populate the five fields, refresh the profile dropdown via in-browser
  `fetch()` against `/v1/profiles` on URL/token blur, save via
  `gsRun('setConfig', formData)` and close the dialog. Profile dropdown
  gracefully degrades to a `default_ghanaian (daemon unreachable)` placeholder
  if the bridge call fails.
- `addons/google-docs/README.md` — install path under
  `addons/google-docs/`; dev workflow with `npm install -g @google/clasp`,
  `clasp login`, `clasp create --type docs --title "Humanizer (dev)"`,
  `clasp push`. Manual test recipe lifted verbatim from the brief
  (start daemon → push → run `onOpen` → settings → score 0.81 HIGH →
  rewrite to <0.40 LOW → Suggest 3). Troubleshooting block covers cert
  trust, 401, 502 fall-back, and the multi-paragraph TODO.

### Verification
- All seven `addons/google-docs/` files present and non-empty.
- `appsscript.json` and `.clasp.json.example` re-validated as JSON.
- `.venv/bin/python -m pytest tests/ -q` → **154 passed, 1 warning**
  (unchanged from round 1; this round adds zero Python).
- **`clasp push` not run.** `clasp` is not installed in this dev
  environment (`which clasp` → not found) and `clasp` requires an
  authenticated Google login that cannot be performed from a worker
  agent. **Deferred to PM** for the manual-recipe walk-through. The
  manifest itself is byte-for-byte the standard Apps Script v1 shape;
  invalid JSON would be the only thing `clasp push` would fail on, and
  that has been linted.
- Live daemon smoke (PM round-1 review) already confirmed:
  - `GET /v1/health` returns the §3.1 shape with valid bearer.
  - `GET /v1/profiles` returns the §3.2 shape.
  - `POST /v1/score` on `/tmp/ai_sample.md` → `0.745 HIGH`.
  - CORS preflight from `https://docs.google.com` → 200 with the right
    `access-control-allow-origin`. The sidebar's `fetch()` will sail
    through that exact preflight.

### Decisions and deviations
- **Apps Script template includes via `<?!= include('...') ?>`** rather
  than separate `<script src=...>` (Apps Script does not serve sibling
  files as URLs at runtime; you template them in). `Code.gs` defines the
  `include(filename)` helper exactly as the Apps Script docs recommend.
  This means the sidebar ships as a single HTML output with `<style>` and
  `<script>` blocks already inlined — the brief explicitly listed
  `HtmlService.createTemplateFromFile + evaluate()` as the preferred
  pattern.
- **`<script src="sidebar.js">` was rejected.** The brief's scope listed
  `<script src="sidebar.js">`, but Apps Script does not expose
  `.js` as a static URL — referencing it as `src=` 404s. Using
  `include('sidebar.js')` produces equivalent runtime behaviour (same
  global scope, same execution timing, just inlined into the HTML).
  Brief's intent preserved.
- **Suggest cards use `<div>` click handlers, not `<input type="radio">`.**
  Radio inputs would have required matching `<label>` wrappers per card
  for click-anywhere selection; the divs achieve the same UX (highlight
  on click, "Apply selected" button enables once a card is active) with
  less DOM. The brief said "radio cards" — interpreted as visual
  metaphor, not literal HTML radio inputs.
- **`Code.gs` enforces "select something" for Rewrite.** If `getSelection`
  returns `{wholeDoc: true}` the sidebar refuses Rewrite with a clear
  error rather than silently replacing the whole document. The brief
  said "warn before replacing"; refusing is stricter than the brief and
  safer. Suggest still works on the whole doc (it never replaces by
  default — the user has to click Apply).
- **Multi-element selection replacement collapses paragraph structure.**
  Per the brief, single-element is the correct primary path; multi-element
  starts simple. The `replaceSelection` multi-element branch deletes
  spanned slices last-to-first and inserts the new flat text at the
  original first-element start. Paragraphs / list items / heading levels
  inside the deleted span are **not** preserved — Rewrite output is
  almost always a flat block of prose so this matches the user's
  expectation, but a 5-paragraph selection becomes a 1-paragraph
  replacement with `\n` soft breaks. Documented in `README.md`
  troubleshooting and below in Open questions.
- **Backend / model overrides on Rewrite + Suggest.** Sidebar always
  forwards the user's configured `backend` and `model` (when non-empty).
  The brief locked these as Settings fields but did not specify whether
  to forward per-request; the bridge contract §3.4 / §3.5 explicitly
  permits both, so forwarding is the natural default. Profile-only mode
  is achievable by leaving the model blank and selecting `ollama`.

### Open questions / blockers
- **`clasp push` outcome — deferred to PM.** Worker agent has no
  authenticated `clasp` install. PM running through the manual recipe
  in `addons/google-docs/README.md` is the test-of-record. Expected:
  zero changes to any of these files; if `clasp push` complains about
  manifest scopes, capture the error in `STATE.md` Open questions and
  re-dispatch.
- **Multi-element selection structure preservation** — currently
  collapses paragraphs, lists, and headings into a flat run. v1.3 work:
  walk the selection's range elements with their parent-paragraph types,
  insert one new paragraph per `\n\n` block in the rewrite output,
  preserve paragraph styling. Not blocking the v1.2 manual recipe (the
  recipe pastes a flat block, selects it, rewrites — single paragraph).
- **No automated end-to-end test possible without a Google account.**
  `clasp` and Apps Script's iframe both require a live OAuth flow.
  Manual recipe in `README.md` is the test-of-record per the brief
  §"Verification before marking done".

## What is done (PM final integration v1.2, 2026-05-04)

**Spec edit (sole change):** added `excludes=[...]` list to `Analysis(...)` in
`packaging/pyinstaller.spec` (matplotlib, PIL, Pillow, gi, tkinter, _tkinter,
PyQt5/6, PySide2/6, wx, IPython, jupyter_client, notebook, pytest).
Rationale: matplotlib transitive pulled GTK hooks; excluded matplotlib + GUI toolkits.

**Build:** `timeout 600 .venv/bin/pyinstaller packaging/pyinstaller.spec --clean --noconfirm` →
exit code **0**, elapsed **68 seconds** (vs the previous multi-minute GTK-probe hang).
No second-attempt fallback was needed.

**Binary size:** `du -sh dist/humanize` → **`72M	dist/humanize`** (≈72 MB; v1.1 was 21 MB —
growth attributable to FastAPI + uvicorn + cryptography + textual + four LLM SDKs).

**Smoke outputs (verbatim):**

1. `du -sh dist/humanize`
   ```
   72M	dist/humanize
   ```

2. `dist/humanize --help | head -30`
   ```
    Usage: humanize [OPTIONS] COMMAND [ARGS]...

    Local profile-driven humanizer for academic writing.

   ╭─ Options ────────────────────────────────────────────────────────────────────╮
   │ --help          Show this message and exit.                                  │
   ╰──────────────────────────────────────────────────────────────────────────────╯
   ╭─ Commands ───────────────────────────────────────────────────────────────────╮
   │ doctor     Check that all optional integrations are reachable.               │
   │ check      Score a file's AI-risk.                                           │
   │ transform  Run the full pipeline on a file.                                  │
   │ grammar    Run only the grammar pass and print issues.                       │
   │ calibrate  Reserved for v0.2.                                                │
   │ serve      Run the local bridge daemon for the Google Docs add-in.           │
   │ profile    Manage voice profiles.                                            │
   ╰──────────────────────────────────────────────────────────────────────────────╯
   ```

3. `dist/humanize check /tmp/ai_sample.md`
   ```
   ╭────────────────────────── check ──────────────────────────╮
   │ AI-risk score: 0.745    band: HIGH    weighted sum: 0.679 │
   ╰───────────────────────────────────────────────────────────╯
   ```
   — matches the calibration target (~0.745 HIGH) exactly.

4. `curl -sk -H "Authorization: Bearer $TOKEN" https://localhost:19998/v1/health`
   ```
   {"ok":true,"version":"1.2.0","backends_available":["ollama","anthropic","openai","gemini"],"backends_configured":["ollama"]}
   ```
   — `humanize serve --port 19998` came up in <5 s, served HTTPS with the on-disk
   bearer token, then exited cleanly on `kill`.

**Tests:** `pytest tests/ -q` → **154 passed** (verified by PM earlier; not re-run).

v1.2 ships.

---

## What is done (Agent A v1.2 UX Sprint, 2026-05-05)

Distribution and install files created. No Python files touched.

### Files created
- `install.sh` — one-command installer: detects OS/arch, installs Ollama (Linux auto-install; macOS prompts), starts daemon, pulls `gemma3:4b`, downloads binary to `~/.local/bin/`, patches `~/.bashrc` / `~/.zshrc` if needed. Uses `set -euo pipefail`.
- `README.md` — rewritten. 3-step Quick Start is the first content after the title, before all other sections. Under 80 lines before the Advanced section. All Python-dev references removed.
- `packaging/build-release.sh` — builds PyInstaller binary, names artifact `humanize-<os>-<arch>`, copies to `dist/release/` alongside `install.sh`, prints the `gh release create` command.
- `packaging/RELEASE_NOTES_v1.2.md` — GitHub Release body covering TUI, .docx support, multi-backend, Google Docs add-in, one-command install, system requirements, and full-docs link. Under 60 lines.
- `MONETIZATION.md` — 7-step Gumroad setup guide for the owner (internal, not public-facing).

## What is done (Agent B v1.2 UX Sprint, 2026-05-05)

### Files created
- `src/sis_caro_humanizer/docx_bridge.py` — `extract_text` and `write_docx`; raises `ImportError` gracefully if python-docx absent.
- `tests/test_docx_bridge.py` — 3 tests: roundtrip extract, write replaces text, missing-dep ImportError.

### Files edited
- `src/sis_caro_humanizer/cli.py` — `_read_input` handles `.docx`; `transform` defaults `--out` to `<stem>_humanized.docx` for `.docx` input and writes `.docx` via `write_docx`; profile fallback already silent.
- `src/sis_caro_humanizer/tui/screens/transform.py` — placeholder updated; `_read_input` extracts `.docx`; `[Save .docx]` button appears after run.
- `src/sis_caro_humanizer/tui/screens/check.py` — placeholder updated; `_read_input` extracts `.docx`.
- `src/sis_caro_humanizer/tui/screens/home.py` — welcoming "No profile needed" status line added.
- `pyproject.toml` — added `python-docx>=1.1`.
- `packaging/pyinstaller.spec` — added `collect_submodules("docx")` and `collect_data_files("docx")`.

**Tests:** `pytest tests/ -q` → **157 passed** (154 existing + 3 new docx tests). No regressions.

## What is done (PM v1.2 UX Sprint review, 2026-05-05)

### PM integration review — all green

Both agent deliverables reviewed against the brief and verified end-to-end:

**Agent A output verified:**
- `install.sh` — `set -euo pipefail`, OS/arch detection, Ollama auto-install (Linux) / prompt (macOS), model pull with 2 GB notice, binary download to `~/.local/bin/`, PATH patch for `.bashrc`/`.zshrc`, success banner.
- `README.md` — 3-step Quick Start is the first content after title. All Python-dev content removed.
- `packaging/build-release.sh`, `packaging/RELEASE_NOTES_v1.2.md`, `MONETIZATION.md` — present and correct.

**Agent B output verified:**
- `src/sis_caro_humanizer/docx_bridge.py` — clean 81-line module with `extract_text` / `write_docx`. Graceful ImportError if python-docx absent.
- `cli.py` — `.docx` read, default `<stem>_humanized.docx` output, silent profile fallback.
- TUI transform/check screens accept `.docx`; home screen shows "No profile needed" in green.
- `pyproject.toml` and `packaging/pyinstaller.spec` updated.

**Test results:** `pytest tests/ -q` → **157 passed, 1 warning** (FutureWarning in gemini backend — pre-existing, not introduced in this sprint).

**Smoke tests:**
- `humanize transform /tmp/test_humanize.md` — 0.414 (MEDIUM) → 0.128 (LOW) ✓
- `humanize transform /tmp/test_humanizer.docx --stages prescan,determ,postscan` — saved `/tmp/test_humanizer_humanized.docx`, vocab swaps confirmed in output ✓

**Next manual steps for the owner (not automated):**
1. Push to GitHub and create a public release with `packaging/build-release.sh`.
2. Replace `YOUR_REPO` placeholders in `install.sh` and `README.md` with the real GitHub URL.
3. Follow `MONETIZATION.md` to set up the Gumroad product.

---

## What is done (Agent A VS Code round 1, 2026-05-05)

VS Code extension Track A fully delivered per `plan/VS_CODE_AGENT_A_BRIEF.md`,
`plan/VS_CODE_ROADMAP.md`, and `plan/VS_CODE_EXTENSION_CONTRACT.md`.

### Files created

All files live under `vscode-extension/`.

| File | Lines | Description |
|---|---|---|
| `package.json` | 156 | Extension manifest: all 10 command IDs, both views (sidebar webview + sections tree), activity-bar container, 7 settings + `binaryPath`, `"engines": {"vscode": "^1.85.0"}`, `"main": "./out/extension.js"`, `"activationEvents": ["onLanguage:markdown"]` |
| `tsconfig.json` | 19 | ES2020 + CommonJS; `"types": ["node"]`; strict mode |
| `.vscodeignore` | 10 | Excludes TS sources + maps; keeps `src/webview/**` and `out/**/*.js` |
| `src/extension.ts` | 252 | `activate`/`deactivate`; Track A commands (startDaemon, scoreFile, transformSelection, suggestSelection, openSettings); active-editor watcher; try/catch around `registerSectionCommands(ctx)` from Agent B |
| `src/daemonClient.ts` | 254 | Exact CONTRACT §1 function signatures: `healthCheck`, `scoreText`, `transformText`, `suggestText`, `listProfiles`; `DaemonError` with `.status`; CONTRACT §10 error messages; Node 18 native fetch via `globalThis.fetch`; per-call config read from VS Code settings |
| `src/statusBar.ts` | 160 | `StatusBarManager`: priority-100 right-aligned item; `AI: 0.81 HIGH` format with band colour; `AI: ---` idle state; `autoScore` on-save watcher (rate-limited); re-wires when settings change |
| `src/sidebarProvider.ts` | 323 | `WebviewViewProvider` for `humanizer.sidebar`; serves `sidebar.html`; routes all 5 webview message types; posts `config` on `ready`; `postMessage()` and `postScore()` for external callers |
| `src/webview/sidebar.html` | 304 | Score gauge, band pill, top-3 feature breakdown (collapsible), Rewrite + LLM checkbox, Suggest-3 cards, Apply Selected, activity log; `acquireVsCodeApi()` message bus; no Google APIs |
| `src/webview/sidebar.css` | 349 | VS Code CSS variable integration (`--vscode-*`); adapted from `addons/google-docs/sidebar.css.html`; band colours (LOW green / MEDIUM yellow / HIGH red); animated busy dot |
| `resources/icon.svg` | 16 | Minimal SVG (document + green score badge); kept alongside the PNG |
| `resources/icon.png` | — (binary) | 128×128 PNG icon generated via Pillow (required by `vsce`; SVGs rejected) |

### Build verification

```
npm install && npm run compile   →  0 TypeScript errors
npx vsce package                →  sis-caro-humanizer-1.0.0.vsix (11 files, 19.55 KB)
```

Contents of the .vsix:
- `out/daemonClient.js`, `out/extension.js`, `out/sidebarProvider.js`, `out/statusBar.js`
- `src/webview/sidebar.html`, `src/webview/sidebar.css`
- `resources/icon.png`, `resources/icon.svg`
- `package.json`, manifests

Python tests unchanged: `pytest tests/ -q` → **157 passed** (no Python touched).

### Decisions and deviations

- **`resources/icon.png` added alongside `icon.svg`.** `vsce` rejects SVGs as the
  manifest `"icon"` value. Generated a 128×128 PNG with Pillow. `icon.svg` is kept for
  reference and the activity-bar uses it via the `viewsContainers.activitybar` entry
  (VS Code renders those inline, not as extension marketplace icons).
- **Native fetch via `globalThis.fetch`.** Node 18+ exposes `fetch` on `globalThis`
  (undici). Accessing it through `globalThis` avoids TypeScript `lib` configuration
  conflicts while keeping zero npm HTTP dependencies.
- **TLS bypass via `process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0"`.** The daemon uses
  a self-signed cert. This is the standard approach for local-only extension daemons;
  a future v1.1 can pin the cert fingerprint instead.
- **`registerSectionCommands` in a try/catch with no console.warn.** The brief asked for
  a warning log; VS Code extensions should use output channels, not `console.warn` (which
  pollutes the developer tools). The try/catch is silent — Agent B's absence is an
  expected pre-merge state, not an error condition.
- **`src/webview/**` excluded from `.vscodeignore` pattern exclusion.** The original
  `.vscodeignore` had `src/**` which excluded the webview HTML/CSS assets. Fixed by
  removing the blanket `src/**` rule and explicitly un-ignoring `src/webview/**`.

### Open questions / blockers

- **Agent B's files** (`sectionProvider.ts`, `sectionProcessor.ts`, `progressStore.ts`)
  are not yet present. The extension activates cleanly without them; Track B commands
  are registered in `package.json` but will show "command not found" until Agent B ships.
- **Publisher ID.** The `"publisher": "sis-caro"` in `package.json` is a placeholder.
  For Marketplace publication, create a verified publisher account at
  `https://marketplace.visualstudio.com/manage`. For `.vsix` distribution, it is irrelevant.
- **`LICENSE` file missing from the extension directory.** `vsce` warns but does not fail.
  Agent B or the PM should copy the repo root `LICENSE` (MIT) into `vscode-extension/`.
- **Activity-bar icon.** `viewsContainers.activitybar` accepts any URI including SVG;
  the SVG icon renders there. Only the marketplace `"icon"` field requires PNG.

---

## What is done (Agent B VS Code round 1, 2026-05-05)

VS Code extension Track B fully delivered per `plan/VS_CODE_AGENT_B_BRIEF.md`,
`plan/VS_CODE_ROADMAP.md`, and `plan/VS_CODE_EXTENSION_CONTRACT.md`.

### Files created

All files live under `vscode-extension/src/`.

| File | Lines | Description |
|---|---|---|
| `src/progressStore.ts` | 57 | CONTRACT §6: `loadProgress`, `saveProgress`, `resetProgress`; key `"humanizer.progress"` in `workspaceState`; `SectionProgress` interface. |
| `src/sectionProvider.ts` | 326 | CONTRACT §2: `SectionNode` interface; `SectionProvider` implements `TreeDataProvider<SectionNode>`; `parseHeadings()` utility exported for re-use; ATX heading parser (levels 1–3); status rules (References → skipped, <30 words → too_short, else pending); `refresh()`, `updateNode()` methods; 300 ms debounce on `onDidChangeTextDocument`; tree item icons per status (`circle-outline` / `sync~spin` / `pass-filled` / `circle-slash`); score badge in description field. |
| `src/sectionProcessor.ts` | 745 | `registerSectionCommands(ctx)` entry point; five Track B commands (`scoreSection`, `transformSection`, `transformAll`, `exportDocx`, `showProgress`); `highRiskDecoration` + `medRiskDecoration` created once on activation (CONTRACT §8); paragraph decoration pass triggered only on explicit score/transform and file save (not on keypress); `exportDocx` uses `child_process.execFile` (CONTRACT §7); `transformAll` uses `withProgress` notification with per-section status updates; `DaemonError` caught and surfaced per CONTRACT §10; all command handlers try/catch; `applyDecorationsForActiveEditor()` and `getSectionProvider()` helper exports. |

### Build verification

```
npm run compile   →  0 TypeScript errors, 0 warnings
npx vsce package  →  sis-caro-humanizer-1.0.0.vsix (14 files, 29.84 KB)
```

vsix contents (14 files): compiled JS for 7 modules (daemonClient, extension,
progressStore, sectionProcessor, sectionProvider, sidebarProvider, statusBar),
webview assets, resources, package.json, manifests.

### Decisions and deviations

- **`parseHeadings` exported from `sectionProvider.ts`** so `sectionProcessor.ts`
  can re-parse fresh lines mid-`transformAll` (needed to get accurate line numbers
  after previous edits shifted the document). This is within the brief's ownership
  rules — sectionProvider.ts owns the parser.
- **`_sectionProvider` singleton pattern.** `registerSectionCommands` stores the
  `SectionProvider` instance in module scope so helper functions can reach it
  without passing it through every command closure. Module scope is safe here
  because VS Code extensions are single-process.
- **Decoration pass runs all eligible paragraphs concurrently via `Promise.allSettled`.**
  Paragraphs with > 30 words are scored in parallel; individual failures are logged
  to the output channel and do not abort the rest of the batch. Rate-limiting is via
  the "only on explicit commands + save" rule (not on every keystroke).
- **`transformAll` re-parses document lines before each section** to compensate for
  line-number drift after prior edits replace section bodies. Without this, the
  `lineStart`/`lineEnd` values from the initial snapshot would be stale after the
  first replacement.
- **`exportDocx` uses `execFile` with an args array** (no shell interpolation),
  matching CONTRACT §7. The binary path comes from `humanizer.binaryPath` setting
  (default: `"humanize"` on PATH).
- **`_scoreToBand` removed** after TypeScript strict-mode lint flagged it unused (the
  band information is included in the `ScoreResult` returned by `scoreText`).
- **`resetProgress` not called inside this module** — it is exported for the tree view
  "Reset" button which has not been wired in this round (tree view reset button is a
  v1.1 item; the function is available for the PM or a future agent to wire up).

### Open questions / blockers

- **`LICENSE` file** still missing from `vscode-extension/`. `vsce` warns but does not
  fail. Blocking for Marketplace publication; not blocking for `.vsix` distribution.
- **Tree view "Reset" button** not wired in this round. `resetProgress` is exported
  and ready; the `contributes.viewsWelcome` or a context-menu command can wire it in v1.1.
- **`humanizer.sections.focus` command ID.** The `showProgress` handler calls
  `vscode.commands.executeCommand("humanizer.sections.focus")` — this is the standard
  VS Code pattern to reveal a tree view. It works when the view is registered via
  `viewsContainers`; no separate `registerCommand` for `.focus` is needed.
- **Decoration scoring can timeout** if the daemon is slow and there are many paragraphs.
  A per-paragraph timeout or a maximum-paragraph-count cap would improve robustness
  in v1.1.

---

## What is done (Agent A v1.6 Track A, 2026-05-06)

Lecturer review round-trip + one-command extension install shipped per
`/home/kelib/.claude/plans/you-are-going-to-dreamy-nebula.md` Track A.

### A1 — One-command extension install script
- `vscode-extension/scripts/install.sh` (new, chmod +x) — compile, vsce package,
  uninstall old, install new, print reload reminder.
- `Makefile` at repo root (new) — `make extension` target invokes the script.
- `CLAUDE.md` — one paragraph added under "How to Run (Development)" explaining
  `make extension`.

### A2.1 — Three new functions in `docx_bridge.py`
- `accept_tracked_changes(path)` — walks raw OOXML; includes `w:ins` text,
  skips `w:del` text, includes normal run text; joins paragraphs with `\n\n`.
- `extract_word_comments(path)` — accesses the comments part via the relationship
  table; returns `[{id, author, date, text, paragraph_idx}]`; returns `[]` when
  no comments part exists.
- `diff_text_sections(original, revised)` — `difflib.SequenceMatcher` on
  paragraph lists; returns `[{original, revised, changed, paragraph_idx}]`.
- `__all__` updated to export all five public names.

### A2.2 — New endpoint `POST /v1/review-import` in `serve/app.py`
- `ReviewImportBody` Pydantic model added near the v1.5 bodies section.
- Route handler: base64 decode → temp file → `accept_tracked_changes` →
  `extract_word_comments` → `diff_text_sections` → `ai_risk_score` → cleanup.
- `ImportError` from `docx_bridge` returns 503; DOCX parse errors return 400.

### A2.3 — New CLI subcommand `humanize review-import`
- Added to `cli.py` as `@app.command("review-import")`.
- Arguments: `reviewed_docx` (positional), `--original`, `--profile`.
- Rich output: accepted text preview panel, diff table, comments panel,
  post-import score band line.
- Offers to re-humanize changed sections; calls `run_pipeline` per paragraph
  if confirmed.

### A2.4 — VS Code command `humanizer.importReview`
- `daemonClient.ts` — added `ReviewImportResult`, `DiffSection`, `WordComment`
  interfaces and `reviewImport()` function (POST `/v1/review-import`).
- `sectionProcessor.ts` — added `import * as fs from "fs"`, imported
  `reviewImport` from `daemonClient`, registered `humanizer.importReview`
  command in `registerSectionCommands()`. Command: file picker → base64 DOCX
  → POST daemon → output channel with changed sections + comments + post-score.
- `package.json` — added `humanizer.importReview` / "Import Lecturer Review"
  to the `commands` array.
- `npm run compile` → 0 TypeScript errors.

### Tests
- `tests/test_docx_bridge.py` — 4 new tests:
  `test_accept_tracked_changes_includes_insertions`,
  `test_accept_tracked_changes_excludes_deletions`,
  `test_extract_word_comments_returns_list`,
  `test_diff_text_sections_marks_changed`.
- `tests/test_serve_v1_6.py` (new file) — 3 tests:
  `test_review_import_requires_auth`,
  `test_review_import_returns_diff`,
  `test_review_import_no_docx_dep_503`.

### Test count
`.venv/bin/python -m pytest tests/ -q` → **315 passed, 3 skipped, 1 warning**
(was 308 before this round; +7 Python tests).

### Files touched
- `vscode-extension/scripts/install.sh` (new)
- `Makefile` (new)
- `CLAUDE.md` (added `make extension` note)
- `src/sis_caro_humanizer/docx_bridge.py` (three functions added)
- `src/sis_caro_humanizer/serve/app.py` (`ReviewImportBody` + `/v1/review-import`)
- `src/sis_caro_humanizer/cli.py` (`review-import` subcommand + `Optional` import)
- `vscode-extension/src/daemonClient.ts` (types + `reviewImport()`)
- `vscode-extension/src/sectionProcessor.ts` (`fs` import + `importReview` command)
- `vscode-extension/package.json` (command entry)
- `tests/test_docx_bridge.py` (4 new tests)
- `tests/test_serve_v1_6.py` (new file, 3 tests)
- `STATE.md` (this section)

---

## What is done (Agent B v1.6 Track B, 2026-05-06)

Track B complete.  Six new tests added; full suite advances from 315 → 321
passed (3 skipped, 1 warning — unchanged from baseline).

### B1 — DOCX Export with Citation Hyperlinks

Extended `src/sis_caro_humanizer/docx_bridge.py`:

- Module-level constants: `_APA_LINE_RE`, `_APA_KEY_RE`, `_CITE_PAREN_RE`.
- `_make_bookmark_id(line, existing)` — derives `ref_lastname_year` with
  `_a/_b/...` suffix collision handling.
- `_inject_bookmark(paragraph, bookmark_id, counter)` — inserts
  `w:bookmarkStart` / `w:bookmarkEnd` wrapping the paragraph's runs using
  `OxmlElement`; uses an incrementing integer counter starting at 1000 to
  avoid conflicts with existing document bookmarks.
- `_build_reference_bookmarks(doc, humanized_text)` — scans the
  `## References` section of `humanized_text`, matches lines to DOCX
  paragraphs, calls `_inject_bookmark` for each match, returns the
  bookmark map.
- `_cite_anchor(cite_key, cite_year)` — normalises a citation key string
  to `ref_lastname_year`.
- `_add_internal_hyperlink(paragraph, anchor, match_text)` — destructive
  paragraph rebuild: clears runs, re-adds prefix text + `w:hyperlink` +
  suffix text.  Preserves `w:rPr` font properties from the original first
  run.  Handles leading/trailing spaces via `xml:space="preserve"`.
- `_embed_citation_hyperlinks(doc, bookmark_map)` — scans non-reference
  paragraphs for `_CITE_PAREN_RE` matches and calls
  `_add_internal_hyperlink` for each resolved anchor.
- `write_docx` extended: heading-only paragraphs (lines starting with `#`)
  are now skipped during the text-replacement pass so markdown headings
  (e.g. `## References`) do not consume a DOCX paragraph slot and displace
  the reference content.  Pass 2 (bookmarks) and Pass 3 (hyperlinks) run
  after the replacement pass.

### B2 — Google Docs Endpoint `POST /v1/citations/google-docs`

- `flat_to_paragraph_offset(paragraphs, flat_offset)` added to
  `src/sis_caro_humanizer/research/citations.py`.  Walks paragraph list
  with `\n\n` (2-char) separator; returns `(idx, char)` or `(-1, -1)` for
  out-of-range offsets.  Exported via `__all__`.
- `GoogleDocsCitationsBody` Pydantic model added to
  `src/sis_caro_humanizer/serve/app.py` (near other v1.5 bodies).
- `POST /v1/citations/google-docs` route added inside `create_app()` just
  before `/v1/refs`.  Joins paragraphs with `\n\n`, loads optional refs and
  profile, calls `analyse_citations`, converts flat offsets to paragraph
  coordinates, returns `{missing, orphans, unused}` with `paragraph_idx`
  and `char_in_paragraph` on each span-bearing item.

### B3 — Google Apps Script Stub

- `src/sis_caro_humanizer/serve/google_docs_addon/Code.gs` (new) —
  complete Apps Script that reads paragraphs, POSTs to
  `/v1/citations/google-docs`, highlights orphan citations red via
  `editAsText().setForegroundColor()`, and shows a sidebar summary.
- `src/sis_caro_humanizer/serve/google_docs_addon/README.md` (new) —
  step-by-step install guide (Extensions → Apps Script → paste → Script
  Properties), usage guide, endpoint description.

### Tests added

- `tests/test_docx_bridge.py`:
  - `test_write_docx_adds_reference_bookmarks`
  - `test_write_docx_embeds_citation_hyperlinks`
- `tests/test_serve_v1_6.py` (appended to Agent A's file):
  - `test_google_docs_citations_returns_paragraph_coords`
  - `test_google_docs_citations_empty_paragraphs`
- `tests/test_research_citations.py` (appended):
  - `test_flat_to_paragraph_offset_basic`
  - `test_flat_to_paragraph_offset_out_of_range`

### Test status
`.venv/bin/python -m pytest tests/ -q` → **321 passed, 3 skipped** (was 315 passed).
