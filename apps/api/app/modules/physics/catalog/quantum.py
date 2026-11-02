"""Verified quantum operations: photons, the photoelectric effect, atoms, statistics."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, FormulaVariant, formula, var

_FREQ = var("freq", "f", "hertz")
_WAVELENGTH = var("wavelength", r"\lambda", "meter")
_WORK_FUNCTION = var("work_function", r"\phi", "joule")
_PHOTOELECTRIC = ("work function", "photoelectr", "metal surface")
_HYDROGEN = ("hydrogen",)
# "falls from n = 3 to n = 2": either order is one photon of one energy.
_N_UPPER = var("n_upper", "n_u", dimensionless=True, words=("from",))
_N_LOWER = var("n_lower", "n_l", dimensionless=True, words=("to",))
_LEVELS = r"\left(\frac{1}{n_l^2} - \frac{1}{n_u^2}\right)"
_LEVELS_EXPRESSION = "(1/n_lower**2 - 1/n_upper**2)"


def _transition(
    operation: str,
    symbol: str,
    base: str,
    expression: str,
    asks: tuple[str, ...],
    result: str,
) -> FormulaSpec:
    return formula(
        operation,
        "modern",
        "Rydberg formula",
        symbol,
        base_latex=base,
        assumptions=("hydrogen, infinite nuclear mass",),
        expression=expression,
        variables=(_N_LOWER, _N_UPPER),
        binding=Binding(
            asks=asks,
            result=(result,),
            inputs=(frozenset({"n_lower", "n_upper"}),),
            cues=_HYDROGEN,
            excludes=("hydrogen-like", "hydrogenic", "atomic number"),
            descending=("n_upper", "n_lower"),
            nonnegative=True,
        ),
    )


_FIELD_B = var("b_field", "B", "tesla")

_LEVEL = var(
    "quantum_n",
    "n",
    dimensionless=True,
    words=("n =", "principal"),
    needs_words=True,
)


SPECS: tuple[FormulaSpec, ...] = (
    # "a 5 mW laser of 630 nm: how many photons per second?" The power over one
    # photon's energy.
    formula(
        "photon_emission_rate",
        "modern",
        "Photon-energy relation",
        r"\frac{N}{t}",
        base_latex=r"\frac{N}{t} = \frac{P\lambda}{hc}",
        expression="power*wavelength/(h_planck*c_light)",
        variants=(
            FormulaVariant(
                present=frozenset({"freq"}),
                latex=r"\frac{N}{t} = \frac{P}{hf}",
                expression="power/(h_planck*freq)",
            ),
        ),
        variables=(var("power", "P", "watt"), _FREQ, _WAVELENGTH),
        binding=Binding(
            asks=(
                "how many photons",
                "number of photons",
                "photons per second",
                "photons each second",
                "photon emission rate",
                "rate of photon emission",
            ),
            result=("1 / second",),
            inputs=(frozenset({"power", "wavelength"}), frozenset({"power", "freq"})),
            cues=("photon",),
            nonnegative=True,
            shown_unit="photons/s",
        ),
    ),
    # "an electron accelerated through 150 V": qV of kinetic energy, so
    # p = sqrt(2mqV). Past 2% of the rest energy the classical momentum is
    # off by more than half a percent, and the law declines.
    formula(
        "de_broglie_from_voltage",
        "modern",
        "de Broglie relation",
        r"\lambda",
        base_latex=r"\lambda = \frac{h}{\sqrt{2mqV}}",
        assumptions=("starts from rest; non-relativistic",),
        expression="h_planck/sqrt(2*m*Q*V)",
        variables=(
            var("m", "m", "kilogram", fallback="particle_mass"),
            var("Q", "q", "coulomb", fallback="particle_charge"),
            var("V", "V", "volt"),
        ),
        binding=Binding(
            asks=("de broglie wavelength", "wavelength"),
            result=("meter",),
            inputs=(frozenset({"m", "Q", "V"}),),
            cues=(
                "accelerated through",
                "accelerated by",
                "accelerated across",
                "through a potential",
                "potential difference",
            ),
            excludes=("photon",),
            requires=("0.02*m*c_light**2 - Q*V", "V"),
            nonnegative=True,
        ),
    ),
    formula(
        "photon_momentum",
        "modern",
        "Photon momentum",
        "p",
        base_latex=r"p = \frac{h}{\lambda}",
        expression="h_planck/wavelength",
        variants=(
            FormulaVariant(
                present=frozenset({"freq"}),
                latex=r"p = \frac{hf}{c}",
                expression="h_planck*freq/c_light",
            ),
        ),
        variables=(_FREQ, _WAVELENGTH),
        binding=Binding(
            asks=("momentum",),
            result=("kilogram * meter / second",),
            inputs=(frozenset({"wavelength"}), frozenset({"freq"})),
            cues=("photon", "light"),
            nonnegative=True,
        ),
    ),
    formula(
        "threshold_frequency",
        "modern",
        "Photoelectric threshold",
        "f_0",
        base_latex=r"hf_0 = \phi",
        expression="work_function/h_planck",
        variables=(_WORK_FUNCTION,),
        binding=Binding(
            asks=(
                "threshold frequency",
                "minimum frequency",
                "cut-off frequency",
                "cutoff frequency",
            ),
            result=("hertz",),
            inputs=(frozenset({"work_function"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "threshold_wavelength",
        "modern",
        "Photoelectric threshold",
        r"\lambda_0",
        base_latex=r"\frac{hc}{\lambda_0} = \phi",
        expression="h_planck*c_light/work_function",
        variables=(_WORK_FUNCTION,),
        binding=Binding(
            asks=(
                "threshold wavelength",
                "maximum wavelength",
                "longest wavelength",
                "cut-off wavelength",
                "cutoff wavelength",
            ),
            result=("meter",),
            inputs=(frozenset({"work_function"}),),
            nonnegative=True,
        ),
    ),
    formula(
        "stopping_potential",
        "modern",
        "Photoelectric equation",
        "V_s",
        base_latex=r"eV_s = hf - \phi",
        expression="(h_planck*freq - work_function)/e_charge",
        variants=(
            FormulaVariant(
                present=frozenset({"wavelength"}),
                latex=r"eV_s = \frac{hc}{\lambda} - \phi",
                expression="(h_planck*c_light/wavelength - work_function)/e_charge",
            ),
        ),
        variables=(_FREQ, _WAVELENGTH, _WORK_FUNCTION),
        binding=Binding(
            asks=("stopping potential", "stopping voltage"),
            result=("volt",),
            inputs=(
                frozenset({"freq", "work_function"}),
                frozenset({"wavelength", "work_function"}),
            ),
            cues=_PHOTOELECTRIC,
            # Below the threshold no electron leaves, so there is nothing to stop.
            nonnegative=True,
        ),
    ),
    formula(
        "quantum_oscillator_energy",
        "modern",
        "Quantum harmonic oscillator",
        "E_n",
        base_latex=r"E_n = \left(n + \tfrac{1}{2}\right)\hbar\omega",
        expression="(quantum_n + 1/2)*hbar*omega",
        variants=(
            FormulaVariant(
                present=frozenset({"freq"}),
                latex=r"E_n = \left(n + \tfrac{1}{2}\right)hf",
                expression="(quantum_n + 1/2)*h_planck*freq",
            ),
        ),
        variables=(
            _FREQ,
            var("omega", r"\omega", "radian / second"),
            var(
                "quantum_n",
                "n",
                dimensionless=True,
                implied=(
                    ("ground state", 0.0),
                    ("first excited state", 1.0),
                    ("second excited state", 2.0),
                    ("third excited state", 3.0),
                ),
            ),
        ),
        binding=Binding(
            asks=("energy",),
            result=("joule",),
            inputs=(frozenset({"omega", "quantum_n"}), frozenset({"freq", "quantum_n"})),
            cues=("harmonic oscillator", "quantum oscillator"),
            nonnegative=True,
        ),
    ),
    _transition(
        "hydrogen_transition_wavelength",
        r"\lambda",
        rf"\frac{{1}}{{\lambda}} = R_\infty{_LEVELS}",
        f"1/(R_inf*{_LEVELS_EXPRESSION})",
        ("wavelength",),
        "meter",
    ),
    _transition(
        "hydrogen_transition_energy",
        r"\Delta E",
        rf"\Delta E = hcR_\infty{_LEVELS}",
        f"h_planck*c_light*R_inf*{_LEVELS_EXPRESSION}",
        ("energy",),
        "joule",
    ),
    formula(
        "bohr_orbit_radius",
        "modern",
        "Bohr model",
        "r_n",
        base_latex=r"r_n = n^2 a_0",
        assumptions=("hydrogen",),
        expression="quantum_n**2*a_0",
        variables=(
            var(
                "quantum_n",
                "n",
                dimensionless=True,
                implied=(("ground state", 1.0), ("first excited state", 2.0)),
            ),
        ),
        binding=Binding(
            asks=("radius", "orbit radius", "orbital radius"),
            result=("meter",),
            inputs=(frozenset({"quantum_n"}),),
            cues=("bohr", "hydrogen"),
            excludes=("hydrogen-like", "hydrogenic", "atomic number"),
            nonnegative=True,
        ),
    ),
    formula(
        "boltzmann_population_ratio",
        "modern",
        "Boltzmann distribution",
        r"\frac{N_2}{N_1}",
        base_latex=r"\frac{N_2}{N_1} = e^{-\Delta E/k_B T}",
        assumptions=("two non-degenerate levels in thermal equilibrium",),
        expression="exp(-energy_gap/(k_B*temp))",
        variables=(var("energy_gap", r"\Delta E", "joule"), var("temp", "T", "kelvin")),
        binding=Binding(
            asks=("ratio", "population ratio", "fraction"),
            result=("dimensionless",),
            inputs=(frozenset({"energy_gap", "temp"}),),
            cues=("boltzmann", "population"),
            nonnegative=True,
        ),
    ),
    formula(
        "boltzmann_entropy",
        "modern",
        "Boltzmann entropy",
        "S",
        base_latex=r"S = k_B \ln \Omega",
        expression="k_B*log(microstates)",
        variables=(var("microstates", r"\Omega", dimensionless=True),),
        binding=Binding(
            asks=("entropy",),
            result=("joule / kelvin",),
            inputs=(frozenset({"microstates"}),),
            cues=("microstate",),
            nonnegative=True,
        ),
    ),
    formula(
        "energy_time_uncertainty",
        "modern",
        "Heisenberg uncertainty principle",
        r"\Delta E_{min}",
        base_latex=r"\Delta E \, \Delta t \geq \frac{\hbar}{2}",
        expression="hbar/(2*dt)",
        variables=(var("dt", r"\Delta t", "second"),),
        binding=Binding(
            asks=(
                "uncertainty in energy",
                "uncertainty in the energy",
                "energy uncertainty",
                "minimum uncertainty",
                "energy width",
            ),
            result=("joule",),
            inputs=(frozenset({"dt"}),),
            cues=("uncertainty", "lifetime"),
            nonnegative=True,
        ),
    ),
    formula(
        "hydrogenlike_energy",
        "modern",
        "Hydrogen-like energy level",
        "E_n",
        base_latex=r"E_n = -\frac{13.6\,Z^2}{n^2}\,\mathrm{eV}",
        assumptions=("infinite nuclear mass",),
        expression="-13.6*e_charge*atomic_number**2/quantum_n**2",
        variables=(
            var(
                "atomic_number",
                "Z",
                dimensionless=True,
                words=("atomic number", "z"),
                needs_words=True,
            ),
            var("quantum_n", "n", dimensionless=True, words=("n",), needs_words=True),
        ),
        binding=Binding(
            asks=("energy",),
            result=("joule",),
            inputs=(frozenset({"atomic_number", "quantum_n"}),),
            cues=("hydrogen-like", "hydrogenic"),
            excludes=("transition", "wavelength"),
            nonnegative=False,
        ),
    ),
    formula(
        "planck_spectral_radiance",
        "modern",
        "Planck's law",
        r"B_\lambda",
        base_latex=r"B_\lambda = \frac{2hc^2}{\lambda^5}\frac{1}{e^{hc/\lambda kT}-1}",
        assumptions=("spectral radiance per steradian, wavelength form",),
        expression=(
            "2*h_planck*c_light**2/wavelength**5/(exp(h_planck*c_light/(wavelength*k_B*temp))-1)"
        ),
        variables=(
            var("wavelength", r"\lambda", "meter", words=("wavelength",), needs_words=True),
            var("temp", "T", "kelvin", words=("temperature",), needs_words=True),
        ),
        binding=Binding(
            asks=("spectral radiance",),
            result=("watt / meter ** 3",),
            inputs=(frozenset({"temp", "wavelength"}),),
            cues=("planck", "blackbody distribution"),
            excludes=("photon",),
            nonnegative=True,
        ),
    ),
    formula(
        "tunnel_probability",
        "modern",
        "Tunneling probability",
        "T",
        base_latex=r"T \approx \exp\left(-\frac{2L}{\hbar}\sqrt{2m(U-E)}\right)",
        assumptions=("a rectangular barrier with E < U; the prefactor is omitted",),
        expression="exp(-2*barrier_width*sqrt(2*m*(barrier_height-particle_energy))/hbar)",
        variables=(
            var("m", "m", "kilogram", fallback="particle_mass"),
            var(
                "barrier_height",
                "U",
                "joule",
                words=("barrier", "height"),
                needs_words=True,
            ),
            var(
                "particle_energy",
                "E",
                "joule",
                words=("energy", "kinetic"),
                needs_words=True,
            ),
            var(
                "barrier_width",
                "L",
                "meter",
                words=("wide", "width", "thick"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("tunneling probability", "transmission probability"),
            result=("dimensionless",),
            inputs=(frozenset({"barrier_height", "barrier_width", "m", "particle_energy"}),),
            cues=("tunnel",),
            nonnegative=True,
            at_most=1.0,
        ),
    ),
    formula(
        "bohr_angular_momentum",
        "modern",
        "Bohr angular momentum",
        "L",
        base_latex=r"L = n\hbar",
        assumptions=("the Bohr model",),
        expression="quantum_n*hbar",
        variables=(
            var(
                "quantum_n",
                "n",
                dimensionless=True,
                words=("n =", "level"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("angular momentum",),
            result=("kilogram * meter ** 2 / second",),
            inputs=(frozenset({"quantum_n"}),),
            cues=("bohr",),
            excludes=("squared", "z component"),
            nonnegative=True,
        ),
    ),
    formula(
        "orbital_angular_momentum_squared",
        "modern",
        "Orbital angular-momentum eigenvalue",
        "L^2",
        base_latex=r"L^2 = \hbar^2 \ell(\ell+1)",
        assumptions=("one orbital angular-momentum eigenvalue",),
        expression="hbar**2*orbital_l*(orbital_l+1)",
        variables=(
            var(
                "orbital_l",
                r"\ell",
                dimensionless=True,
                words=("orbital", "azimuthal"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("angular momentum squared",),
            result=("kilogram ** 2 * meter ** 4 / second ** 2",),
            inputs=(frozenset({"orbital_l"}),),
            cues=("orbital quantum", "azimuthal"),
            nonnegative=True,
        ),
    ),
    formula(
        "angular_momentum_z",
        "modern",
        "Angular-momentum z component",
        "L_z",
        base_latex=r"L_z = m\hbar",
        assumptions=("the z component",),
        expression="magnetic_quantum*hbar",
        variables=(
            var(
                "magnetic_quantum",
                "m",
                dimensionless=True,
                words=("magnetic quantum",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("z component of angular momentum",),
            result=("kilogram * meter ** 2 / second",),
            inputs=(frozenset({"magnetic_quantum"}),),
            cues=("magnetic quantum",),
            excludes=("zeeman",),
            nonnegative=False,
        ),
    ),
    formula(
        "hydrogenlike_radius",
        "modern",
        "Hydrogen-like Bohr radius",
        "r_n",
        base_latex=r"r_n = \frac{n^2 a_0}{Z}",
        assumptions=("a hydrogen-like atom, infinite nuclear mass",),
        expression="quantum_n**2*a_0/atomic_number",
        variables=(
            _LEVEL,
            var(
                "atomic_number",
                "Z",
                dimensionless=True,
                words=("atomic number", "z ="),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("orbit radius", "orbital radius", "radius"),
            result=("meter",),
            inputs=(frozenset({"atomic_number", "quantum_n"}),),
            cues=("hydrogen-like", "hydrogenic", "atomic number"),
            nonnegative=True,
        ),
    ),
    formula(
        "zeeman_shift",
        "modern",
        "Normal Zeeman shift",
        r"\Delta E",
        base_latex=r"\Delta E = \frac{e\hbar B m_l}{2 m_e}",
        assumptions=("the normal Zeeman effect",),
        expression="e_charge*hbar*b_field*magnetic_quantum/(2*m_e)",
        variables=(
            _FIELD_B,
            var(
                "magnetic_quantum",
                "m_l",
                dimensionless=True,
                words=("magnetic quantum",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("zeeman shift",),
            result=("joule",),
            inputs=(frozenset({"b_field", "magnetic_quantum"}),),
            cues=("zeeman",),
            nonnegative=False,
        ),
    ),
)
