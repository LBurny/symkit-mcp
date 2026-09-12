# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Engineering baseline: the rules the project already declared are now enforced
instead of assumed.

### Added

- **CI quality gate** (`.github/workflows/ci.yml`): ruff, mypy, pytest on Python
  3.10 and 3.12, and the modularity ratchet. The release pipeline runs the same
  checks as a `quality` job that `build` depends on, so a tag can no longer
  publish untested code. (Not yet exercised on a runner.)
- **Modularity ratchet** (`scripts/check_modularity.py`, `modularity-baseline.json`):
  files and functions over the hard limit are frozen at their current size and may
  only shrink; new code must respect the limit. `--update` lowers the baseline and
  refuses to raise it.
- Tests for the public library API: `tests/application/test_use_cases.py` and
  `tests/infrastructure/test_basic_verifier.py` (27 cases). `use_cases.py` and
  `BasicVerifier` previously had no direct coverage despite being exported from
  `symkit/__init__.py`.

### Changed

- **Bylaw §5.1** thresholds raised and made honest: files 300 soft / 600 hard,
  functions 40 / 60, classes 200 / 400, modules 12 / 20. File and function lengths
  are machine-enforced; class, module, and complexity limits are review triggers.
  New §5.1.1 defines the ratchet baseline.
- Dropped unused dev dependencies (`black`, `pylint`, `bandit`, `safety`); ruff
  covers formatting and linting. All four remain runnable on demand via `uvx`.
- `ROADMAP.md` refreshed from 1.1.0 to 1.6.1 reality; `ARCHITECTURE.md` layer
  inventories corrected (they listed directories that no longer exist).
- `server.py`'s version-override comment translated to English, per the code-comment
  convention.

### Fixed

- `tests/formulas/test_formula_index_store.py` performance budgets were tight
  wall-clock assertions (5s build / 100ms search) that failed under full-suite load
  while passing in isolation. Loosened to order-of-magnitude guardrails that still
  catch accidental quadratic indexing.
- `BasicVerifier` picked the integration/differentiation variable with
  `list(free_symbols)[0]`, so the same correct step could be verified in one
  process and failed in another (set order follows `PYTHONHASHSEED`); constant
  results like d/dx(5x) = 5 were always failed. Both checks now try every free
  symbol in sorted order and succeed if any variable proves the step.
- `BasicVerifier.verify_derivation` counted inconclusive steps (unknown
  operations, unprovable checks) as failures. They are now reported separately
  as `inconclusive_steps`, and a derivation with only inconclusive steps returns
  INCONCLUSIVE instead of FAILED.
- `tools/_state.reset_catalog` dropped the shared formula catalog without
  closing its SQLite connection, leaking the index file lock (an `os error 32`
  source on Windows). It now closes the store first.

## [1.6.1] - 2026-09-11

Hardening release for the formula index, from a second black-box test pass
that probed path safety, adversarial queries, duplicate detection, concurrent
writes, and the 1.5.2 → 1.6.x upgrade path.

### Fixed

- **Path traversal in formula writes.** `formula_add` and `formula_promote`
  passed the caller-supplied `id`, `category`, and `new_id` straight into a
  filesystem join, so `id="../../escaped"` wrote a YAML file outside the
  library root — and then reported failure, leaving the stray file behind.
  Write targets are now resolved and must stay under the library root;
  offending calls fail before touching disk. Ids must be plain file names.
- **Unrelated expression-less entries collapsed as duplicates.**
  `content_hash("")` returned the shared sentinel `"empty"`, so any two
  formulas with no expression were treated as the same content and only one
  stayed visible in search. An empty expression now yields no content identity
  and is never grouped.
- **`formula_promote` / `formula_remove` missed externally written files.**
  Both read the index without reconciling it first (unlike `search` / `get`),
  so a formula written by hand or by another process was reported as
  "not found" until some unrelated call happened to refresh the index.

### Changed

- `FormulaLibrary.add_or_update` validates the target path before writing and
  only updates its in-memory index after the file is safely on disk.

## [1.6.0] - 2026-09-11

### Added

- **Persistent formula index.** The formula library is now served from a
  rebuildable SQLite FTS5 index (trigram tokenizer) over the unchanged YAML
  layers — bundled seeds, session-derived staging, and the curated user
  overlay. Search matches Chinese aliases and expression content, and stays
  deterministic and offline.
- **Curation workflow.** Entries carry a `tier` (`seed` / `staging` /
  `curated`); `formula_search` accepts a `tier` filter and ranks curated above
  staging. New tools: `formula_promote` (staging → curated with metadata
  overrides), `formula_reindex` (rebuild after hand edits), `formula_stats`
  (per-tier counts, duplicate groups, last sync).
- **Content-hash dedup.** Entries are hashed by canonicalized expression;
  search collapses duplicates to one representative with a `duplicates`
  count. `scripts/prune_staging.py` quarantines test-scaffolding residue from
  the staging store (dry-run by default).

### Changed

- `session_complete(auto_save=True)` now assigns deterministic staging ids
  (`<slug>-<hash6>`) instead of the random session hex id. Re-completing
  identical content is an idempotent re-save that merges `session_ids`; the
  `-v2` minting branch is gone.
- Write paths (`formula_add`, `formula_remove`, `formula_promote`,
  `session_complete`) update the index synchronously — new formulas are
  searchable and recommendable in the same process, no restart needed.
- `derive()` recommendations read the index, so `verified` status and
  derivation provenance now reach the recommender.

### Fixed

- Session-derived formulas no longer require a server restart to appear in
  `formula_search` results.
- Startup eagerly reconciles the index in the worker thread alongside the
  SessionManager warmup.
- **`formula_search` no longer returns semantically unrelated results for
  generic-word queries.** The index path had dropped the legacy
  `FormulaLibrary._STOPWORDS` suppression, so FTS matched any single token:
  `formula_search("Einstein field equations")` returned Euler and
  Navier-Stokes equations. A hit now requires a discriminative token;
  all-generic-noun queries keep the legacy low-relevance behaviour, and
  function-word-only queries return nothing. Exact id/name/alias matches are
  unaffected. Found by the black-box sandbox lab
  (`I:\Formulation\example\symkit-mcp-test-index`), which also closed the
  test gap: the existing stopword test exercised `FormulaLibrary.search`, not
  the path the MCP tool uses.

## [1.5.2] - 2026-09-11

Patch release with no behaviour change: the `@mcp.tool` docstrings are the only
text a client renders in its tool list, so they are user-facing copy, and they
were written in a decorated style a caller cannot use.

### Changed

- **Tool descriptions rewritten.** Emoji and decorative separator banners
  removed, prose tightened. The codegen tools no longer instruct callers to use
  `SymPy-MCP` / `print_latex_expression()` — neither exists in this project;
  they now name `math` and `session_verify_step` / `session_verify_session`.
  `formula_search` no longer implies it only searches locally: `source="local"`
  (the default) is offline, other sources query Wikidata / SciPy constants /
  BioModels. Semantic marks (check/cross) stay in tool *output* and reports,
  where they carry meaning.

### Fixed

- Documentation counts corrected to the live registry (44 tools, 32 operations)
  in `AGENTS.md`, `CLAUDE.md`, `.github/copilot-instructions.md` and
  `docs/symkit-vs-sympy-mcp.md`; they had drifted to 41/43 tools, `~25`
  operations, and a `v1.0.1` version stamp.

## [1.5.1] - 2026-09-11

Generalization pass over the assumption subsystem, driven by the last black-box
round (run-024). Rather than patch the single reported bug, the three invariants
that all five previous incarnations of the "assumption symbol mismatch" family
had violated were restored as architecture, and guarded by tests that fail on
the shape of the code.

The invariants: **I1** assumptions never influence parsing; **I2** verification
never re-parses a display string; **I3** one implementation of assumption
binding, with the session's `AssumptionEngine` as the source of truth.

### Fixed

- **CRITICAL: assumptions rewrote function calls into products** (run-024).
  An assumption on `k` made `k(x)` parse as `k*x` on the engine path, because
  assumption symbols were injected into the parser's `local_dict` before
  parsing and overrode the `Function` binding for the call site. `k(x)`,
  `v(t)`, `p(T)` and every other call site now survive any assumption set, on
  every entry point.
- **Verification mis-reported reserved-name results as FAILED.** Solving
  `x**2 + 1 = 0` gave `Eq(x, I)` and was flagged FAILED with residual
  `I**2 + 1`: the verifier re-parsed the display string `"Eq(x, I)"`, which
  yields `Symbol('I')` (the parser protects `E`/`I` as user variables, 1.5.0),
  while the archived object holds the imaginary unit. The same class of bug hit
  LaTeX-derived symbols such as `Symbol('mu_{t}')`, which are not valid Python
  at all. Verification now replays the archived `srepr`; display strings are
  only a fallback for records written before srepr archiving existed.
- **`laplacian` returned a silently wrong value under assumptions.**
  `laplacian(x**2 + y**2 + z**2)` returned 4 with `x` positive and 2 with
  `x, y` positive instead of 6 — a bare `Symbol('x')` subs key never matched
  the assumption-bearing coordinate.
- **`laplace` / `fourier` transforms returned silently wrong results under
  assumptions.** With `t` positive, `laplace(exp(-k*t))` returned
  `exp(-k*t)/s` instead of `1/(k+s)`; with `x` positive, `fourier(exp(-x**2))`
  returned `FourierTransform(1, x, k)*exp(-x**2)` instead of the Gaussian. The
  transform variable was a plain Symbol while the integrand held the
  assumption-bearing one, so SymPy treated the integrand as constant.
- **`dsolve` failed outright when the independent variable carried an
  assumption** (`t` positive → "is not a solvable differential equation in
  v(t)").
- **`assume_for_step` and domain defaults never reached `math()`.** They were
  written to the session's `AssumptionEngine` and then ignored, because `math()`
  read only `MathContext`: `assume_for_step("k positive")` followed by
  `math("simplify", "sqrt(k**2)")` returned `sqrt(k**2)`, and a thermodynamics
  session did not make `T` positive. The effective assumption set is now the
  engine's merged view (domain < global < session < step) with the explicit
  context on top, and a stronger layer replaces a symbol's property set instead
  of unioning with it.
- **A correct one-sided limit was reported INCONCLUSIVE**, and an infinite limit
  could never verify at all. The verifier probed both sides of the point (so
  the other side always disagreed), and the tolerance comparison degenerates for
  infinities (`inf < inf` is False). The direction is now archived on the step
  and only the requested side is probed; infinite limits are checked by
  magnitude growth and sign.
- **`dsolve` with a non-matching `variable` surfaced SymPy's raw "is not a
  solvable differential equation in u(t)"**, which reads as if the equation were
  unsolvable. It now names the dependent function actually present and suggests
  the right `variable=` value.
- **A limit that needs sign information failed with a bare SymPy
  "Result depends on the sign of ..."** — informative about the symbols, silent
  about the remedy. It now points at `assumptions=[...]` / `assume_for_step()`.
- **A correct `simplify` step was reported FAILED when its input was an
  unevaluated derivative**, and the whole chain then read `overall: failed`.
  `simplify(Derivative(tanh(x**4), x))` yields the evaluated derivative, but
  `simplify(Derivative(...) - <evaluated>)` does not reduce to zero — SymPy
  evaluates the `Derivative` and then fails to apply the trig identity to what
  is left, so an identically zero residual looked like a changed value. The
  equality check now evaluates pending operations first. (Found by the 1.5.1
  black-box acceptance run; pre-existing, not a 1.5.1 regression.)
- **Substitution with a comma inside a value was reported INCONCLUSIVE.** The
  step archived the mapping as a comma-joined display string
  (`"L_fw = (1 + c_w3**6)**Rational(1,6)"`) and the verifier split it on `","`,
  fragmenting the value and producing a false "Could not parse replacement
  expression" — while the substitution had in fact been applied correctly. The
  mapping is now also archived as JSON and the verifier reads that first; the
  string form remains as a fallback for older records. Any comma-bearing value
  was affected: `Rational(1,6)`, `Eq(a, b)`, multi-argument calls. (Found by
  the 1.5.1 black-box acceptance run; pre-existing.)

### Changed

- `DerivationStep` gains `input_srepr`; legacy session JSON loads unchanged and
  falls back to string parsing.

### Added

- `symkit.domain.assumption_binding` — the single implementation of
  assumption-to-symbol binding (`resolve_assumed_symbol`, `apply_assumptions`),
  owning the property whitelist and conflict table that were previously
  duplicated in `step_verifier` and `assumption_engine`.
- `symkit.domain.expr_io.safe_load_expression` — srepr-first reconstruction of
  archived expressions, shared by the verifier and session replay.
- Structural regression guards: an AST scan forbidding hand-built
  assumption-bearing `Symbol(...)` outside the shared constructor, a
  function-notation matrix across entry points, a sweep over every reserved name
  asserting a call site is never rebound, and a reserved-name round-trip matrix
  through save/load/replay.

### Verification

- 478 tests (was 398).
- 405-cell sweep (45 inputs × 9 assumption sets across all 32 operations)
  against a pre-change worktree: exactly 16 cells changed, all of them the
  correctness fixes above; the `_parse_ode` parser-stack consolidation is
  behaviour-neutral.
- Session-mode sweeps (405 cells each): domain defaults changed 0 cells;
  step assumptions changed 23 cells, every one a case where the per-call
  assumption does not mention the affected symbol — the intended effect, with
  no case where an explicit per-call assumption lost.
- 20-case verification-verdict sweep: per-step status and verdict identical
  before and after archiving `input_srepr` for engine operations.

## [1.5.0] - 2026-09-10

Sixteen defects found by black-box rounds run-020/run-021 (deep-water tasks: Laplace-transform chains, series/limits, the simplification family, assumption toggles, cantilever beam, matrix ops; and meta-tools: symbol registry, assumption-engine layers, derive() recommender, formula-library ecology, rollback branches, error resilience). Two were CRITICAL: a *verified* but semantically wrong beam solution caused by E/I constant capture, and `assume_for_step` being entirely uncallable through the real MCP schema.

### Breaking-ish

- **`E` and `I` now parse as symbols**, not Euler's number / the imaginary unit. In a formula-derivation tool they are overwhelmingly variables (Young's modulus, moment of inertia, energy, current); the old behavior let a beam ODE solve with `E*I → e*i` and pass verification. Use `exp(1)` / `1j` for the constants.
- **`assume_for_step` signature changed** from variadic `*args` (which no MCP client could actually call) to `args: str | list[str]` — e.g. `assume_for_step("x positive y real")`.

### Added

- 🧹 **`formula_remove` tool** — deletes user-overlay and session-derived formulas (read-only seeds untouched), giving the library a cleanup path for polluted entries.
- 🧭 **derive() sees the live library** — `formula_add` entries are immediately recommendable (previously invisible until server restart), and session-derived candidates whose variables are disjoint from the goal targets are vetoed (junk auto-saves with misleading names can no longer ride keyword overlap into recommendations).
- 🔀 **True bidirectional limits** — `direction="+-"` computes both one-sided limits and fails loud when they disagree; SymPy's no-dir default was silently right-handed (`1/x` at 0 "succeeded" with `oo`).
- 📐 **dsolve accepts Leibniz notation of any order** — `d^4w/dx^4` works; mismatched orders are rejected loudly; the notation hint no longer misreports order-4 as unsupported.
- 🔍 **solve infers the variable** when the expression has exactly one free symbol, and lists the candidates otherwise.

### Fixed

- **eigenvects records a session step** and renders LaTeX (it returned `_result_obj=None`, leaving an invisible step and an empty `$$$$` display).
- **check_symbol_conflicts checks user/session registrations**, not just symbols already in expressions (`symbols_checked: 0` blindness).
- **Unknown domains are preserved verbatim** (with an explicit warning) instead of silently degrading to `general`.
- **Ghost variable `s`** from English possessives ("Hooke's law") no longer pollutes goal target variables.
- **parse() accepts matrix literals** (`[[a,b],[c,d]]`), matching the matrix ops' input convention.
- **Parse errors are sanitized** — no more raw `('unexpected EOF in multi-line statement', (1, 0))` arg tuples.
- **resume → complete no longer overwrites** the earlier saved record; a new `-v2` id is minted with a warning when the expression differs.
- **tool_categories is built live** from the tool registry; the static map had drifted (12 registered tools missing, 3 phantom tools).
- `assume()` echoes `assumptions_applied`; `generate_sympy_script` declares `E`/`I` symbols.

## [1.4.0] - 2026-09-10

Eight defects found by black-box rounds run-017/run-018 (gravitational-field + inertia-tensor and SHM + codegen tasks driven by subagents — the first black-box coverage of vector calculus, matrix ops, rollback, `derive()`, and the code generators).

### Added

- 🧭 **solve accepts systems** — a comma-separated expression (e.g. `"x + y - 2, x - y"`) with comma-separated variables solves as a system; previously it crashed with a cryptic `'tuple' object has no attribute 'has'`.
- 🧮 **dsolve ics accepts derivative initial values** — `{"x'(0)": "v_0"}` (one prime per order) alongside `{"x(0)": "x_0"}`; second-order IVPs no longer need a 9-call manual workaround.
- 📜 **generate_sympy_script declares symbols from operations** — solve/diff/integrate inputs routinely introduce symbols absent from the expressions; generated scripts no longer die with `NameError` on first run, and single-argument `Eq()` (deprecated) is no longer emitted for inputs without `=`.
- 🔢 **eigenvals records a session step** and renders LaTeX (previously an empty `$$$$` display and an invisible step).

### Fixed

- 🚨 **gradient no longer returns the zero vector for every input** — coordinate substitution matched bare Symbols against assumption-bearing parsed symbols and silently no-opped, so the field never depended on the basis coordinates (run-017; 4th incarnation of the assumption-mismatch class). Coordinates are matched by name; divergence/curl zeros are now real (a non-zero control `div(x*y, z*x, y*z) = 2*y` is pinned by test).
- 🧮 **dsolve applies context assumptions** — with k, m positive, `m*x'' + k*x` solves to the trig form instead of complex-root exponentials.
- 🛡️ **Tuple guards** — comma parses (python tuples) can no longer poison a session: `session_record_step` rejects them fail-loud, and session_show's risk/suggestion builders plus the domain-level expression loader degrade gracefully instead of crashing with `'tuple' object has no attribute 'free_symbols'`.
- ➗ **divergence results are simplified** — the radial field rendered three unsimplified r^(5/2) terms instead of 0.

Assumption-scope reform motivated by run-013 (per-call assumptions leaked permanently into the shared context even for `session=false` probe calls) and the design discussion that followed.

### Added

- 🧹 **`unassume(variables)`** — remove assumptions for named symbols from the shared context and the session engine (domain defaults preserved). `assume()` was previously irreversible short of a server restart.
- 🧹 **`clear_assumptions()`** — reset the whole scope (context + session engine layers), domain defaults preserved.
- 📣 **`assumptions_applied` echo** — `math()` responses list which assumptions took effect for the call.

### Changed

- ⚖️ **Per-call assumptions respect the `session` flag** — with `session=true` they persist into the shared context AND the session's assumption engine (visible to the step verifier, so identities recorded under session assumptions verify instead of staying inconclusive); with `session=false` they apply to that call only via a call-local context and the shared context is untouched — stateless calls are now truly side-effect free. Cross-session globals remain the explicit `assume()` tool's job. **Migration note:** code that seeded the context with `math(..., assumptions=[...], session=false)` must call `assume()` (or pass `session=true`) instead.

### Fixed

- ✅ **Parse-collapsed boolean steps verify** — when session assumptions make the parser resolve `Eq(...)` to a boolean before recording, a same-value boolean step verifies instead of landing in an unverifiable inconclusive limbo.

## [1.3.0] - 2026-09-10

Assumption-scope reform motivated by run-013 (per-call assumptions leaked permanently into the shared context even for `session=false` probe calls) and the design discussion that followed.

## [1.2.2] - 2026-09-10

Nine defects found by black-box rounds run-011/run-012 (Maxwell-Boltzmann and RC/RLC circuit tasks driven by subagents) and accepted by run-013/014/015 re-runs.

### Added

- 🧮 **dsolve understands Leibniz notation** — `dV/dt` and `d^2x/dt^2` parse into real `Derivative` terms alongside `diff(V,t)`.
- 🎯 **dsolve accepts `ics`** — initial conditions like `{"V(0)": "V_0"}` are forwarded to `sympy.dsolve`, eliminating the 3-call manual constant-solving workaround.
- 🔀 **`list_assumptions` accepts `"merged"`** as an alias for the default merged view.

### Fixed

- 🚨 **dsolve rejects non-ODE input loudly** — `R*C*dV/dt + V` used to parse `dV`/`dt` as plain symbols and return an algebraic rearrangement disguised as an ODE solution; input without any derivative of the dependent variable now fails with a notation hint.
- 💾 **Save selection is goal- and lineage-aware** — `session_complete(auto_save=true)` picks the last symbolic step involving a goal target variable (including hand-recorded binding steps like `Eq(v_rms, ...)`), else the last output in the derivation's symbol lineage; tangential probes (`exp(x)` limit probes, `omega` side-quests) no longer get saved under the derivation's name.
- 🔍 **Definite integrals verify by numeric quadrature** — the reverse-differentiation check false-FAILED correct definite results (d/dx of a constant is 0); bounds are read from the recorded command, parameters are prime-valued, and quadrature disagreement yields INCONCLUSIVE rather than a false FAILED.
- ➕ **solve promotes the positive root** — the `solution` field prefers a provably positive root under active assumptions instead of blindly taking `solutions[0]`; `all_solutions` keeps the full set.
- 📈 **series keeps the `O(x**n)` term** instead of silently reporting a bare polynomial as if exact.
- 🧾 **Scalar strings coerce to lists** — `limitations="..."`, `tags="..."`, `assumptions="..."`, `target_variables="..."`, `related_variables="..."` no longer fail schema validation or splat into characters.

## [1.2.1] - 2026-09-10

Four defects found by black-box round run-008 (damped-oscillator task) and accepted by run-010 probe: all four fixes verified from the black box.

### Fixed

- 🔢 **`evalf` substitution works under context assumptions** — substitution keys are rebound by name to the assumption-bearing symbols actually present in the parsed expression, instead of silently no-opping when earlier calls installed positive assumptions.
- 💾 **Derived-formula saver stores the representative symbolic output** — `session_complete(auto_save=true)` no longer saves a trailing numeric check (evalf float or residual `0`); the last symbolic step output is saved, `variables` metadata is backfilled, and the response reports `saved_expression`.
- ✅ **Boolean `simplify` outputs record cleanly** — `simplify(Eq(...))` resolving to a plain Python `True` no longer crashes step verification (`Add - bool` TypeError silently dropped the step); identities are verified when the verifier can confirm them, otherwise INCONCLUSIVE.
- 🎯 **Goal extraction ignores apostrophes** — prose primes like `x''(t)` are no longer mistaken for single-quoted expressions (junk targets such as `(t) + c x` no longer poison progress matching); double-quoted targets still extract.

## [1.2.0] - 2026-09-10

Structural fixes from the framework-design review of black-box regression rounds run-005/006/007: unknown function calls can no longer degrade to implicit multiplication, recorded steps are the same SymPy objects returned to the client, the derived-formula read/write schema is pinned by contract tests, ignored parameters warn instead of disappearing, and session verification grades outcomes instead of all-or-nothing.

### Added

- 🧩 **solve returns a bare solution** — `solution` / `solution_latex` fields carry the isolated right-hand side alongside the `Eq(v, ...)` expression, so agents no longer hand-strip the wrapper (and corrupt parentheses doing so).
- 🎯 **`session_start` / `session_set_goal` accept `target_variables`** — explicit override for the heuristic goal-text variable extraction.
- 🔢 **`evalf` accepts `substitution`** — substitute symbols and numerically evaluate in one call.
- ✅ **dsolve / limit / evalf steps are auto-verified** — via `checkodesol`, numeric probe points, and numeric re-evaluation respectively.

### Fixed

- 🚨 **Parser red line: `v(t)` stays a function call** — unknown `name(...)` call sites parse as undefined SymPy Functions (Mathematica convention) instead of silently degrading to implicit multiplication (`v*t`); `Integer * Integer**-1` factor pairs fold into exact rationals inside any product, so `1/2*rho*...` round-trips stably through the parser.
- 📼 **Recorded steps are the returned objects** — zero-reparse recording: the session archive is built from the live SymPy object, so archive and response can no longer diverge on function notation, assumptions, or unevaluated forms.
- 📖 **Derived formulas are readable by the library** — writer (`DerivationResult`) and reader (`FormulaEntry`) agree on `sympy_str` / `expression` / `latex` keys, pinned by contract tests; legacy expression-only YAML still loads.
- ⚠️ **Ignored parameters warn** — a per-operation parameter audit table flags caller-set params the operation does not consume (e.g. `point` on `simplify`); two-word assumptions (`"x positive"`) are accepted alongside `"x is positive"`, and malformed clauses warn instead of being silently dropped.
- 🔥 **Engine errors propagate** — 14 previously-silent `except` sites now surface `{ExceptionType}: {message}` in the tool's failure message.
- 📊 **Verification is graded** — a chain is `verified` when nothing failed and at least one substantive step verified; inconclusive steps (notes, ops without an automatic checker) lower confidence but no longer poison the chain; `generate_derivation_report` always renders the failed/inconclusive counts and LaTeX-renders `given` symbol keys.
- 🧭 **Goal tracking sees the whole history** — "solve for X" is satisfied when ANY step output isolates X, so a later `evalf` no longer false-reports "Not yet solved".

### Changed

- 🧱 **`math()` internals split into `tools/_math_dispatch.py`** (operation dispatch, parsing, parameter audit); `tools/math.py` is now a thin recording wrapper.

## [1.1.0] - 2026-09-10

Validated end-to-end by a black-box regression harness (headless MCP client, byte-identical task inputs, artifacts isolated via `SYMKIT_DATA_DIR`): verification false-failures dropped from 15 to 0, generated reports retain all step formulas, fractional exponents parse as exact rationals, and no cross-run formula contamination was observed.

### Fixed

- 🧭 **Session verification no longer false-fails substitute steps** — the verifier now builds assumption-aware target symbols, so substitution actually matches the input symbols; purely numeric residuals are compared with a 1e-9 tolerance instead of exact equality (machine-epsilon differences no longer flip correct steps to FAILED).
- ➗ **Numeric divisions are normalized during parsing** — `x**(1/6)` no longer keeps an unevaluated `Mul(1, 1/6)` exponent, so float bases like `65.0**(1/6)` evaluate numerically; unevaluated `Derivative` semantics are preserved.
- 🧮 **`substitute` folds evaluable unevaluated derivatives** — substituting into a deferred derivative no longer leaves `Derivative(0, x)` behind.
- 🔎 **Derived formulas are searchable** — `formula_search` now includes session-derived formulas (`formulas/derived/`) in its corpus; previously they were only visible to the recommender.
- 📄 **`generate_derivation_report` renders what it is given** — step `latex` is rendered as display math; `verification` accepts int counts (total/verified/failed/inconclusive) plus a text `note` (legacy bools still render as ✅/❌); the Results section emits proper LaTeX instead of raw SymPy source text.
- 🎯 **Goal progress counts variables from all steps** — target variables appearing only in intermediate steps are no longer reported missing; `progress_score` reflects coverage when no explicit target expression is set; multi-letter underscored symbols (e.g. `nu_tilde`) are extracted from goal text.
- 💤 **Persisting no longer flips an ACTIVE session to PAUSED** — `session_start` no longer returns the confusing `status: "paused"` right after creation; `session_complete`'s `auto_save` is documented as gating only the formula-library write (the session JSON is always persisted).
- 🧷 **Pinned `mcp>=1.0.0,<2.0`** — fresh installs no longer crash at startup (mcp 2.x removed `mcp.server.fastmcp`); `serverInfo.version` now reports the symkit package version instead of the MCP SDK version.

### Added

- 🔢 **New `evalf` math operation** — numeric floating-point evaluation, so agents no longer need decimal-exponent workarounds.
- ⚠️ **solve() warns on float coefficients** — solutions from equations containing float coefficients (e.g. `0.5`) carry an explanatory warning pointing to exact fractions (`1/2`) for exact symbolic results.

## [1.0.1] - 2026-07-08

### Changed

- 🐍 **Lowered Python requirement from 3.12+ to 3.10+** to make `pip install symkit-mcp` available on more environments.

### Fixed

- 🔢 **Corrected MCP tool count from 43 to 41** across `README.md`, `README.zh-CN.md`, `ARCHITECTURE.md`, `docs/symkit-design.md`, and `docs/symkit-design.zh-CN.md`.

## [1.0.0] - 2026-07-08

### Changed

- 🏷️ **Project rebranded to SymKit** — a general-purpose symbolic formula derivation engine
  - Renamed packages from `nsforge` / `nsforge_mcp` to `symkit` / `symkit_mcp`
  - Updated `pyproject.toml`, README, and documentation to reflect the new name
  - Project positioning is now domain-agnostic (physics, engineering, chemistry, biology, economics, etc.)
- 🧹 **Repository cleanup for public release**
  - Removed generated cache files (`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`)
  - Removed runtime artifacts (`derivation_sessions/`, `formulas/derived/`)
  - Removed development-only workspace files (`.claude/`, `memory-bank/`, `.vscode/`)
  - Rewrote `.gitignore` in English with broader coverage
- 📝 **Documentation refreshed**
  - Rewrote `README.md` and `README.zh-CN.md` with general-purpose examples and the correct **41-tool** count
  - Updated `ARCHITECTURE.md`, `CLAUDE.md`, and `ROADMAP.md` to match the current tool set
  - Removed outdated references to non-existent tools, skills, and Memory Bank
- 🌐 **Source comments internationalized**
  - All Chinese comments and docstrings in `src/` translated to English
- 📦 **Version bumped to 1.0.0** across `pyproject.toml`, `src/symkit/__init__.py`, and `src/symkit_mcp/__init__.py`; updated `Development Status` classifier to `5 - Production/Stable`.
- 🚀 **Initial PyPI release automation** via `.github/workflows/release.yml` using Trusted Publishing (OIDC): pushes to `main` publish to TestPyPI, and `v*` tags publish to PyPI.

## [0.2.5] - 2026-07-07

### Fixed

- 🐛 **CWD-relative data paths broke after `pip install`** — seed formulas,
  derived formulas, and session JSONs were resolved relative to the current
  working directory, so they vanished or leaked across runs when the server
  was launched from anywhere other than the repo root.
  - Seed formulas now ship read-only inside the wheel under
    `symkit/resources/seed_formulas/` and load via `importlib.resources`.
  - Derived formulas and session JSONs persist in a per-user data directory
    resolved with `platformdirs` (e.g. `~/.local/share/symkit/`,
    `%LOCALAPPDATA%\symkit`). Override with the `SYMKIT_DATA_DIR` env var.
  - Added `src/symkit/domain/paths.py` as the single source of truth for data
    directory resolution.
- 🐛 **Derived-formula data isolation bug** — `DerivationSession.__post_init__`
  instantiated a fresh `DerivationRepository(Path("formulas/derived"))` that
  bypassed the global singleton and the test fixture's temp dir, causing real
  persisted formulas to outscore test candidates. This was the root cause of
  two pre-existing test failures (`test_derive_with_scipy_external_source`,
  `test_derive_includes_external_recommendations`), now fixed. The
  `fresh_session_manager` fixture now resets the repository singleton too.

### Changed

- 🧹 **Removed three unused heavy dependencies** — `matplotlib`, `pint`, and
  `scipy` were declared but never imported at runtime. `scipy_constants.py`
  hardcodes CODATA values as float literals; the "scipy" string remains only as
  a textual source label. `pip install symkit-mcp` is now significantly lighter
  (no more numpy/scipy/matplotlib transitive pull).
- 📦 **Seed formula library moved into the package** — the six seed YAMLs
  (Reynolds number, Navier-Stokes, Euler, continuity, Newton's 2nd law, ideal
  gas law) now live under `src/symkit/resources/seed_formulas/` and ship in the
  wheel. User-added formulas via `formula_add` write to a writable per-user
  overlay that overrides seeds by id; deleting a seed-id removes only the
  override, leaving the read-only seed intact.
- 📝 **Version bumped to 0.2.5** across `pyproject.toml`,
  `src/symkit/__init__.py`, and `src/symkit_mcp/__init__.py`.

## [0.2.4] - 2026-01-21

### Added

- Unified `math()` tool supporting ~25 symbolic operations
- Step-by-step derivation sessions with full CRUD control
- Symbol assumption management
- External formula search (Wikidata, SciPy constants, BioModels)
- Symbol registry for domain-specific notation
- Code/report generation (Python, LaTeX, Markdown, SymPy)
- 43 MCP tools total across math, derivation, assumptions, verification, and orchestration

### Changed

- `pyproject.toml` version synchronized to `0.2.4`
- `src/symkit/__init__.py` and `src/symkit_mcp/__init__.py` versions synchronized to `0.2.4`

### Fixed

- MyPy type errors in `sympy_engine.py` and `services.py`
- Ruff linting issues across the codebase

## [0.2.0] - 2025-12-15

### Added

- Initial derivation framework
- Formula repository with provenance tracking
- Basic MCP server integration

## [0.1.0] - 2025-12-01

### Added

- Initial project structure
- SymPy engine integration
- Core domain entities and value objects
