# Physics review — 2026-10-04

Review baseline: `origin/main` at the start of this review. The physics suite had
3,238 passing tests. Its school corpus answered all 132 questions correctly; the
coverage floor was 131. These figures describe the maintained examples, not every
possible phrasing or every topic supported by SymPy.

## Topic inventory

The baseline catalog contains 282 operations across 20 solver kinds, 111 with
word-problem bindings and 89 with catalog-owned arithmetic expressions. Catalog
registration checks solver ownership; binding tests exercise every declared input set.

| Kind | Operations | Scope |
|---|---:|---|
| Thermal | 40 | Heat, phase change, gases, kinetic theory, thermodynamics |
| Circuit | 36 | DC, capacitors, inductors, RC/RL, AC and transformers |
| Modern | 34 | Photons, photoelectric effect, nuclear decay, relativity, atomic levels |
| Fluids | 23 | Pressure, flow, buoyancy, viscosity and capillarity |
| Magnetism | 20 | Fields, magnetic forces and induction |
| Rotation | 16 | Angular motion, inertia, rolling and angular momentum |
| Optics | 15 | Lenses, mirrors, refraction, diffraction and interference |
| Waves | 13 | Propagation, resonance, Doppler and sound |
| Kinematics | 12 | Constant motion, gravity and rates |
| Gravitation | 10 | Gravity, orbital motion and escape speed |
| Energy | 9 | Work, power, kinetic/potential energy and conservation |
| Circular | 9 | Circular motion and related constraints |
| Spring | 8 | Hooke's law, spring energy and oscillation quantities |
| Force | 7 | Force balance, weight and tension |
| Friction | 6 | Normal force, friction, limiting equilibrium and incline motion |
| Materials | 6 | Elasticity and stress/strain |
| Projectile | 5 | Trajectories and launch quantities |
| SUVAT | 5 | Constant-acceleration rearrangements |
| Momentum | 4 | Momentum, impulse, collision and recoil |
| Torque | 4 | Moments and lever balance |

## Correctness findings

The independent Bugbot review reproduced three P1 issues and eight P2 issues.
The companion correctness and animation PRs address these cases with regression tests.

- Static friction was returned as its maximum `mu*N` instead of the equilibrium
  force. Resting 5 kg, 20 degrees, `mu_s=0.4`: 18.4 N versus 16.8 N required.
- Sliding state and direction were lost. Downhill 10 degrees, `mu_k=0.5`:
  0 versus -3.13 m/s². Uphill 30 degrees, `mu_k=0.2`: 3.21 versus 6.60 m/s² downhill.
- SUVAT distance after reversal was displacement. `u=10`, `a=-2`, `t=10`:
  0 m versus 50 m travelled.
- Collision arithmetic used SI values but its substitution printed raw mixed units.
- Vertical launches produced zero-width scenes and lost the scalar answer.
- Atwood masses were sorted before conversion, reversing the intended magnitude.
- Vector endpoints in negative quadrants were outside the scene bounds.
- Work/height annotations used physical lengths within fixed display bounds;
  potential-energy ground crossed the suspended body.
- Four-decimal SI rounding collapsed micrometre orbits to a stationary point.
- Replacing one moving scene with another retained the previous animation progress.
- A single fixed playback duration concealed changes to physical timescales.

Review of the implementations also caught decimal-token precision loss, symbolic
eigensystems with unstated exceptional parameters, ODE families missing coefficient
and solution-domain conditions, a false displacement/distance formula equivalence,
initial rest mistaken for current equilibrium, zero amplitude treated as unspecified,
and harmonic velocity arrows at zero-velocity turning points. Regression tests cover
these cases. Numeric eigensystems and conditional linear ODE families define the
supported symbolic boundary; unsupported exceptional branches decline.

## Structure and extensions

Keep the catalog as the owner of numerical laws and assumptions. Extractors bind
words and dimensions; pure solvers compute in SI; presentation reads those exact
results. Shared law binding and the bounded symbolic executor are useful common
infrastructure. Physics must not reach through math's private solver modules.

The new explicit-model path adds algebra/systems, simplification, differentiation,
integration, conditional linear ODE general solutions, Cartesian vector calculus, vector products and
numeric matrix eigensystems. Decimal tokens retain exact precision. ODE leading-coefficient,
discriminant and generated singularity conditions are explicit; unsupported nonlinear
or parameterized variable-coefficient equations and symbolic eigensystems decline.
Parameterized algebra supports affine equations with fixed coefficients. Systems whose
rank or degree depends on an unconstrained coefficient decline, including `a*x=0`;
substitution alone cannot prove completeness at singular coefficient values.
The parser, operation solver and schema remain separate from
numeric word-problem extraction. Exact input/output binding prevents an old symbolic
result from answering a changed request.

## Remaining SymPy-capable coverage

SymPy is a general library. Supporting every possible model or expression is not a
finite feature list. These are concrete capabilities **not yet supported as complete
physics requests**; the presence of SymPy or a related named formula is not coverage:

- ODE initial/boundary conditions, coupled ODEs, PDEs and user-specified piecewise models.
- Lagrange/Kane/Hamilton derivations from bodies, generalized coordinates and constraints.
- Laplace/Fourier transforms, transfer functions, state-space and stability analysis.
- Quantum operators/states, commutators, spin, wavefunction normalization and expectation
  values as typed physics operations; explicit finite integrals and matrices can express
  some of their mathematics, but do not supply their physics assumptions.
- Polarization/Jones matrices, paraxial ray systems and symbolic beam/continuum mechanics.
- Tensor relativity, symbolic Maxwell systems and coordinate systems beyond Cartesian.
- Automatic unit checking of arbitrary symbolic models, positivity/reality assumptions,
  transcendental solution sets, singular parameter branches and numerical root searches.
- Parameter sliders with server recomputation, additional field/circuit/wave scenes, and
  device profiling of frame time, clipping, accessibility and background transitions.

These require explicit contracts and testable physical assumptions. Unsupported requests
must continue to decline instead of returning a fragment under a verified label.

## Native animation contract

The native renderer uses Skia with Reanimated shared/derived values. The server samples
the path uniformly in time; the device interpolates those samples with a uniform spatial
scale. Physics is never re-solved on the device. Timing metadata must record the physical
time span and playback rate separately, and scene replacement must cancel the old clock.
Reduce Motion keeps the static diagram. Lifecycle and parameter tests complement native
device validation; Jest mocks cannot establish native frame rate or visual quality.

References: [SymPy algebra](https://docs.sympy.org/latest/guides/solving/solve-equation-algebraically.html),
[SymPy ODEs](https://docs.sympy.org/latest/guides/solving/solve-ode.html),
[Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/).
