# Math and physics subject separation

Math and physics are independent peer subjects. Chemistry follows the same general principle.
This document records the current dependency graph and the tests that keep it from regressing.
It replaces the older staged ticket plan; those phases are complete.

## Before and after

Before this cleanup, physics was a package but not an independent request pipeline:

```text
user
  → math detection (also recognized physics)
  → math extractor registry (also registered physics extractors)
  → MathIntent | PhysicsIntent
  → math block registry (also registered physics builders)
  → VerifiedMathBlock (also carried physics state)
  → MATH_SOLVER_HINT (also contained physics instructions)
  → math direct/fence code (also understood physics simulations)
```

That arrangement made math the parent system and allowed a change in a math registry, prompt, or
fence to alter physics behavior.

The current graph selects a peer subject first:

```text
                           ┌→ math detection → MathIntent → math solver/trace
user → neutral dispatcher ┤                                      ↓
                           └→ physics detection → PhysicsIntent → physics solver/working
                                                                  ↓
                       neutral VerifiedSolveBlock transport ← subject result
                                                                  ↓
                   subject direct reply or subject prompt + subject fence
                                                                  ↓
                                  neutral chat stream and persistence
```

Neither subject imports or registers the other subject's extraction, solver, direct-reply, prompt,
or fence behavior.

## Ownership

| Layer | Math owns | Physics owns | Neutral/shared owns |
|---|---|---|---|
| Detection | `modules/math/tools/prompt.py`, math matchers | `modules/physics/extract.py::needs_physics` | `services/subjects/dispatch.py::detect_subject` chooses one peer subject |
| Intent | `modules/math/schemas/intent.py::MathIntent` | `modules/physics/schemas/intent.py::PhysicsIntent` | No shared subject enum |
| Extraction | `modules/math/tools/extract.py` and math extractors | `modules/physics/extract.py` and physics extractors | Text/unit scanning primitives in `services/` |
| Solving | `modules/math/solve/`, `modules/math/school.py` | `modules/physics/solver.py`, `modules/physics/solvers/` | `services/sympy_executor.py`, generic solve error |
| Teaching data | Math `KeyStep`, arithmetic/fraction traces | Physics formula/substitution working and trajectories | Generic transport only |
| Direct reply | `modules/math/tools/direct*.py` | `modules/physics/direct.py` | `maybe_direct_subject_reply` dispatch |
| Prompt context | math prompt constants and `modules/math/tools/prompt.py` | `prompt_constants/physics.py`, `modules/physics/prompt.py` | `prompt_constants/solving.py` universal verification safety |
| Finalization | `modules/math/fence.py` | `modules/physics/fence.py` | stream pipeline dispatches by verified block type |
| Result transport | `VerifiedMathBlock` | `VerifiedPhysicsBlock` | base `VerifiedSolveBlock`, markers, `SolveServiceError` |
| Rendering | math/fence-specific mobile components | trajectory/simulation components | Markdown, persistence, Copy/share/read-aloud infrastructure |

## Shared code is deliberately narrow

`app.services.solving` is a transport boundary, not a solver. It contains:

- `SolveServiceError`, the subject-neutral deterministic-decline exception;
- `VerifiedSolveBlock`, the generic canonical-result transport;
- `VerifiedMathBlock` and `VerifiedPhysicsBlock`, which keep subject-specific state separate;
- neutral marker stripping and wrapper helpers.

`app.services.subjects.dispatch` owns generic chat integration:

- detect one subject before extraction;
- call only that subject's augmentation path, through its adapter (`services/subjects/registry`,
  structure ticket ST-07);
- dispatch direct presentation based on the verified block subtype.

`app.services.symbolic_text`, `app.services.unit_text`, and `app.services.units` contain scanning
or unit primitives that have no subject policy. `app.core.sympy_executor` owns the bounded
worker execution mechanism (math hands it the warm-up solve at process start). Moving these primitives out of math prevents physics from importing a
different subject merely to parse text, units, or run the shared symbolic engine.

The only allowed production import from physics into a math schema is `GraphBlockSpec`. A physics
trajectory is rendered by the same generic sampled-function graph contract. The dependency is on
a presentation schema, not on a math extractor or solver. The static seam test names and justifies
this exception explicitly; any new cross-subject dependency fails the test.

## Prompt and fence boundaries

Math and physics have independent prompt guidance. `MATH_SOLVER_HINT` contains no physics kind,
formula, or simulation instruction. Physics guidance is added only on the physics path.

The universal rule—never claim deterministic verification without a verified result—lives in the
neutral solve-safety prompt. It is not duplicated or hidden inside either subject.

Math fence finalization knows math answer, arithmetic, geometry, graph, and number-line contracts.
Physics fence finalization knows physics answers, formula working, trajectories, and simulations.
The neutral stream pipeline selects the correct finalizer from the result type. A model cannot
replace a subject's canonical answer or invent a canonical visual after solving. Timeout and
exception recovery follows the same ownership rule: a physics turn uses the physics-safe fence
fallback and never enters math graph recovery.

## Rate/time/distance ownership

Physical speed, distance, and travel-time questions—including unit-bearing forms—belong to
physics. They are extracted by `modules/physics/extractors/rates.py` and solved by the physics
motion solver. Math no longer keeps an “average speed” escape hatch or imports the physics rate
grammar.

Pure numeric ratios and unit conversions remain math. The subject detector uses the request's
physical quantities and units to select physics, rather than routing all division to physics.
Likewise, exponent wording such as “the third power of 5” is a complete math grammar. Physics
recognizes “power of …” only when the bounded phrase names a physical quantity or unit, so a broad
word collision cannot steal the request before math extraction.

## Architecture guards

`app/tests/services/test_subject_separation_seams.py` statically and dynamically enforces:

- `MathIntent.kind` and `PhysicsIntent.kind` are disjoint;
- every declared kind has an owning builder registry entry;
- `modules/math/` does not import `PhysicsIntent`, physics extractors, or physics builders;
- `modules/physics/` cannot import math internals outside the explicit graph-schema exception;
- math prompt constants contain no physics behavior;
- neutral and subject packages import cold without relying on import order;
- ordinary math detection cannot return a physics intent, and vice versa.

Physics request-integrity tests additionally re-extract the current user request before a direct
reply. A verified block computed for one prompt cannot be reused to answer a different or compound
prompt.

## Compatibility surface

Every subject raises the neutral `SolveServiceError`; the `MathServiceError` alias was removed once
no caller used it (2026-10-20 code-health audit, DEAD-05).

Older public math entry points remain available where existing callers depend on them, but they
no longer dispatch physics. Compatibility must never reintroduce a physics registry or intent into
the math package.

## Adding a subject capability

When adding a math or physics operation:

1. add the kind/operation to that subject's schema;
2. add extraction in that subject only;
3. add a deterministic solver and typed working data;
4. register it in that subject's builder registry;
5. add subject prompt/direct/fence behavior if needed;
6. add registry-completeness, request-integrity, regression, and invariant tests;
7. do not add a branch to another subject's dispatcher.

If both subjects need a primitive, first prove that it contains no subject policy, then move the
small primitive to `app.services`. Sharing a solver or extractor through math is not neutral reuse.

## Out of scope

The camera's user-facing math/physics/chemistry picker is a separate product surface. This
document covers backend subject ownership and chat integration. The Grade 1–12 capability audit is
maintained in [MATH_GRADE_1_12_COVERAGE.md](./MATH_GRADE_1_12_COVERAGE.md).
