"""Verified fluids operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "pressure_from_force",
        "fluids",
        "Pressure formula",
        "P",
        base_latex="P = \\frac{F}{A}",
        variables=(
            var("F", "F", "newton"),
            var("area", "A", "meter ** 2"),
        ),
    ),
    formula(
        "pressure_at_depth",
        "fluids",
        "Hydrostatic-pressure equation",
        "P",
        assumptions=("gauge pressure, not absolute",),
        variables=(
            var("depth", "h", "meter"),
            var("g", "g", "meter / second ** 2"),
            var("rho", r"\rho", "kilogram / meter ** 3"),
        ),
    ),
    formula(
        "upthrust",
        "fluids",
        "Archimedes' principle",
        "F_b",
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("rho", r"\rho", "kilogram / meter ** 3"),
            var("volume", "V", "meter ** 3"),
        ),
    ),
    formula(
        "density",
        "fluids",
        "Density formula",
        "\\rho",
        base_latex="\\rho = \\frac{m}{V}",
        variables=(
            var("m", "m", "kilogram"),
            var("volume", "V", "meter ** 3"),
        ),
    ),
    formula(
        "continuity_velocity",
        "fluids",
        "Continuity equation",
        "v_2",
        base_latex="A_1v_1 = A_2v_2",
        variants=(
            # A pipe given by its diameters: v₂ = v₁(d₁/d₂)².
            FormulaVariant(
                present=frozenset({"d1", "d2"}),
                latex=r"v_2 = v_1\left(\frac{d_1}{d_2}\right)^2",
            ),
        ),
        variables=(
            var("A1", "A_1", "meter ** 2"),
            var("A2", "A_2", "meter ** 2"),
            var("d1", "d_1", "meter"),
            var("d2", "d_2", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "flow_rate",
        "fluids",
        "Volume-flow-rate formula",
        "Q",
        variables=(
            var("area", "A", "meter ** 2"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "hydraulic_force",
        "fluids",
        "Pascal's principle",
        "F_2",
        base_latex="\\frac{F_1}{A_1} = \\frac{F_2}{A_2}",
        variants=(
            # Pistons given by diameter: each area goes with its diameter squared.
            FormulaVariant(
                present=frozenset({"d1", "d2"}),
                latex=r"F_2 = F_1\left(\frac{d_2}{d_1}\right)^2",
            ),
        ),
        variables=(
            var("A1", "A_1", "meter ** 2"),
            var("A2", "A_2", "meter ** 2"),
            var("d1", "d_1", "meter"),
            var("d2", "d_2", "meter"),
            var("F1", "F_1", "newton"),
        ),
    ),
    formula(
        "bernoulli_pressure",
        "fluids",
        "Bernoulli's equation",
        "P_2",
        base_latex="P_1 + \\frac{1}{2}\\rho v_1^2 = P_2 + \\frac{1}{2}\\rho v_2^2",
        assumptions=("horizontal flow, so the height terms cancel",),
        variants=(
            FormulaVariant(
                present=frozenset({"h1", "h2"}),
                latex=(
                    r"P_1 + \frac{1}{2}\rho v_1^2 + \rho gh_1 = "
                    r"P_2 + \frac{1}{2}\rho v_2^2 + \rho gh_2"
                ),
                assumptions=("steady incompressible flow with no viscosity",),
            ),
        ),
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("h1", "h_1", "meter"),
            var("h2", "h_2", "meter"),
            var("pres1", "P_1", "pascal"),
            var("rho", r"\rho", "kilogram / meter ** 3"),
            var("v1", "v_1", "meter / second"),
            var("v2", "v_2", "meter / second"),
        ),
    ),
    # Horizontal Bernoulli as a difference: water that speeds up from v₁ to v₂
    # loses ½rho(v₂² - v₁²) of pressure. No pressure is stated, so the drop
    # itself is the answer.
    formula(
        "bernoulli_pressure_drop",
        "fluids",
        "Bernoulli's equation",
        r"\Delta P",
        base_latex=r"P_1 - P_2 = \tfrac{1}{2}\rho(v_2^2 - v_1^2)",
        assumptions=("horizontal, steady, incompressible flow with no viscosity",),
        expression="rho*(v_after**2 - v_before**2)/2",
        variables=(
            var(
                "rho",
                r"\rho",
                "kilogram / meter ** 3",
                words=("water", "liquid", "fluid", "oil", "density"),
                fallback="water_density",
                needs_words=True,
            ),
            var("v_before", "v_1", "meter / second", words=("from", "initial", "wide", "wider")),
            var("v_after", "v_2", "meter / second", words=("to", "final", "narrow", "narrower")),
        ),
        binding=Binding(
            asks=(
                "pressure drop",
                "drop in pressure",
                "pressure difference",
                "difference in pressure",
                "pressure change",
                "change in pressure",
                "fall in pressure",
            ),
            result=("pascal",),
            inputs=(frozenset({"rho", "v_after", "v_before"}),),
            # A height difference adds rho g Δh, which the horizontal form leaves out.
            cues=("horizontal",),
            excludes=("height", "higher", "lower", "rises", "climbs", "vertical", "uphill"),
            # Slowing down raises the pressure: not a drop.
            nonnegative=True,
        ),
    ),
    formula(
        "poiseuille_flow",
        "fluids",
        "Poiseuille's law",
        "Q",
        base_latex=r"Q = \frac{\pi r^4\Delta P}{8\eta L}",
        assumptions=("steady laminar flow in a straight pipe",),
        variables=(
            var("L", "L", "meter"),
            var("delta_pressure", r"\Delta P", "pascal"),
            var("r", "r", "meter"),
            var("viscosity", r"\eta", "pascal * second"),
        ),
    ),
    formula(
        "mass_flow_rate",
        "fluids",
        "Mass-flow-rate equation",
        "\\dot{m}",
        base_latex="\\dot{m} = \\rho Av",
        variables=(
            var("area", "A", "meter ** 2"),
            var("rho", r"\rho", "kilogram / meter ** 3"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "torricelli_speed",
        "fluids",
        "Torricelli's law",
        "v",
        base_latex="v = \\sqrt{2gh}",
        assumptions=("a wide tank open to the air, so the surface barely moves",),
        variables=(
            # How far below the surface the hole is: "a hole 3 m below the surface".
            # Only a depth under a liquid's surface: a hole 3 m deep is dug.
            var(
                "depth",
                "h",
                "meter",
                words=(
                    "below the surface",
                    "below the water surface",
                    "below the water level",
                    "below the water's surface",
                    "below the free surface",
                    "beneath the surface",
                    "under the surface",
                    "below the top of the water",
                ),
                needs_words=True,
            ),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
        ),
        # Water leaving a hole a depth below an open surface. The hole names the
        # law; a fall or a slide is energy conservation, not this.
        binding=Binding(
            asks=("how fast", "speed", "velocity", "efflux"),
            result=("meter / second",),
            inputs=(frozenset({"depth", "g"}),),
            cues=("hole", "leak", "orifice", "spout", "outlet", "opening", "tap"),
            excludes=(
                "pump",
                "pressure",
                "pipe",
                "hose",
                "dropped",
                "falls",
                "thrown",
                "dig",
                "drill",
            ),
            nonnegative=True,
        ),
    ),
    formula(
        "stokes_drag",
        "fluids",
        "Stokes' drag law",
        "F_d",
        base_latex="F_d = 6\\pi\\eta rv",
        variables=(
            var("r", "r", "meter"),
            var("v", "v", "meter / second"),
            var("viscosity", r"\eta", "pascal * second"),
        ),
    ),
    formula(
        "reynolds_number",
        "fluids",
        "Reynolds-number equation",
        "Re",
        base_latex="Re = \\frac{\\rho vL}{\\eta}",
        variables=(
            var("L", "L", "meter"),
            var("rho", r"\rho", "kilogram / meter ** 3"),
            var("v", "v", "meter / second"),
            var("viscosity", r"\eta", "pascal * second"),
        ),
    ),
    formula(
        "surface_tension",
        "fluids",
        "Surface-tension definition",
        "\\gamma",
        base_latex="\\gamma = \\frac{F}{L}",
        variables=(
            var("F", "F", "newton"),
            var("L", "L", "meter"),
        ),
    ),
    formula(
        "laplace_pressure",
        "fluids",
        "Young-Laplace equation",
        "\\Delta P",
        base_latex=r"\Delta P = \frac{2\gamma}{r}",
        variants=(
            FormulaVariant(
                equals=(("mode_factor", 4.0),),
                latex=r"\Delta P = \frac{4\gamma}{r}",
            ),
        ),
        variables=(
            var("mode_factor", "mode_factor", dimensionless=True, visible=False),
            var("r", "r", "meter"),
            var("surface_tension", r"\gamma", "newton / meter"),
        ),
    ),
    # ``k`` is the spring constant elsewhere, so the drag coefficient is ``drag_k``.
    formula(
        "linear_drag_fall",
        "fluids",
        "Linear drag under constant gravity",
        "v(t)",
        base_latex=r"v(t)=\frac{mg}{k}\left(1-e^{-(k/m)t}\right)",
        assumptions=(
            "Downward is positive",
            "Drag is -kv with k positive",
            "Released from rest unless a downward initial speed is given",
        ),
        variables=(
            var("drag_k", "k", "kilogram / second"),
            var("g", "g", "meter / second ** 2"),
            var("m", "m", "kilogram"),
            var("show_motion", "show_motion", dimensionless=True, visible=False),
            var("t", "t", "second"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "linear_drag_upward",
        "fluids",
        "Linear drag on an upward throw",
        "v(t)",
        base_latex=r"v(t)=-\frac{mg}{k}+\left(v_0+\frac{mg}{k}\right)e^{-(k/m)t}",
        assumptions=("Upward is positive", "Drag is -kv on the signed velocity"),
        variables=(
            var("drag_k", "k", "kilogram / second"),
            var("g", "g", "meter / second ** 2"),
            var("m", "m", "kilogram"),
            var("t", "t", "second"),
            var("v0", "v_0", "meter / second"),
        ),
    ),
    formula(
        "quadratic_drag_fall",
        "fluids",
        "Quadratic drag under constant gravity",
        "v(t)",
        base_latex=r"v(t)=v_T\tanh\left(\frac{gt}{v_T}\right),\quad v_T=\sqrt{\frac{mg}{b}}",
        assumptions=(
            "Downward is positive",
            "Drag is -bv^2 with b positive",
            "Released from rest",
        ),
        variables=(
            var("drag_b", "b", "kilogram / meter"),
            var("g", "g", "meter / second ** 2"),
            var("m", "m", "kilogram"),
            var("show_motion", "show_motion", dimensionless=True, visible=False),
            var("t", "t", "second"),
        ),
    ),
    formula(
        "stokes_terminal_velocity",
        "fluids",
        "Stokes terminal velocity",
        "v_T",
        base_latex=r"v_T=\frac{2r^{2}(\rho_{s}-\rho_{f})g}{9\eta}",
        assumptions=("Laminar flow around a sphere", "The sphere is denser than the fluid"),
        variables=(
            var("g", "g", "meter / second ** 2"),
            var("r", "r", "meter"),
            var("rho", r"\rho_f", "kilogram / meter ** 3"),
            var("rho_body", r"\rho_s", "kilogram / meter ** 3"),
            var("viscosity", r"\eta", "pascal * second"),
        ),
    ),
    formula(
        "quadratic_drag_force",
        "fluids",
        "Quadratic drag force",
        "F_D",
        base_latex=r"F_D = \frac{1}{2}C_D\rho A v^2",
        expression="0.5*drag_coefficient*rho*area*v**2",
        variables=(
            var(
                "drag_coefficient",
                "C_D",
                dimensionless=True,
                words=("coefficient",),
                needs_words=True,
            ),
            var("rho", r"\rho", "kilogram / meter ** 3"),
            var("area", "A", "meter ** 2"),
            var("v", "v", "meter / second"),
        ),
        binding=Binding(
            asks=("drag force", "drag"),
            result=("newton",),
            inputs=(frozenset({"area", "drag_coefficient", "rho", "v"}),),
            cues=("drag coefficient",),
            nonnegative=True,
        ),
    ),
    # A standing person or a resting block presses with its weight.
    formula(
        "pressure_from_weight",
        "fluids",
        "Pressure",
        "p",
        base_latex=r"p = \frac{m g}{A}",
        expression="m*g/area",
        variables=(
            var("m", "m", "kilogram"),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("area", "A", "meter ** 2"),
        ),
        binding=Binding(
            asks=("pressure",),
            result=("pascal",),
            inputs=(frozenset({"m", "g", "area"}),),
            cues=("stands", "standing", "rests", "resting", "exert", "exerts", "foot", "feet"),
            nonnegative=True,
        ),
    ),
    # The water's own pressure at a depth: p = rho g h, no atmosphere added.
    formula(
        "water_pressure_at_depth",
        "fluids",
        "Hydrostatic pressure",
        "p",
        base_latex=r"p = \rho g h",
        assumptions=("the pressure due to the water alone, without the atmosphere",),
        expression="rho*g*depth",
        variables=(
            var("rho", r"\rho", "kilogram / meter ** 3", fallback="water_density"),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("depth", "h", "meter"),
        ),
        binding=Binding(
            asks=("pressure", "water pressure"),
            result=("pascal",),
            inputs=(frozenset({"rho", "g", "depth"}),),
            cues=("deep", "depth", "bottom", "below the surface", "underwater"),
            excludes=("absolute", "total", "atmospheric", "stands", "exert"),
            nonnegative=True,
        ),
    ),
    # Archimedes: the upthrust is the weight of the water pushed aside.
    formula(
        "upthrust_from_volume",
        "fluids",
        "Archimedes' principle",
        "F_b",
        base_latex=r"F_b = \rho g V",
        expression="rho*g*volume",
        variables=(
            var("rho", r"\rho", "kilogram / meter ** 3", fallback="water_density"),
            var("g", "g", "meter / second ** 2", fallback="gravity"),
            var("volume", "V", "meter ** 3"),
        ),
        binding=Binding(
            asks=("upthrust", "buoyant force", "buoyancy force", "buoyancy"),
            result=("newton",),
            inputs=(frozenset({"rho", "g", "volume"}),),
            cues=("submerged", "immersed", "under water", "underwater", "in water", "fully"),
            # A floating body displaces less than its own volume.
            excludes=("floating", "floats", "float"),
            nonnegative=True,
        ),
    ),
)
