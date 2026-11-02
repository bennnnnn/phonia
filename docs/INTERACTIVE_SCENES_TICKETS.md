# Interactive scenes: real objects and live sliders

The roadmap for making Recall's STEM pictures look like the thing in the question and respond
when a student changes a value. It is written to be picked up later, ticket by ticket. Status:
**planned, not started** (decided 2026-10-20).

## Why

The goal is to be the biggest STEM learning app. About a week after launch, Recall is to be
refocused on STEM, with more STEM content, more capacity, and a UI built around it. Pictures are
how a student remembers an answer. Two things would make them teach:

- **Show the thing itself.** A car should look like a car, and a dropped ball like a ball.
- **Let the student experiment.** Drag a slider ("what if the speed were 30 m/s?") and see the
  motion, the numbers, and the graph change straight away.

## Where things stand (2026-10-20)

- **Physics scenes** (`simulation` fence, schema v2, `modules/physics/schemas/simulation.py`).
  - **Types:** about 20 scene types, plus `circuit`, `rays` and `wave` diagrams. See
    `docs/physics.md#pictures`.
  - **Who builds them:** the solvers' scene builders (`solvers/motion_scenes.py`,
    `force_scenes.py`, `circuit_scenes.py`, `optics_scenes.py`, `wave_scenes.py`,
    `field_scenes.py`), plus `solvers/catalog_scenes.py` for 27 catalog laws.
  - **Coverage:** 162 of the 163 STEM-sweep questions that want a picture get one. Of the 507
    catalog laws, only the core topics have a picture.
- **Objects are shapes.** `SimulationBody.shape` is `circle` or `box`; a car is a box.
- **No interaction.** The server samples every position of every frame
  (`SimulationBody.path`). The phone walks those samples and never re-derives motion
  (`lib/physics/simulation/`, `components/rich/SimulationBlock.tsx`). This is golden rule 7.
- **Graphs.** Maths graphs (`graph` fence) are server-sampled points drawn with Skia. Chemistry
  has 2D (smiles-drawer) and 3D (Skia) molecules.
- **Building blocks that already exist:**
  - `services/law_binding/expression.py`: a checked arithmetic tree for every catalog law, with a
    closed list of functions. Nothing is executed; the tree is walked.
  - `services/law_binding/reduction.py`: the same tree worked step by step.
  - Shared server/phone fixtures (`docs/fixtures/presentation_cases.json`) that hold twin code to
    one output.

## The decision: Option A (phone evaluates a checked formula)

Golden rule 7 changes from "the phone never computes motion" to:

> The phone never **solves**. For an interactive scene, the server sends the law's checked
> formula as a **tree** (never as text), the names a slider may change with their ranges, and
> the sampled path for the value asked. The phone only **evaluates** that tree, with the closed
> list of operations below, to redraw the motion as a slider moves.

Rules that come with it:

1. **The server owns the physics.**
   - It decides the scene, which quantities are adjustable, their units and ranges, and the
     formula for each moving coordinate and each readout.
   - It checks the formula against its own sampled path before sending it (see IS-01).
2. **The phone only walks a tree.**
   - Operations: numbers, names, `+ − × ÷ ^`, unary minus, and the functions `sqrt sin cos tan
     asin acos atan exp log abs`, with `pi`, `t` and the declared parameters as names.
   - No string parsing, no `eval`, no equation solving.
   - Limits on depth and size; NaN or infinity stops the redraw and shows the last good frame.
3. **Parity is tested, not hoped for.** The phone's evaluator has a twin test file of server
   cases (`docs/fixtures/expression_cases.json`), generated like `physics_replies.json`.
4. **Option B is the fallback.** When the motion has no closed form (collisions stepped in time,
   air drag, several interacting bodies), the phone asks the server for a new scene when the
   slider is released (IS-20). There's no evaluation on the phone for those scenes.
5. **The worked answer stays the answer to the question asked.**
   - Sliders change the picture and its live readouts, not the Given/Substitution/Answer above
     it.
   - A **"Solve with these values"** button sends the question again with the new numbers. The
     server solves and verifies it as usual.
6. **Older apps keep working.** The schema change is additive. The sampled `path` stays in every
   scene, so an app without the new code plays the scene as today.

## Phase 1: foundations and the most-asked scenes (about 3 weeks)

**Done when:** the eight most common physics situations have real objects and working sliders,
with the parity fixture and the sweep guarding them.

### IS-01 Schema v3 (additive)
`modules/physics/schemas/simulation.py`:
- `SimulationBody.appearance: Appearance | None`. `Appearance` is a closed list: `car`, `ball`,
  `person`, `crate`, `cart`, `block`, `bob`, `rocket`, `planet`, `satellite`, `stone`,
  `skateboarder`, …. `None` draws today's circle or box.
- `SimulationBody.motion: Motion | None`:
  - `x` and `y` as expression trees over `t` and the parameters, plus an optional `heading` tree;
  - `t_max` as a tree, for example the time of flight.
- `SimulationBlockSpec.controls: list[SceneControl]`. Each control has:
  - `name` (the parameter), `symbol` (LaTeX), `label_key` (i18n), `unit`;
  - `min`, `max`, `step` and `value` (the asked value);
  - an optional `bounds` tree for limits that depend on other values.
- `SimulationBlockSpec.readouts: list[Readout]`: a `symbol`, a tree and a `unit` (for example
  R, H, t and v at landing), shown live under the scene.
- **Server self-check on build:**
  - every tree uses only the closed operations and declared names;
  - evaluating `motion` at the sampled times reproduces `path` within 1e-6 relative;
  - every control's `min ≤ value ≤ max`;
  - motion and readouts stay finite at all 2ⁿ corners of the control ranges.
  
  A scene that fails any of these drops its `controls` and stays a plain animation, so a broken
  slider never ships.
- **Tree format:** compact JSON, for example `{"op":"*","a":[…]}`, built from the checked Python
  `ast` in `expression.py` (`to_tree`).

### IS-02 Server: controls and motion for the eight families
Families: projectile (with a ledge), free fall and vertical throw, straight-line motion (the
car), incline (with and without friction), pendulum (small angle), spring and simple harmonic
motion, uniform circular motion, and travelling and standing waves.
- Builders in `motion_scenes.py`, `force_scenes.py`, `wave_scenes.py` and `catalog_scenes.py`.
- Ranges come from the law's variables in the catalog (`VariableSpec`), with sensible school
  ranges. A slider may also add quantities the question didn't give, like `g` on the Moon.
- Readouts reuse the law's own expression (`FormulaSpec.expression`), so a readout always matches
  the formula above it.

### IS-03 Evaluator twin on the phone
- New `lib/physics/expression.ts`:
  - evaluates a tree on the UI thread (worklet-safe; `lib/__tests__/workletRules.test.ts`
    applies);
  - no allocation per frame, and limits on depth and size.
- New shared fixture `docs/fixtures/expression_cases.json`:
  - written by a server test (`UPDATE_EXPRESSION_FIXTURE=1`) holding trees, parameter sets and
    values;
  - read by a jest test that checks parity to 1e-9 relative.

### IS-04 Sliders and live readouts on the phone
- New kit control `ui/controls/Slider.tsx`. The lint rules keep raw controls inside the kit;
  list the slider in `ui/README.md`.
- `components/rich/SimulationBlock.tsx` and `lib/physics/simulation/`:
  - a control panel under the scene, then the readouts;
  - redraw from the motion trees as the slider moves;
  - restart the motion from `t = 0` on release;
  - refit the viewport with hysteresis (`viewport.ts`, `layoutFrames.ts`) so the frame doesn't
    jump while dragging;
  - **Reset** returns to the asked values.
- **"Solve with these values"** sends a chat message built from the question and the new values
  (`features/chat` send path, one tap).
- **Accessibility:**
  - each slider has a label, value and unit;
  - the alt sentence updates;
  - reduced motion shows the end frame.

### IS-05 Artwork for objects
- New `components/rich/scene/appearance/`:
  - one Skia drawing per `Appearance`, coloured from theme tokens in light and dark;
  - scaled to the body's radius or box;
  - turned along its heading where that makes sense (a rocket turns, a car on the ground stays
    level).
- Phase 1 set, about 12: car, ball, person, crate, cart, block, pendulum bob, spring coil,
  rocket, planet, satellite, stone. Plus the scenery the scenes already draw: ledge, ground,
  incline.
- **Art style: stylized**, clean and flat like Brilliant or Duolingo, drawn in code. A realistic
  set would need a designer or a licensed pack (see Open questions).

### IS-06 Server: which object it is
- New reader for everyday objects in the question ("car", "ball", "stone", "girl", "box",
  "rocket"), mapped to an `Appearance`, with look-alike tests.
  - It goes in the physics extractors, next to `modules/physics/bodies.py`, which reads planets
    today.
  - Add its look-alikes to the behavior sweep corpus.
- Each scene type has a default when no object is named: a ball for a projectile, a block for an
  incline.

### IS-07 Rules and docs
- Update golden rule 7 in `CLAUDE.md` and `docs/physics.md#pictures` to the Option A wording
  above.
- Add the expression fixture to the shared-fixture list in `docs/ENGINEERING_STANDARDS.md`.

### IS-08 Sweep and tests
- `tests/behavior/stem_sweep.py`: validate `controls`, `motion` and `readouts` on every scene
  (the IS-01 checks again, from the outside).
- Hold "interactive pictures" entry by entry in `stem_snapshot.json`, like drawn pictures.
- Phone tests:
  - the evaluator parity fixture;
  - slider interaction (change, release, reset);
  - snapshot tests of each appearance in light and dark;
  - frame rate measured on a mid-range Android phone in a dev build.

### IS-09 Usage signals
- Metadata-only analytics events (`modules/analytics`, `lib/api/analytics.ts`), never prompt
  text: `scene_viewed`, `scene_control_changed`, `scene_solved_with_values`.
- They rank the families for Phase 2 by real use.

## Phase 2: the rest of physics (about 4–6 weeks)

Group the 507 catalog laws into visual families. Build them in order of usage (IS-09); each
family takes about 1–3 days. **Done for a family when:**
- it has a builder, controls and readouts;
- its objects have artwork;
- its sweep entries pass;
- the STEM snapshot records them.

| Family | Scene and sliders | Option |
|---|---|---|
| Forces, Newton's laws, friction | blocks, Atwood machine and pulleys; masses, μ, angle | A |
| Energy | a track with KE/PE bars; height, mass, speed | A |
| Momentum and collisions | carts colliding; masses, speeds, elastic or inelastic | B (IS-20) |
| Circular motion and gravitation | orbits, a conical pendulum, a car on a banked curve; radius, mass, speed | A |
| Oscillations | spring and mass, pendulum, damped motion | A (damped: B) |
| Waves and sound | string and pipe harmonics, Doppler; frequency, length, speed | A |
| Optics | lens and mirror ray diagrams; object distance, focal length | A |
| Circuits | series and parallel; voltage and resistances, with current, voltage and power readouts and bulb brightness | A |
| Electric and magnetic fields | charges and field lines, force on a wire | A for forces; B for field maps |
| Gases and thermal | particles in a box; temperature, volume, amount | A for the state; particle jitter is decorative only (seeded, no physics) |
| Fluids | buoyancy, pressure at depth, continuity | A |
| Modern and nuclear | a decay curve with a half-life slider, photoelectric emission | A |

A law with nothing meaningful to show (Hawking temperature, Fermi energy) stays without a
picture.

### IS-20 Option B: a new scene on release
- `POST /physics/scene` with `{operation, params}` returns a verified scene for scenes that can't
  be evaluated on the phone.
- Rate-limited per user and cached by `(operation, params)` in Redis.
- The phone shows the last frame dimmed while the new one loads.

## Phase 3: maths and chemistry (about 5–7 weeks)

- **Maths.** The same evaluator and slider UI:
  - graphs with parameter sliders (families like `a·sin(bx + c)`, transformations, the tangent
    at x, the area under a curve);
  - animated geometry constructions (angle sums, circle theorems);
  - number lines and fraction models.
  
  The `graph` fence gains the same `controls` and expression tree. Its points stay for older
  apps.
- **Chemistry:**
  - particle models for the gas laws;
  - reaction progress (mole bars as a reaction proceeds);
  - titration curves with concentration and volume sliders;
  - the existing 3D molecules, with a rotate and zoom hint.

## Estimates and risks

| Phase | Effort (one developer with AI help) |
|---|---|
| 1, foundations and eight families | about 3 weeks |
| 2, the rest of physics | about 4–6 weeks |
| 3, maths and chemistry | about 5–7 weeks |
| Realistic art set (optional, in parallel) | about 2–4 weeks with a designer |

Risks, and what keeps each small:
- **Frame rate on low-end Android.** Evaluate on the UI thread with no allocation per frame; cap
  points; measure in IS-08.
- **Evaluator parity bugs.** The shared fixture and the server self-check in IS-01; a scene that
  fails drops its sliders.
- **Inconsistent art.** One style guide and theme tokens; artwork reviewed in light and dark.
- **Scope creep.** Families go in order of usage; a law with nothing to show stays without a
  picture.
- **Prompt and turn cost.** None from Option A: sliders never reach the server or the model. "Solve
  with these values" is an ordinary turn.

## Open questions

- Art: stylized only, or a realistic set later (designer or licensed pack)?
- When a slider moves, should the worked solution follow automatically, or only through "Solve
  with these values"? This plan says only through the button.
- Should the STEM refocus also add a full-screen "explore" view for scenes in lessons? The scene
  component should be built so it can grow into one.
