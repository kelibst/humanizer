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
