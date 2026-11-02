"""Verified modern operations."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, bind, formula, var

# A half-life and the time that has passed are both times: the words say which.
HALF_LIFE = var("half_life", r"T_{1/2}", "second", words=("half-life", "half life"))
ELAPSED = var("elapsed", "t", "second", words=("after", "elapsed", "later", "in", "for"))
HALF_LIFE_CUES = ("half-life", "half life")

SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "half_life_remaining",
        "modern",
        "Radioactive-decay law",
        "N",
        variables=(
            ELAPSED,
            HALF_LIFE,
            var("m", "m", "kilogram"),
            var("n_halves", "n", dimensionless=True),
        ),
        binding=bind(
            ("mass remaining", "mass left", "remains", "remaining", "left"),
            "kilogram",
            "elapsed",
            "half_life",
            "m",
            cues=HALF_LIFE_CUES,
        ),
    ),
    formula(
        "mass_energy",
        "modern",
        "Mass-energy equivalence",
        "E",
        variables=(var("m", "m", "kilogram"),),
    ),
    formula(
        "photon_energy",
        "modern",
        "Photon-energy relation",
        "E",
        variables=(
            var("freq", "f", "hertz"),
            var("wavelength", r"\lambda", "meter"),
        ),
        # "the energy of a 1.2 µm infrared photon": a photon named by its
        # wavelength, without the word. The solver gives J and again eV.
        binding=Binding(
            asks=(
                "energy of the photon",
                "energy of a photon",
                "energy of each photon",
                "photon energy",
                "energy",
            ),
            result=("joule", "joule"),
            inputs=(frozenset({"wavelength"}), frozenset({"freq"})),
            cues=("photon",),
            excludes=(
                "momentum",
                "work function",
                "photoelectr",
                "kinetic",
                "stopping",
                "threshold",
                "photons",
                "per second",
                "power",
            ),
            nonnegative=True,
        ),
    ),
    formula(
        "de_broglie_wavelength",
        "modern",
        "de Broglie relation",
        "\\lambda",
        variables=(
            var("m", "m", "kilogram"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "lorentz_factor",
        "modern",
        "Lorentz-factor equation",
        "\\gamma",
        base_latex="\\gamma = \\frac{1}{\\sqrt{1-v^2/c^2}}",
        variables=(var("v", "v", "meter / second"),),
    ),
    formula(
        "time_dilation",
        "modern",
        "Relativistic time dilation",
        "\\Delta t",
        base_latex="\\Delta t = \\gamma\\Delta t_0",
        variables=(
            var("proper_time", r"\Delta t_0", "second"),
            var("v", "v", "meter / second"),
        ),
        # "A muon at 0.98c lives 2.2 µs at rest: its lifetime in the lab?" A
        # speed written onto c names light's speed, the cue relativity reads.
        binding=Binding(
            asks=(
                "lifetime measured",
                "lifetime in the lab",
                "lifetime as measured",
                "measured lifetime",
                "observed lifetime",
                "lifetime observed",
                "dilated lifetime",
                "dilated time",
                "time measured",
                "time in the lab",
                "lifetime",
            ),
            result=("second",),
            inputs=(frozenset({"proper_time", "v"}),),
            cues=("speed of light",),
            excludes=("half-life", "half life", "length", "contract"),
            nonnegative=True,
        ),
    ),
    formula(
        "length_contraction",
        "modern",
        "Relativistic length contraction",
        "L",
        base_latex="L = \\frac{L_0}{\\gamma}",
        variables=(
            var("proper_length", "L_0", "meter"),
            var("v", "v", "meter / second"),
        ),
    ),
    formula(
        "photoelectric_kinetic_energy_wavelength",
        "modern",
        "Photoelectric equation",
        "K_{max}",
        base_latex=r"K_{max} = \frac{hc}{\lambda} - \phi",
        expression="h_planck*c_light/wavelength - work_function",
        variables=(
            var("wavelength", r"\lambda", "meter"),
            var("work_function", r"\phi", "joule"),
        ),
        binding=Binding(
            asks=(
                "maximum kinetic energy",
                "max kinetic energy",
                "maximum ke",
                "max ke",
                "kinetic energy",
                "energy of the photoelectrons",
            ),
            result=("joule",),
            inputs=(frozenset({"wavelength", "work_function"}),),
            cues=("work function",),
            nonnegative=True,
            shown_unit="eV",
        ),
    ),
    formula(
        "photoelectric_kinetic_energy",
        "modern",
        "Photoelectric equation",
        "K_{max}",
        base_latex="K_{max} = hf - \\phi",
        variables=(
            var("freq", "f", "hertz"),
            var("work_function", r"\phi", "joule"),
        ),
        # The solver gives the energy in J and again in eV.
        binding=Binding(
            asks=(
                "maximum kinetic energy",
                "max kinetic energy",
                "maximum ke",
                "max ke",
                "kinetic energy",
                "energy of the photoelectrons",
            ),
            result=("joule", "joule"),
            inputs=(frozenset({"freq", "work_function"}),),
            cues=("work function",),
            nonnegative=True,
        ),
    ),
    formula(
        "uncertainty_momentum",
        "modern",
        "Heisenberg uncertainty principle",
        "\\Delta p_{min}",
        base_latex="\\Delta p_{min} = \\frac{\\hbar}{2\\Delta x}",
        variables=(var("uncertainty_x", r"\Delta x", "meter"),),
    ),
    formula(
        "particle_box_energy",
        "modern",
        "Infinite-square-well energy",
        "E_n",
        base_latex="E_n = \\frac{n^2h^2}{8mL^2}",
        variables=(
            var("L", "L", "meter"),
            var("m", "m", "kilogram"),
            var("quantum_n", "n", dimensionless=True),
        ),
    ),
    formula(
        "hydrogen_energy_level",
        "modern",
        "Hydrogen energy-level equation",
        "E_n",
        base_latex="E_n = -\\frac{13.6\\,\\mathrm{eV}}{n^2}",
        variables=(var("quantum_n", "n", dimensionless=True),),
    ),
    formula(
        "compton_shift",
        "modern",
        "Compton-scattering equation",
        "\\Delta\\lambda",
        base_latex="\\Delta\\lambda = \\frac{h}{m_ec}(1-\\cos\\theta)",
        variables=(var("angle", r"\theta", dimensionless=True),),
    ),
    formula(
        "wien_peak",
        "modern",
        "Wien's displacement law",
        "\\lambda_{max}",
        base_latex="\\lambda_{max}T = b",
        variables=(var("temp", "T", "kelvin"),),
    ),
    formula(
        "stefan_boltzmann_power",
        "modern",
        "Stefan-Boltzmann law",
        "P",
        base_latex="P = \\epsilon\\sigma AT^4",
        variables=(
            var("area", "A", "meter ** 2"),
            var("emissivity", r"\epsilon", dimensionless=True),
            var("temp", "T", "kelvin"),
        ),
    ),
    formula(
        "net_blackbody_power",
        "modern",
        "Net blackbody power",
        "P",
        base_latex=r"P = \varepsilon\sigma A(T^4 - T_0^4)",
        assumptions=("the surroundings are a black enclosure",),
        expression="emissivity*sigma*area*(temp**4 - temp_env**4)",
        variables=(
            var(
                "emissivity",
                r"\varepsilon",
                dimensionless=True,
                words=("emissivity",),
                needs_words=True,
            ),
            var("area", "A", "meter ** 2", words=("area",), needs_words=True),
            var(
                "temp",
                "T",
                "kelvin",
                words=("body", "surface"),
                needs_words=True,
            ),
            var(
                "temp_env",
                "T_0",
                "kelvin",
                words=("surroundings", "ambient", "environment"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("net radiated power", "net power"),
            result=("watt",),
            inputs=(frozenset({"area", "emissivity", "temp", "temp_env"}),),
            cues=("blackbody", "stefan"),
            nonnegative=False,
        ),
    ),
    # E = mc^2, for a mass turned wholly into energy.
    formula(
        "mass_energy_equivalence",
        "modern",
        "Mass-energy equivalence",
        "E",
        base_latex=r"E = m c^2",
        expression="m*c_light**2",
        variables=(var("m", "m", "kilogram"),),
        binding=Binding(
            asks=("energy", "how much energy", "energy released"),
            result=("joule",),
            inputs=(frozenset({"m"}),),
            cues=(
                "converted",
                "into energy",
                "to energy",
                "annihilat",
                "e=mc",
                "rest energy",
                "equivalent",
                # "0.003 u of mass is lost": the mass a reaction gives up.
                "mass is lost",
                "mass lost",
                "mass defect",
                "loses mass",
            ),
            nonnegative=True,
        ),
    ),
)
