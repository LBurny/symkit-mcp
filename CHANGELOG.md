# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

A complex formula/theorem derivation round (`symkit-mcp-test-r17`: 21 cards over
three lanes plus two real-kernel Lean cards) exercised theorem-level derivations —
orthogonal-polynomial generating functions, determinant lemmas, Gamma/Beta
theorems, Laurent and residue work, transform pairs, series asymptotics, Legendre
duality, Euler/Gibbs–Duhem, the virial theorem, quantum commutators,
fluctuation–response, Maxwell to wave, relativity invariants, Lean certification
under side conditions, adversarial claims and an adversarial derivation chain.
The mathematics was overwhelmingly correct; every defect below is in the
reporting, recording or verification layer. Test suite grew 1071 to 1087.

### Fixed

- **A derivation that ends by renaming its variables reported the
  pre-substitution expression.** `representative_expression` built its "lineage"
  from free-symbol overlap, so a closing `substitute` (`x -> y`) shared no name
  with the earlier steps and the walk-back delivered the old answer through both
  reporting exits (`session_show.result_expression` and
  `session_complete.final_expression`) while the persisted `current_expression`
  held the correct one. A step that consumed the previous step's output now
  continues the lineage regardless of symbol names.
- **A superseded exact `0` no longer becomes the final expression.** The r14 rule
  ("an exact zero convergence self-check is the conclusion") returned on the
  *first* zero output, so a mid-derivation residual check hijacked the report of
  everything that followed it — five cards delivered `0`/`0.0` instead of the
  result. A zero is the conclusion only when no later symbolic step supersedes it.
- **A rescaled equation is no longer reported as a failed step.**
  `sympy.simplify` normalizes an equation by moving everything to one side and
  dividing by the leading coefficient (`Eq(2*x, 3*x)` returns `Eq(x, 0)`, which
  flips the sign of `lhs - rhs`); comparing those differences for exact equality
  called the tool's own output "Simplify changes expression value" and dragged the
  session to `overall: failed`. Equation differences are now compared up to a
  nonzero constant factor.
- **An internal operation failure is a tool result, not a protocol error.**
  `math("evalf", "isprime(1681)")` raised `'bool' object has no attribute 'evalf'`
  and `math("simplify", "factorint(1681)")` returned the parsed mapping as if it
  were a response, so the client saw `KeyError: 'success'`. Exceptions are now
  caught and reported as `success: false`, and a parse result that is a mapping is
  rejected with a clear message.
- **An unknown operation is named as such.** `math("sum", ..., variable="k")`
  answered "Parameter 'variable' is not used by operation 'sum'" for an operation
  that does not exist. Unknown operations now reach the dispatcher's own message.
- **The recorded step input is the string the caller submitted.** The `original`
  field held `str(parsed_input)`, so `hermite(3, 0.7)` was archived as `-5.656`,
  `(x+1)*(x-1)` as `(x + 1)*(x - 1*1)` and a residual as `0` — provenance that no
  longer reproduced the submission. Reported by three cards.
- **The "contains division" warning now follows the algebra.** It was a substring
  test on the rendered output, so any fractional coefficient (`4*x**3/3`) raised a
  denominator warning on an expression with no division at all. The warning now
  requires a symbolic denominator.
- **A high-order derivative no longer wedges the server.** The differentiation
  check reverse-integrates the output once per order, and `sympy.integrate` has no
  time limit: `math("diff", "(1 - 2*x*t + t**2)**(-1/2)", variable="t", order=4)`
  returns in 0.02s with `session=False` but blocked every tool for 15+ minutes
  with the default `session=True` — the second integration of the 701-operation
  intermediate never returned (r17 task-01). The check now stops past a size
  budget (`verification_guardrails.INTEGRATION_OPS_CAP`) and reports INCONCLUSIVE;
  the same call returns in 0.47s. The warning checks moved to that module as well,
  keeping the frozen verifier at its recorded size.

### Known issues

- `assumptions=["A noncommutative"]` is accepted, echoed back in
  `assumptions_applied`, and then ignored — symbols stay commutative, so every
  commutator collapses to `0` and `expand((A+B)**2)` returns the commutative
  expansion, both marked verified. Repro: `probe/audit7_noncommutative.py` in the
  r17 lab. Either refuse the property loudly or build
  `Symbol(..., commutative=False)` end to end.

## [1.9.0] - 2026-09-14

### Added

- **`lean_status()` — a read-only Lean environment probe.** Agents kept guessing
  whether the optional Lean backend was installed (listing directories, running
  `lake --version`) and read a missing `Mathlib` top-level directory as "Mathlib
  is not installed", even though Mathlib lives under
  `<data dir>/lean-workspace/.lake/packages/mathlib`. The new tool answers in one
  call: the resolved toolchain / Mathlib / workspace paths, where each was
  resolved from (`ELAN_HOME`, `PATH`, `~/.elan`, `SYMKIT_DATA_DIR`), which layer
  is missing, and the exact next command — named for the running interpreter, so
  it works even when the console script is not on `PATH`. It never runs Lean and
  never downloads. `session_certify`'s unavailable response now points at it.
- Readiness is now judged from the files on disk. `detect_status` additionally
  verifies that Mathlib is fetched and built (manifest entry, package sources,
  and the compiled oleans), so a workspace whose Mathlib was deleted no longer
  reports ready from a leftover stamp. The stamp is advisory only, so a
  workspace copied from another machine stays usable when its stamp is lost.

### Fixed

- **A nonlinear ODE no longer wedges the whole server.** `sympy.dsolve` has no
  internal time limit and does not raise on an unsolvable nonlinear ODE — it
  spins. Because the MCP server is one process, a single `math` call on the
  nonlinear pendulum (`theta'' + (g/l) sin(theta) = 0`) blocked every other tool
  for 30+ minutes (reproduced by the `symkit-mcp-test-leanstatus` round). A
  narrow up-front screen now refuses the reliably non-terminating class — a
  dependent function under a transcendental (`sin(theta(t))`, `exp(y(t))`) — with
  an actionable message in 0.02s, while linear and separable ODEs still solve.
- **`factor` results are no longer flagged as suspect identities.** Factoring a
  nonzero expression (`factor(c^2*S - b^2*S)` → `-(b-c)*(b+c)*S`) is the answer,
  not a failed identity claim, yet it carried `suspect_identity: "unreduced"`
  ("the difference did not reduce to zero") and surfaced as a session warning.
  The `factor` operation is now exempt from that grading; `simplify`/`expand`
  keep it unchanged. Found by the `symkit-mcp-test-leanstatus` round.
- **Every Lean hint now names the same setup command.** The `reason` strings
  embedded a bare `symkit-lean-setup` while `lean_status.next_step` and
  `session_certify.setup` named a module invocation with the running
  interpreter — three surfaces, two answers, so a caller had to choose. The
  hint is now derived from one public `lean_toolchain.setup_command()`, and
  regression tests plus the lab probe assert the three agree. Found by the
  `symkit-mcp-test-leanstatus` round.
- **`lean_status.missing` speaks the report's vocabulary.** It listed `"lake"`
  while the sibling field is `toolchain`; the entry is now `"lake_binary"`
  (no `lake` found at all, as distinct from `toolchain`: a lake exists whose
  elan home lacks the pinned version).

## [1.8.0] - 2026-09-14

A Lean-certification sandbox round (`symkit-mcp-test-lean`) verified the four
process/report fixes below end to end against the built wheel (all green: the
`trivial` split, the certify-time `assumptions`, the toolchain guard, and the
tree-kill) and found two further defects, both fixed here; it also ships the
`sandbox-experiment` agent skill (six-step black-box round playbook). Its
deterministic probes and two operator cards are the acceptance evidence; the
"substitute steps are skipped" complaint was re-confirmed as design-as-intended.
Test suite grew 1041 → 1055.

A fourth 2026-09-14 report (a real Lean-certified SST derivation) was
re-verified against the source: three process/environment defects and two
report-semantics defects were confirmed and fixed here; the "substitute steps
are skipped" complaint is design-as-intended (only ring/field algebraic
rewrites are certifiable, documented in the README), and the matrix
`untranslatable` rows are the lane correctly reporting a real coverage
boundary. Test suite grew 1041 → 1053.

Fixes from the r16 black-box sandbox round (20 task cards; findings in the
`symkit-mcp-test-r16` lab). Test suite grew 956 → 997.

Fixes from the 2026-09-14 maintainer verification round: nine defects reported
from a real SST k-omega derivation session were re-verified against the source
before fixing; six were confirmed and fixed here, two turned out to be
message-semantics misreadings (the suspect messages are factually accurate),
and one schema claim did not reproduce. A follow-up turbine-session report
re-verified six more claims the same way: four were artifacts of the pre-fix
code, one was a downstream symptom of the content loss, and the remaining live
bug (the target warning) is fixed here. Test suite grew 997 → 1031.

A third 2026-09-14 turbine report (two sessions, 99 recorded steps) was
re-verified the same way: two P1 defects are real and fixed here (the
auto-save probe pollution below, and a verifier false FAILED caused by
one-ULP float drift), the "aggregation misleads" complaint traced to that
false failure plus a misreading of the suspect/inconclusive semantics, and
the remaining minor items are design-as-intended (search AND semantics,
domain assumption presets) or SymPy usage traps. Test suite grew 1031 → 1041.

### Added

- **`session_certify` takes certify-time assumptions.** Steps that divide by a
  variable need an explicit nonzero fact; previously the only way to supply one
  was to register it with `assume(...)` and re-run the whole derivation.
  `session_certify(assumptions=...)` now accepts the engine's mapping shape
  (`{"cp": {"nonzero": True}}`), a string (`"cp nonzero x positive"`) or a list
  of alternating pairs, and binds them as Lean hypotheses. Steps that recorded
  their own assumptions keep them.

### Changed

- **Tool descriptions cleaned up.** The `formula_remove` description no longer
  carries an internal run-history note, `show_assumptions` now states that it
  only covers the shared math context (the assumption engine's levels are
  listed by `list_assumptions`), and `formula_search` documents the `scipy`
  source once instead of twice. Stale module docstrings now say `math()`
  covers 33 operations and that `formula.py` is local-library-first.

### Fixed

- **A leading negated term is no longer read as an asserted difference.** The
  verifier's difference-form heuristic matched any sum containing a negated
  compound, so an ordinary expression like `-x**2 + x*(x + 1)` — which
  simplifies correctly to `x` — was treated as an identity claim and the step
  carried a `suspect_identity: unreduced` warning saying its "difference did not
  reduce to zero ... numerically nonzero at tested points". Both assertions were
  false (the residual is identically zero), and `session_verify_session` headlined
  the warning on a correct step. The negated operand now counts only when a
  non-negative term precedes it, and the archived-srepr path skips inputs whose
  recorded text begins with a unary minus on an identifier.
- **Skipped certification steps say why.** A step outside the certified fragment
  (`differentiate`, `integrate`, …) was reported with `certification: skipped`
  and `reason: null`, so a reader could not tell whether the gap was
  intentional; it now names the operation and the eligible set.
- **A cancelled Lean certification no longer leaves an orphan holding the elan
  lock.** The batch checker used `subprocess.run(timeout=...)`, which kills only
  the direct child; `lake` spawns the compiler and, during a toolchain install,
  an elan child that owns `toolchains/<version>.lock`. A timed-out run left both
  alive, and every later Lean call then blocked forever on
  "waiting for previous installation request to finish". The checker now starts
  the command in its own process group and kills the whole tree on timeout
  (`taskkill /F /T` on Windows, `killpg` on POSIX), so no orphan or stale lock
  survives.
- **`lake` discovery honours `ELAN_HOME` over `PATH`.** `find_lake()` checked
  `PATH` first, so a default `~/.elan/bin/lake` silently shadowed the elan
  install a user pointed at with `ELAN_HOME` — and since `lake` resolves
  toolchains against its own elan home, the first certified step triggered a
  fresh multi-GB toolchain download into the wrong home. `ELAN_HOME` now wins,
  and readiness additionally verifies that the selected `lake` already owns the
  toolchain pinned in the workspace, reporting a directing reason instead of
  starting a surprise download.
- **Trivial certification goals no longer inflate the `proven` count.** A step
  whose input and output are structurally identical (`x = x`, `0 = 0`) was
  translated, proved by `ring`, and counted as `proven` — 11 of the 20 theorems
  in the reported session were tautologies that certified no algebra. Such steps
  are now classified `trivial`, reported with the reason, kept out of `proven`
  (new `summary.trivial`), never sent to the kernel, and get no `details.lean`
  record.
- **The verifier absorbs float-path noise instead of failing correct steps.**
  The substitution check recomputes the recorded substitution and compares it
  with the archived output; the two computation paths can drift a power
  exponent by one ULP (`0.99999999999999989` vs `1.0`), and because the
  residual kept a free symbol, the numeric-zero gate's no-tolerance branch
  flipped a correct step to FAILED with details printing both sides as the
  same string — an otherwise-correct turbine chain was judged `failed`.
  Symbol-bearing residuals are now sampled at assumption-compatible points
  (unevaluated `Derivative`/`Integral`/`Sum` stay unsamplable) with the same
  1e-9 tolerance philosophy before refusal, and substitution failure details
  carry full-precision `srepr` forms so float differences stay visible instead
  of being masked by 15-digit `str` rounding.
- **The math dispatcher rejects unconsumed parameters.** Passing
  `substitution` to `expand`/`simplify` (or any parameter the requested
  operation does not consume) previously only warned while returning a
  plausible-looking result, which read as if the parameter had been applied.
  The call now fails with an error naming the offending parameter.
- **`session_complete` stops warning about a target that was never set.** A
  text-only goal (no target expression, no target variables, and the default
  `derive_expression` form) can never match anything, so the "Current
  expression does not match the derivation target" warning fired
  unconditionally. It now appears only when the goal defines a checkable
  target (`DerivationGoal.has_explicit_target()`).
- **`session_complete` no longer saves a bare constant as the derived
  formula.** A trailing `0` self-check still headlines `final_expression`
  (r14 task-08 display semantics). An earlier draft of this fix preferred the
  last symbolic derivation output; a second turbine round showed that output
  is typically a verification *probe* (two sessions, two probe pollutions), so
  the library write is now skipped entirely whenever the outcome is a bare
  constant, with a warning pointing at `formula_add`. A multi-step derivation
  can no longer land in the library as `expression: '0'` with `variables: {}`.
- **The library `verified` label now requires no unreduced differences.** When
  the verification summary lists `suspect_identity_steps`, the formula is
  saved with `verified: false` and the response names the flagged steps; the
  graded chain-level `overall` semantics are unchanged. A 16-step chain with 3
  suspect and 1 inconclusive step can no longer publish `verified: true`.
- **Lowercase `max`/`min` evaluate numerically.** The parser rewrites them to
  SymPy's auto-evaluating `Max`/`Min`, so `evalf("max(0.1, 0.05)")` returns
  `0.1` and SST-style F1/F2 mixing-function identities become numerically
  verifiable instead of freezing on `Function('max')`.
- **A name used both bare and as a call site parses.** `1/z + z(x)` — and the
  turbomachinery workhorses `k`/`k(x)`, `omega`/`omega(x)` — no longer dies
  with an unhelpful `SympifyError: z`: call sites are renamed internally to
  `<name>__call` bound to `Function('<name>')`, the bare occurrence keeps its
  plain `Symbol`, and per-call assumptions attach to the symbol rather than
  being dropped because a call site exists.
- **`evalf` of a symbolic input is verifiable.** The verifier compares
  `N(input)` with the recorded output symbolically instead of answering
  INCONCLUSIVE for the same step the tool reported as a success; mismatches
  stay INCONCLUSIVE, so float form noise cannot produce a false FAILED.
- **Flat list literals are matrices.** `[1/1.168, 2+2]` parses to a column
  `Matrix` exactly like the list-of-lists grid already did (run-020), instead
  of reaching the execution layer and crashing with
  `'list' object has no attribute 'evalf'/'replace'`.
- **`assume` accepts the clause-list form.** `assume(["x is positive"])` now
  works alongside the dict form, aligning the three assumption entry points
  (`assume`, `math(assumptions=[...])`, `assume_for_step`); an unparsable
  clause rejects the whole batch up-front with a clear error.

- **Verifier stops accusing honest computations of being false identities.**
  A plain expression that merely looks like a difference (`E²−p²c²`, an AM-GM
  expansion) is no longer treated as a zero-assertion: only steps whose input
  is an explicit equation get the numeric TRUE/FALSE refutation, and a
  difference containing an unevaluated `Sum`/`Integral` is never refuted by
  substitution. Non-asserted difference forms get a neutral
  `suspect_identity: "unreduced"` hint that tells the caller to record an
  equation for a definitive verdict. (r16 tasks 01/08/19/20)
- **Hand-recorded equations get a numeric gate and a trig fallback.** When the
  symbolic difference of a recorded `Eq` does not reduce, the verifier now
  tries `expand(trig=True)`/`trigsimp` and then a rational-point residual:
  numerically zero → `inconclusive` ("unproven, not disproven"), genuinely
  nonzero → `failed`. The true identity `cos(6x) = 32cos⁶x − 48cos⁴x + 18cos²x − 1`
  is no longer declared "not an identity" because `simplify` alone cannot
  reduce it. (r16 task 17)
- **Definite-integral results are no longer false-failed** by the
  differentiation reverse-check (a constant antiderivative differentiates to
  0 ≠ integrand). A definite-bounds `Integral` whose output lacks the bound
  variable is checked numerically or left `inconclusive` instead. The
  `erfi` reverse-check also no longer treats a recorded variable of `None`
  as the literal symbol `None`. (r16 tasks 06/19)
- **`evalf` on large finite sums is exact and cancellation-aware.**
  `Sum((-1)**n/n, (n,1,2000))` returned `−0.7 + 0.09i` (naive double
  summation with a phantom imaginary part); finite sums now evaluate exactly
  first at ≥30-digit precision, double the precision and warn when
  catastrophic cancellation is detected. The evalf verification baseline was
  aligned to the same exact path. (r16 task 19)
- **`session_explain`/`session_complete` no longer crash** with
  `'tuple' object has no attribute 'free_symbols'` when the session contains
  a system-`solve` (list-input) step; tuple/list solution objects are
  unwrapped at every consumer. (r16 task 20)
- **Assumptions are scoped to the session.** `assume` no longer leaks across
  sessions into unrelated solves, and Lean certification binds hypotheses
  from the step's own record instead of the global pool (ring identities no
  longer inherit an unrelated `x ≠ 0` binder). (r16 task 20/15)
- **Lean field lane falls back to a ring proof with meaningful binders.** An
  unproven field statement is retried as its cleared polynomial identity
  (structure preserved, never collapsed to `0 = 0`) with the denominator
  factors bound nonzero; the retry reports lane `field+ring`. The
  untranslatable reason now lists *all* denominator factors missing an
  assumption, not just the first. (r16 task 15)
- **Nested `integrate(integrate(...))` calls no longer return the correct
  value times a spurious `x`.** When the input already contains inline
  integral calls and no outer limits are given, the parsed (already fully
  evaluated) value is returned instead of differentiating once more in the
  default variable. (r16 acceptance, task 06)
- **System solve respects assumptions and announces headline truncation.**
  Tuple solutions violating active assumptions are filtered into
  `filtered_by_assumptions` (consistent with scalar solve), and multi-solution
  results warn that the headline `solution` shows the first of N. (r16 tasks
  07/10/20)
- **Oversized explicit sums are rejected up front.** Parsing an expression
  with more than 1000 explicit additive terms fails with guidance toward
  `Sum(1/k, (k,1,n))`/`harmonic(n)`, instead of wedging the server for
  30+ minutes / gigabytes on exact-rational denominators (observed with a
  term-by-term H_n at n = 10⁶). (r16 task 05 incident)
- **Session provenance:** `dimension` calls now record steps; `parse`/`cancel`
  are no longer mislabelled `load_formula`/`simplify` in the step's top-level
  operation; `evalf` substitutions are recorded as `input_substitution` so
  numeric anchors are reproducible from the log. (r16 tasks 03/15/16)

## [1.7.0] - 2026-09-14

### Added

- **Dimensional analysis in `math()` and the verification chain.** New
  `math("dimension", expr, units={...})` operation (32 → 33 operations) reports
  `consistent` / `dimensionless` / `dimensions` / `issues`; with no unit
  information it returns `consistent: null` instead of guessing. The response
  also carries `result_dimension`, the net dimension of the whole expression
  (e.g. `R*C` → `{time: 1}`), so "is this a time?" is answered directly. Unit
  sources, strongest first: explicit `units`, units declared on loaded-formula
  variables, then `register_symbol(unit=...)` defaults. `session_verify_step`
  and `session_verify_session` now run the check automatically whenever the
  session has unit information — a step with a definite mismatch becomes
  `failed` — while unit-free sessions keep their previous behaviour.
  `tool_recommend` routes "dimension"/"量纲"/"unit" to the new operation (the
  branch previously sat behind "check" and was unreachable).

- **Formula write-path governance.** `formula_add` now requires every variable
  to carry a non-empty `unit`, with `"-"` as the explicit dimensionless/unknown
  sentinel (a missing or empty unit is rejected instead of silently written);
  unparseable unit strings only warn and are stored verbatim. `formula_add` and
  `session_complete(auto_save=True)` now return `similar_to` when the library
  already holds a structurally or textually similar formula (alpha-invariant
  fingerprint first, FTS fallback second), so duplicate Bernoulli-style entries
  surface at write time. Auto-save backfills variable units from the session
  unit context (`register_symbol` defaults + loaded-formula variables) instead
  of writing empty strings. `formula_promote` persists `curated: true`,
  `formula_get` exposes the `curated` flag, and `formula_stats` reports
  alpha-invariant `structural_duplicate_groups` alongside content-hash
  `duplicate_groups`. (`verified` still means the step verifier ran; `curated`
  means an explicit human promotion.)

- **Optional Lean 4 kernel certification.** A new `session_certify` tool
  (Verification category; tool count 44 → 45) re-proves the algebraic-equality
  (`simplify`/`expand`/`factor`/`combine` inside the rational fragment) with
  the Lean 4 + Mathlib kernel (`ring`/`field_simp`) and attaches the outcome
  to each step's verification record under `details.lean`. Existing verdicts
  are never modified and `unproven` never means "wrong"; disagreements with
  the heuristic verifier are surfaced as `discrepancies`. The lane ships with
  zero new Python dependencies and degrades gracefully: without a toolchain
  every tool behaves exactly as before, and `symkit-lean-setup` performs the
  one-time elan + toolchain + Mathlib install into a managed workspace under
  the user data dir. Variable denominators require an explicit
  `nonzero`/`positive` assumption, so side conditions become checkable rather
  than implicit. `scripts/lean_oracle.py` re-runs the lane over persisted
  sessions and reports verifier disagreements (exit 1 on a likely StepVerifier
  false negative).

### Changed

- **Tool taxonomy reorganized.** All tools now carry a
  `meta={"category": ...}` label from a fixed set of nine categories (Unified
  Math, Assumptions, Verification, Symbol Semantics, Formula Library, Session
  Management, Output, High-Level Orchestration, Meta). Previously 18 tools had
  no category and appeared under an undescribed "Other"; `formula_search` sat
  outside the "Formula Search" category that only held `formula_remove`;
  `assume` / `show_assumptions` were mislabelled as Unified Math; and the
  verification tools were mixed into Session Management. `tool_categories` now
  reads its descriptions from a module-level table covering every category.

### Removed

- **BREAKING: the four `generate_*` tools are replaced by one `generate_output`
  tool.** `generate_python_function`, `generate_latex_derivation`,
  `generate_derivation_report`, and `generate_sympy_script` are removed — they
  were four output formats of the same operation, and choosing among them was
  needless model overhead. Call `generate_output(format=..., ...)` with
  `format` set to `"markdown_report"`, `"latex"`, `"python"`, or
  `"sympy_script"`. The old tools' parameters are flattened into optional
  arguments; the selected format's required parameters must be supplied, and a
  missing one returns `{"success": false, "error": ...}` naming it rather than
  raising. For the same inputs the artifact is byte-for-byte identical to the
  old tool's output. Tool count drops from 47 to 44; the `Output` category now
  holds this one tool.

### Fixed

- **Operator-glued search queries recalled nothing.** `formula_search` now
  splits query tokens on non-word characters, so `v*L*rho/mu` recalls the
  spaced `rho * v * L / mu` entry instead of returning zero hits (the trigram
  FTS index cannot index sub-3-character tokens, and the LIKE fallback was
  skipped whenever a long token existed).
- **Exact expression matches could be outranked.** A query that parses as an
  expression now also matches against the alpha-invariant structural
  fingerprint (`structural` match kind, ranked just below an exact id hit),
  so an exactly-matching formula is no longer buried under tier/verified
  boosts.
- **Reserved names broke fingerprint rename-invariance.** `structural_hash`
  now parses via `parse_user_expression`, so formulas using `E`/`I`/`pi` as
  ordinary variables (energy, current, …) fingerprint identically under
  renaming; the index schema version bumps to 4 and rebuilds automatically.
  `content_hash` (staging-id identity) is unchanged.
- **Structural fingerprints were not fully rename-invariant.** The
  alpha-renaming order followed SymPy's name-sorted canonical form, so a
  rename that changed alphabetical ranks (e.g. `rho*v*L/mu` →
  `q1*q2*q3/q4`) changed the fingerprint and the `similar_to` structural
  channel silently missed renamed clones. Fingerprints are now derived from
  a name-independent structural signature (occurrence-path ordering), so any
  alpha-renaming collides; schema version bumps to 5 and rebuilds on open.
- **Lean setup downloaded elan from a dead URL.** `symkit-lean-setup` pointed
  at `release.lean-lang.org/elan/...` (404). It now fetches the platform's
  `elan-init` archive from the official `leanprover/elan` GitHub releases
  (zip/tar.gz per OS/arch, extracted without path traversal), sends an
  explicit User-Agent (some CDNs reject the urllib default), honors
  `ELAN_HOME` in `find_lake` for portable/CI installs, names the attempted
  URL on download failure, and surfaces the `lean --version` stderr tail
  when version detection fails (e.g. an untrusted TLS root during toolchain
  download) instead of a bare "could not parse". The `session_certify`
  degradation hint now states what the installer does (one-time ~1–2 GB
  download, requires network).
- **Dimensional analysis treated literal zero as dimensionless.** A recorded
  ODE step like `Eq(C*R*v_C'(t) + v_C(t) - V, 0)` was judged dimensionally
  inconsistent because the right side `0` is dimensionless — flipping a
  correct derivation to `failed`. A literal-zero equation side is now
  dimension-polymorphic; genuine mismatches (`v^2 = v0^2 + 2*a*t`) still
  fail.
- **Derivative-aware dimensions.** The dimension checker reduces
  `Derivative` terms (`dim(dF/dt) = dim(F)/dim(t)`), resolves an applied
  function `x(t)` to its symbol's unit, and names the actual blocker when
  inconclusive (derivative vs non-integer exponent) instead of always
  blaming exponents.
- **`curl`/`divergence` silently returned 0 for non-vector input.**
  `math("curl", "F1(x,y,z)*i + F2(x,y,z)*j + F3(x,y,z)*k")` parsed `i/j/k`
  as scalar symbols and returned a zero vector with `success: true`;
  list/Matrix inputs raised raw `AttributeError`/`TypeError`. Non-vector
  input now fails with guidance on the accepted forms (comma-separated
  components, a 3-element list or Matrix, or `N.i/N.j/N.k` notation — which
  also lets `gradient` output feed back into `curl`).
- **`gradient`/`laplacian` ignored their default coordinate set.** Without an
  explicit `variable=`, both operators reused the single-variable default
  (`x`) as their coordinate list, so `math("gradient", "f(x,y,z)")` returned
  only the x-component — `Derivative(f(N.x, y, z), N.x)*N.i` — with `y`/`z`
  left as plain symbols rather than basis coordinates. They now fall back to
  `x, y, z` as documented.
- **The Lean lane's first real-kernel run exposed two header bugs (D12/D13).**
  The setup smoke test proved `(1 : ℝ) + 1 = 2` under only
  `Mathlib.Tactic.Ring`, whose transitive imports carry no Real algebra
  instances, so `symkit-lean-setup` always failed at its final check and could
  never write the readiness stamp. And the certification header (FieldSimp +
  Ring) omitted `Mathlib.Data.Real.Basic`, so every rendered `(x : ℝ)`
  theorem failed `OfNat ℝ n` instance synthesis and steps the heuristic
  verifier had verified came back `lean_unproven`. The smoke now proves two
  ℚ goals under the exact imports the certification lane uses, and the
  certification header imports `Mathlib.Data.Real.Basic`; the first true
  end-to-end kernel certification run proves the algebraic steps
  (`proven: 2`, `discrepancies: []`).
- **A `verified` simplify step no longer implies the asserted identity holds.**
  A poisoned 10-step chain (coefficient/sign/formula errors) received the
  byte-identical `10/10 verified` as the clean chain: the verifier only
  checks that the recorded output equals the recomputed operator result.
  Steps whose recorded input is a difference (`A − B`) and whose output is
  not zero now carry `details.suspect_identity` with an explicit message
  that the asserted identity appears FALSE; neutral verdicts read "output
  matches the recomputed operator result". A lazily-returned `Integral`
  (input ≡ output) is no longer stamped "verified by numeric quadrature" —
  it is inconclusive.
- **Correct steps failed on `Subs` forms.** Re-running `doit()` on an
  already-evaluated `Subs` drops SymPy 1.14's substitution binding, so a
  correct chain-rule step was judged failed and a fully-correct session
  reported `overall: "failed"`. Pending evaluation now skips `doit()` on
  `Subs` and canonicalizes anonymous dummies so equivalent forms cancel.
- **Unregistered symbols no longer inherit domain-default units.** The
  symbol registry's per-domain convenience table (`k` → rate constant 1/h,
  `p` → pascal, …) leaked into the session unit map, so a physically-correct
  `k = π/L` was flagged dimensionally inconsistent. Units now come only from
  explicit `units=`, `register_symbol(unit=...)` and formula variables;
  unknown symbols stay inconclusive instead of being assigned invented
  dimensions.
- **Matrix powers and nested `.inv()` crashed or mis-parsed.** `Matrix**n`
  reached SymPy's assumption system as an unevaluated `Pow` and raised
  "unsupported operand type(s) for +: 'ImmutableDenseMatrix' and 'int'" —
  integer matrix powers are now folded at parse time (negative powers via
  `inv()`, non-square/singular become structured errors). `A.inv()` nested
  in a larger expression crashed the `evaluate=False` transformer
  ("'Attribute' object has no attribute 'id'"); attribute chains now fall
  back to evaluated parsing. `ifourier` degenerated to a constant when the
  input and output variables shared a name; it now falls back to a dual
  variable and errors structurally when the declared variable is absent.
- **`dsolve` silently forged a solution for coupled systems.** `S` is a SymPy
  singleton (`sp.S(t)` evaluates to `t`), so `S(t)` was rewritten to plain
  `t` before dsolve and a plausible-looking but wrong closed form came back
  with `success: true`. Degenerate call names are now bound as undefined
  functions, and an undefined function appearing in the same additive term
  as the dependent variable is rejected as a coupled/underdetermined system
  (additive forcing terms like `f(t)` remain supported). `solve` no longer
  silently drops the zero root filtered away by assumptions and discloses
  assumption-filtered roots via `filtered_by_assumptions`; substitute/`ilaplace`
  results containing `nan`/`zoo` are structured errors naming the
  critical-damping case instead of returning `nan`.
- **A zero-convergence step is now the headline.** `final_expression`,
  `show.result_expression` and `show.latex` picked different steps when the
  chain converged to `0` (the constant was skipped in favour of a symbolic
  intermediate step); an exact zero now wins, so all three sources agree.
  Goal extraction no longer produces phantom target variables — derivative
  tokens (`u_tt`), differential-notation fragments (`d` of `d f/dv`) and
  applied function names are stripped, extraction is narrowed against the
  chain's real free symbols, and `target_reached` becomes true when any
  verified step covers the targets (a final `0` included).
- **Round-15 follow-ups.** `suspect_identity` is graded: a difference that a
  random rational substitution proves nonzero is `"numeric"` ("the asserted
  identity is FALSE"), while a difference the simplifier merely cannot reduce
  (unevaluated `Derivative`, `-E + exp(1)`) is `"unreduced"` ("identity
  unproven, not disproven") — no more false alarms on true identities;
  `session_verify_session`/`session_complete` aggregate
  `suspect_identity_steps` so the signal survives the summary. `limit` now
  `doit()`s embedded derivatives and fails structurally on the
  non-evaluable remainder instead of silently treating them as constants.
  The dimension guard catches inconsistent **products/quotients** of
  mis-declared units (previously only sums were checked; `L/R` with
  `L = henry/second` returned a false green). The Lean lane now passes
  session assumptions into theorems (`x ≠ 0`/`x > 0` binders), supports
  product-form compound denominators with per-factor hypotheses, fixes a
  tactic-indentation bug that made every `field_simp` step unsolvable, and
  emits deterministic, actionable `untranslatable` reasons — the r15
  task-14 chain went from `proven: 0` to **`proven: 3/3`** on the real
  kernel. `evalf` no longer returns spurious imaginary parts on pure real
  integers, and giant-integer results no longer silently drop their step.
- **Manually recorded equations are content-checked.** A custom step whose
  expression is an equation now gets an identity check: sides equal under
  assumptions → verified; differing by a nonzero constant → failed
  ("equation is false"); otherwise inconclusive with the residual shown
  ("not an identity: the sides differ by 2*a*b"), so a mis-stated identity
  is visibly flagged while definitions and model equations stay inconclusive
  rather than failed. Math-operation steps over equation inputs additionally
  record `details.equation_identity`.
- **The headline result no longer quotes a failed step.**
  `session_complete`'s `final_expression` is the last non-failed step; when
  failed tail steps are skipped, the response adds
  `final_expression_skipped_failed: true` with a note naming the step.

## [1.6.2] - 2026-09-12

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

- **The step verifier rejected a correct derivative that lands on a non-zero
  constant.** `_verify_differentiation` decided from "the output has no free
  symbols" and returned `Non-zero derivative of constant` before reverse
  integration ran, so `diff(2*x, x) = 2` — and any higher-order derivative
  reaching a constant — was reported FAILED; five such steps turned a whole
  chain into `overall: failed`. Reverse integration now runs always, repeated
  once per differentiation order, so the check covers both `diff(2*x, x) = 2`
  and `diff(x**2, x, 2) = 2`.
- **Matrix-valued steps could never verify.** `is_numerically_zero` only
  understood scalars: `Matrix == 0` is not a Python truth value and
  `complex(matrix.evalf())` raises, so an `expand`/`simplify` whose difference
  *was* the zero matrix was reported as changing the expression. Matrix
  differences are now checked entrywise, expanding a symbolic matrix expression
  first.
- **`evalf` crashed with a `RecursionError` on `Identity`-bearing matrix
  expressions.** `A*A - c*A + k*Identity(n)` stays a `MatAdd` with the identity
  term unabsorbed and `.evalf()` recurses on it; the uncaught error escaped to
  the tool boundary. Such expressions are now made explicit first, which also
  collapses the term — a true Cayley-Hamilton residual now comes out as the zero
  matrix instead of a crash.
- `session_show` and `session_complete` answered "what did this produce"
  differently: `complete` reports the derivation outcome, `show` still reported
  the raw current expression. `show` now carries `result_expression` /
  `result_latex` with the same value as `final_*`, keeping `latex` / `sympy` for
  the current expression.
- **The step verifier reported a correct substitution as FAILED, and a no-op
  substitution as verified.** A substitution key whose spelling needs evaluation
  (`/2` arrives from the user parser as `Pow(2, -1)`) never matched the archived
  expression, which holds `Rational(1, 2)`; `subs` matches structurally, so the
  reconstructed expectation kept the un-substituted term and the step was
  reported FAILED — dragging `session_verify_session` to `overall: failed` on a
  mathematically correct chain. Keys are now re-evaluated structurally
  (`expr_io.evaluated_form`). Conversely, a substitution whose keys were all
  absent from the expression still said "Substitution verified"; it is now
  INCONCLUSIVE, which also stops it inflating the verified count.
- **`session_complete` reported the last step as the answer.** `final_expression`
  was `str(current_expression)`, so a trailing `evalf` probe — a numeric
  residual, `-1.0`, a constant — became the delivered result. It now reports the
  derivation's outcome (`representative_expression`), falling back to the
  current expression.
- **A note inherited the previous step's output.** `session_add_note` recorded
  the neighbouring step's expression as its own output, so a pure-text note
  looked like it had produced that value (and could be picked up by target
  matching). Notes now carry no output, and rollback/delete walk past
  output-less steps instead of clearing the session's current expression.
- `session_load_formula` silently coerced an unknown `source` label to
  `user_input`, and `session_start` silently swapped an unrecognized `pattern`
  for `direct-manipulation`. Both now warn and echo what was used.
- Matrix steps recorded their operation as the bucket `matrix_op` with no trace
  of the actual call; `input_expressions["operation"]` now keeps the call name.
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

- **`formula_remove` tool** — deletes user-overlay and session-derived formulas (read-only seeds untouched), giving the library a cleanup path for polluted entries.
- **derive() sees the live library** — `formula_add` entries are immediately recommendable (previously invisible until server restart), and session-derived candidates whose variables are disjoint from the goal targets are vetoed (junk auto-saves with misleading names can no longer ride keyword overlap into recommendations).
- **True bidirectional limits** — `direction="+-"` computes both one-sided limits and fails loud when they disagree; SymPy's no-dir default was silently right-handed (`1/x` at 0 "succeeded" with `oo`).
- **dsolve accepts Leibniz notation of any order** — `d^4w/dx^4` works; mismatched orders are rejected loudly; the notation hint no longer misreports order-4 as unsupported.
- **solve infers the variable** when the expression has exactly one free symbol, and lists the candidates otherwise.

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

- **solve accepts systems** — a comma-separated expression (e.g. `"x + y - 2, x - y"`) with comma-separated variables solves as a system; previously it crashed with a cryptic `'tuple' object has no attribute 'has'`.
- **dsolve ics accepts derivative initial values** — `{"x'(0)": "v_0"}` (one prime per order) alongside `{"x(0)": "x_0"}`; second-order IVPs no longer need a 9-call manual workaround.
- **generate_sympy_script declares symbols from operations** — solve/diff/integrate inputs routinely introduce symbols absent from the expressions; generated scripts no longer die with `NameError` on first run, and single-argument `Eq()` (deprecated) is no longer emitted for inputs without `=`.
- **eigenvals records a session step** and renders LaTeX (previously an empty `$$$$` display and an invisible step).

### Fixed

- **gradient no longer returns the zero vector for every input** — coordinate substitution matched bare Symbols against assumption-bearing parsed symbols and silently no-opped, so the field never depended on the basis coordinates (run-017; 4th incarnation of the assumption-mismatch class). Coordinates are matched by name; divergence/curl zeros are now real (a non-zero control `div(x*y, z*x, y*z) = 2*y` is pinned by test).
- **dsolve applies context assumptions** — with k, m positive, `m*x'' + k*x` solves to the trig form instead of complex-root exponentials.
- **Tuple guards** — comma parses (python tuples) can no longer poison a session: `session_record_step` rejects them fail-loud, and session_show's risk/suggestion builders plus the domain-level expression loader degrade gracefully instead of crashing with `'tuple' object has no attribute 'free_symbols'`.
- **divergence results are simplified** — the radial field rendered three unsimplified r^(5/2) terms instead of 0.

Assumption-scope reform motivated by run-013 (per-call assumptions leaked permanently into the shared context even for `session=false` probe calls) and the design discussion that followed.

### Added

- **`unassume(variables)`** — remove assumptions for named symbols from the shared context and the session engine (domain defaults preserved). `assume()` was previously irreversible short of a server restart.
- **`clear_assumptions()`** — reset the whole scope (context + session engine layers), domain defaults preserved.
- **`assumptions_applied` echo** — `math()` responses list which assumptions took effect for the call.

### Changed

- **Per-call assumptions respect the `session` flag** — with `session=true` they persist into the shared context AND the session's assumption engine (visible to the step verifier, so identities recorded under session assumptions verify instead of staying inconclusive); with `session=false` they apply to that call only via a call-local context and the shared context is untouched — stateless calls are now truly side-effect free. Cross-session globals remain the explicit `assume()` tool's job. **Migration note:** code that seeded the context with `math(..., assumptions=[...], session=false)` must call `assume()` (or pass `session=true`) instead.

### Fixed

- **Parse-collapsed boolean steps verify** — when session assumptions make the parser resolve `Eq(...)` to a boolean before recording, a same-value boolean step verifies instead of landing in an unverifiable inconclusive limbo.

## [1.3.0] - 2026-09-10

Assumption-scope reform motivated by run-013 (per-call assumptions leaked permanently into the shared context even for `session=false` probe calls) and the design discussion that followed.

## [1.2.2] - 2026-09-10

Nine defects found by black-box rounds run-011/run-012 (Maxwell-Boltzmann and RC/RLC circuit tasks driven by subagents) and accepted by run-013/014/015 re-runs.

### Added

- **dsolve understands Leibniz notation** — `dV/dt` and `d^2x/dt^2` parse into real `Derivative` terms alongside `diff(V,t)`.
- **dsolve accepts `ics`** — initial conditions like `{"V(0)": "V_0"}` are forwarded to `sympy.dsolve`, eliminating the 3-call manual constant-solving workaround.
- **`list_assumptions` accepts `"merged"`** as an alias for the default merged view.

### Fixed

- **dsolve rejects non-ODE input loudly** — `R*C*dV/dt + V` used to parse `dV`/`dt` as plain symbols and return an algebraic rearrangement disguised as an ODE solution; input without any derivative of the dependent variable now fails with a notation hint.
- **Save selection is goal- and lineage-aware** — `session_complete(auto_save=true)` picks the last symbolic step involving a goal target variable (including hand-recorded binding steps like `Eq(v_rms, ...)`), else the last output in the derivation's symbol lineage; tangential probes (`exp(x)` limit probes, `omega` side-quests) no longer get saved under the derivation's name.
- **Definite integrals verify by numeric quadrature** — the reverse-differentiation check false-FAILED correct definite results (d/dx of a constant is 0); bounds are read from the recorded command, parameters are prime-valued, and quadrature disagreement yields INCONCLUSIVE rather than a false FAILED.
- **solve promotes the positive root** — the `solution` field prefers a provably positive root under active assumptions instead of blindly taking `solutions[0]`; `all_solutions` keeps the full set.
- **series keeps the `O(x**n)` term** instead of silently reporting a bare polynomial as if exact.
- **Scalar strings coerce to lists** — `limitations="..."`, `tags="..."`, `assumptions="..."`, `target_variables="..."`, `related_variables="..."` no longer fail schema validation or splat into characters.

## [1.2.1] - 2026-09-10

Four defects found by black-box round run-008 (damped-oscillator task) and accepted by run-010 probe: all four fixes verified from the black box.

### Fixed

- **`evalf` substitution works under context assumptions** — substitution keys are rebound by name to the assumption-bearing symbols actually present in the parsed expression, instead of silently no-opping when earlier calls installed positive assumptions.
- **Derived-formula saver stores the representative symbolic output** — `session_complete(auto_save=true)` no longer saves a trailing numeric check (evalf float or residual `0`); the last symbolic step output is saved, `variables` metadata is backfilled, and the response reports `saved_expression`.
- **Boolean `simplify` outputs record cleanly** — `simplify(Eq(...))` resolving to a plain Python `True` no longer crashes step verification (`Add - bool` TypeError silently dropped the step); identities are verified when the verifier can confirm them, otherwise INCONCLUSIVE.
- **Goal extraction ignores apostrophes** — prose primes like `x''(t)` are no longer mistaken for single-quoted expressions (junk targets such as `(t) + c x` no longer poison progress matching); double-quoted targets still extract.

## [1.2.0] - 2026-09-10

Structural fixes from the framework-design review of black-box regression rounds run-005/006/007: unknown function calls can no longer degrade to implicit multiplication, recorded steps are the same SymPy objects returned to the client, the derived-formula read/write schema is pinned by contract tests, ignored parameters warn instead of disappearing, and session verification grades outcomes instead of all-or-nothing.

### Added

- **solve returns a bare solution** — `solution` / `solution_latex` fields carry the isolated right-hand side alongside the `Eq(v, ...)` expression, so agents no longer hand-strip the wrapper (and corrupt parentheses doing so).
- **`session_start` / `session_set_goal` accept `target_variables`** — explicit override for the heuristic goal-text variable extraction.
- **`evalf` accepts `substitution`** — substitute symbols and numerically evaluate in one call.
- **dsolve / limit / evalf steps are auto-verified** — via `checkodesol`, numeric probe points, and numeric re-evaluation respectively.

### Fixed

- **Parser red line: `v(t)` stays a function call** — unknown `name(...)` call sites parse as undefined SymPy Functions (Mathematica convention) instead of silently degrading to implicit multiplication (`v*t`); `Integer * Integer**-1` factor pairs fold into exact rationals inside any product, so `1/2*rho*...` round-trips stably through the parser.
- **Recorded steps are the returned objects** — zero-reparse recording: the session archive is built from the live SymPy object, so archive and response can no longer diverge on function notation, assumptions, or unevaluated forms.
- **Derived formulas are readable by the library** — writer (`DerivationResult`) and reader (`FormulaEntry`) agree on `sympy_str` / `expression` / `latex` keys, pinned by contract tests; legacy expression-only YAML still loads.
- **Ignored parameters warn** — a per-operation parameter audit table flags caller-set params the operation does not consume (e.g. `point` on `simplify`); two-word assumptions (`"x positive"`) are accepted alongside `"x is positive"`, and malformed clauses warn instead of being silently dropped.
- **Engine errors propagate** — 14 previously-silent `except` sites now surface `{ExceptionType}: {message}` in the tool's failure message.
- **Verification is graded** — a chain is `verified` when nothing failed and at least one substantive step verified; inconclusive steps (notes, ops without an automatic checker) lower confidence but no longer poison the chain; `generate_derivation_report` always renders the failed/inconclusive counts and LaTeX-renders `given` symbol keys.
- **Goal tracking sees the whole history** — "solve for X" is satisfied when ANY step output isolates X, so a later `evalf` no longer false-reports "Not yet solved".

### Changed

- **`math()` internals split into `tools/_math_dispatch.py`** (operation dispatch, parsing, parameter audit); `tools/math.py` is now a thin recording wrapper.

## [1.1.0] - 2026-09-10

Validated end-to-end by a black-box regression harness (headless MCP client, byte-identical task inputs, artifacts isolated via `SYMKIT_DATA_DIR`): verification false-failures dropped from 15 to 0, generated reports retain all step formulas, fractional exponents parse as exact rationals, and no cross-run formula contamination was observed.

### Fixed

- **Session verification no longer false-fails substitute steps** — the verifier now builds assumption-aware target symbols, so substitution actually matches the input symbols; purely numeric residuals are compared with a 1e-9 tolerance instead of exact equality (machine-epsilon differences no longer flip correct steps to FAILED).
- **Numeric divisions are normalized during parsing** — `x**(1/6)` no longer keeps an unevaluated `Mul(1, 1/6)` exponent, so float bases like `65.0**(1/6)` evaluate numerically; unevaluated `Derivative` semantics are preserved.
- **`substitute` folds evaluable unevaluated derivatives** — substituting into a deferred derivative no longer leaves `Derivative(0, x)` behind.
- **Derived formulas are searchable** — `formula_search` now includes session-derived formulas (`formulas/derived/`) in its corpus; previously they were only visible to the recommender.
- **`generate_derivation_report` renders what it is given** — step `latex` is rendered as display math; `verification` accepts int counts (total/verified/failed/inconclusive) plus a text `note` (legacy bools still render as ✅/❌); the Results section emits proper LaTeX instead of raw SymPy source text.
- **Goal progress counts variables from all steps** — target variables appearing only in intermediate steps are no longer reported missing; `progress_score` reflects coverage when no explicit target expression is set; multi-letter underscored symbols (e.g. `nu_tilde`) are extracted from goal text.
- **Persisting no longer flips an ACTIVE session to PAUSED** — `session_start` no longer returns the confusing `status: "paused"` right after creation; `session_complete`'s `auto_save` is documented as gating only the formula-library write (the session JSON is always persisted).
- **Pinned `mcp>=1.0.0,<2.0`** — fresh installs no longer crash at startup (mcp 2.x removed `mcp.server.fastmcp`); `serverInfo.version` now reports the symkit package version instead of the MCP SDK version.

### Added

- **New `evalf` math operation** — numeric floating-point evaluation, so agents no longer need decimal-exponent workarounds.
- **solve() warns on float coefficients** — solutions from equations containing float coefficients (e.g. `0.5`) carry an explanatory warning pointing to exact fractions (`1/2`) for exact symbolic results.

## [1.0.1] - 2026-07-08

### Changed

- **Lowered Python requirement from 3.12+ to 3.10+** to make `pip install symkit-mcp` available on more environments.

### Fixed

- **Corrected MCP tool count from 43 to 41** across `README.md`, `README.zh-CN.md`, `ARCHITECTURE.md`, `docs/symkit-design.md`, and `docs/symkit-design.zh-CN.md`.

## [1.0.0] - 2026-07-08

### Changed

- **Project rebranded to SymKit** — a general-purpose symbolic formula derivation engine
  - Renamed packages from `nsforge` / `nsforge_mcp` to `symkit` / `symkit_mcp`
  - Updated `pyproject.toml`, README, and documentation to reflect the new name
  - Project positioning is now domain-agnostic (physics, engineering, chemistry, biology, economics, etc.)
- **Repository cleanup for public release**
  - Removed generated cache files (`__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`)
  - Removed runtime artifacts (`derivation_sessions/`, `formulas/derived/`)
  - Removed development-only workspace files (`.claude/`, `memory-bank/`, `.vscode/`)
  - Rewrote `.gitignore` in English with broader coverage
- **Documentation refreshed**
  - Rewrote `README.md` and `README.zh-CN.md` with general-purpose examples and the correct **41-tool** count
  - Updated `ARCHITECTURE.md`, `CLAUDE.md`, and `ROADMAP.md` to match the current tool set
  - Removed outdated references to non-existent tools, skills, and Memory Bank
- **Source comments internationalized**
  - All Chinese comments and docstrings in `src/` translated to English
- **Version bumped to 1.0.0** across `pyproject.toml`, `src/symkit/__init__.py`, and `src/symkit_mcp/__init__.py`; updated `Development Status` classifier to `5 - Production/Stable`.
- **Initial PyPI release automation** via `.github/workflows/release.yml` using Trusted Publishing (OIDC): pushes to `main` publish to TestPyPI, and `v*` tags publish to PyPI.

## [0.2.5] - 2026-07-07

### Fixed

- **CWD-relative data paths broke after `pip install`** — seed formulas,
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
- **Derived-formula data isolation bug** — `DerivationSession.__post_init__`
  instantiated a fresh `DerivationRepository(Path("formulas/derived"))` that
  bypassed the global singleton and the test fixture's temp dir, causing real
  persisted formulas to outscore test candidates. This was the root cause of
  two pre-existing test failures (`test_derive_with_scipy_external_source`,
  `test_derive_includes_external_recommendations`), now fixed. The
  `fresh_session_manager` fixture now resets the repository singleton too.

### Changed

- **Removed three unused heavy dependencies** — `matplotlib`, `pint`, and
  `scipy` were declared but never imported at runtime. `scipy_constants.py`
  hardcodes CODATA values as float literals; the "scipy" string remains only as
  a textual source label. `pip install symkit-mcp` is now significantly lighter
  (no more numpy/scipy/matplotlib transitive pull).
- **Seed formula library moved into the package** — the six seed YAMLs
  (Reynolds number, Navier-Stokes, Euler, continuity, Newton's 2nd law, ideal
  gas law) now live under `src/symkit/resources/seed_formulas/` and ship in the
  wheel. User-added formulas via `formula_add` write to a writable per-user
  overlay that overrides seeds by id; deleting a seed-id removes only the
  override, leaving the read-only seed intact.
- **Version bumped to 0.2.5** across `pyproject.toml`,
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

### Fixed

- **Dimensional analysis (sandbox round 13, all verified through MCP stdio)**
  - `register_symbol(unit=...)` was silently ignored for every name the built-in
    registry already ships a default for: `k` (thermal conductivity) analysed as
    the pharmacokinetic rate constant `1/h`, `V` (velocity) as the volume of
    distribution `L`, plus `rho`, `p`, `T`, `nu`, `mu`. User registrations now
    take precedence over built-in domain defaults.
  - A manually recorded step was judged with the *previous* step's expression
    (`session_record_step` archives the prior expression in `input_srepr`), so
    `T_w + T_in` — two temperatures added — failed with an unrelated `exp(x)`
    complaint and dragged the whole chain to `overall: failed`. Recorded steps
    are now checked on their own expression only.
  - Fractional exponents made the checker bail out: engineering correlations
    such as `Nu == 0.027*Re**0.8*Pr**(1/3)*D` slipped through, and the report
    claimed unknown symbols while listing none. A dimensionless base now stays
    dimensionless under any exponent, and the message distinguishes an unknown
    unit from a form the checker cannot reduce.
  - `"-"` (the marker the write path asks callers to use for a dimensionless
    quantity) was read as *unknown*, leaving every dimensionless correlation
    unverifiable. `-`, `1`, `dimensionless` and `unitless` now assert
    dimensionless.
  - A matrix step crashed `session_verify_session` outright
    (`'MutableDenseMatrix' object has no attribute 'is_number'`).

- **`generate_output`** returned the raw exception text
  `Error executing tool generate_output: 'result_var'` when a step item lacked a
  key its renderer indexes. Nested `steps`/`parameters`/`expressions`/
  `operations` items are now validated and reported as actionable errors.

- **`formula_promote`** silently rewrote promoted entries through a partial
  model: a `verified: true` staging formula became `verified: false`, and
  assumptions, limitations, derivation_steps and session_ids were dropped.
  Unmodeled keys are now carried through the load/save round trip.

- **`formula_add`** rejected `variables={}` while its own error text promised
  "can be empty {}" (the guard was `if not variables`). With units now mandatory
  per variable, a formula with no free symbols could not be added at all.

- **`intent_execute`** answered an unrecognized intent with
  `intent_execute("<the same text>")` — non-terminating for a caller that
  follows the recommendation, and contradicting its own rationale. It now
  points at `tool_categories` instead.

- **Formula-derivation symbols `Q` (heat) and `O`** failed to parse
  (`Q = m*cp*dT` → `SympifyError: <AssumptionKeys object at 0x...>`); both are
  now protected as variables, while `O(x**2)` keeps its Big-O meaning.
