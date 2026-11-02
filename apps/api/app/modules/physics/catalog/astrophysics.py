"""Stars, black holes and cosmology: luminosity, Hawking radiation, Hubble's law
and the critical density, the virial theorem."""

from __future__ import annotations

from app.services.law_binding.spec import Binding, FormulaSpec, formula, var

_DENSITY = var("rho", r"\rho", "kilogram / meter ** 3", words=("density",), needs_words=True)


SPECS: tuple[FormulaSpec, ...] = (
    formula(
        "hawking_power",
        "modern",
        "Hawking power",
        "P",
        base_latex=r"P = \frac{\hbar c^6}{15360\pi G^2 M^2}",
        assumptions=("a Schwarzschild black hole",),
        expression="hbar*c_light**6/(15360*pi*G_grav**2*M**2)",
        variables=(var("M", "M", "kilogram", fallback="body_mass"),),
        binding=Binding(
            asks=("hawking power", "hawking luminosity"),
            result=("watt",),
            inputs=(frozenset({"M"}),),
            cues=("hawking power", "hawking luminosity"),
            nonnegative=True,
        ),
    ),
    formula(
        "friedmann_hubble",
        "gravitation",
        "Friedmann equation",
        "H",
        base_latex=r"H = \sqrt{\frac{8\pi G\rho}{3} - \frac{kc^2}{a^2} + \frac{\Lambda c^2}{3}}",
        assumptions=("the Hubble parameter from the stated density, curvature, scale, and Lambda",),
        expression=(
            "sqrt(8*pi*G_grav*rho/3 - curvature*c_light**2/scale_factor**2"
            " + lambda_cosmo*c_light**2/3)"
        ),
        variables=(
            _DENSITY,
            var(
                "curvature",
                "k",
                dimensionless=True,
                words=("curvature",),
                needs_words=True,
            ),
            var("scale_factor", "a", "meter", words=("scale",), needs_words=True),
            var(
                "lambda_cosmo",
                r"\Lambda",
                "1 / meter ** 2",
                words=("cosmological",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("hubble parameter",),
            result=("1 / second",),
            inputs=(frozenset({"curvature", "lambda_cosmo", "rho", "scale_factor"}),),
            cues=("friedmann",),
            nonnegative=True,
        ),
    ),
    formula(
        "virial_kinetic_energy",
        "gravitation",
        "Virial theorem",
        "K",
        base_latex=r"2K + U = 0",
        assumptions=("a self-gravitating system in equilibrium",),
        expression="-potential_energy/2",
        variables=(var("potential_energy", "U", "joule", words=("potential",), needs_words=True),),
        binding=Binding(
            asks=("kinetic energy",),
            result=("joule",),
            inputs=(frozenset({"potential_energy"}),),
            cues=("virial",),
            nonnegative=False,
        ),
    ),
    formula(
        "virial_potential_energy",
        "gravitation",
        "Virial theorem",
        "U",
        base_latex=r"2K + U = 0",
        assumptions=("a self-gravitating system in equilibrium",),
        expression="-2*kinetic_energy",
        variables=(var("kinetic_energy", "K", "joule", words=("kinetic",), needs_words=True),),
        binding=Binding(
            asks=("potential energy",),
            result=("joule",),
            inputs=(frozenset({"kinetic_energy"}),),
            cues=("virial",),
            nonnegative=False,
        ),
    ),
    formula(
        "hubble_law",
        "gravitation",
        "Hubble's law",
        "v",
        base_latex=r"v = H_0 d",
        expression="hubble_constant*galaxy_distance",
        variables=(
            var(
                "hubble_constant",
                "H_0",
                "1 / second",
                words=("hubble",),
                needs_words=True,
            ),
            var(
                "galaxy_distance",
                "d",
                "meter",
                words=("distance", "away"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("recessional speed", "recession speed", "speed"),
            result=("meter / second",),
            inputs=(frozenset({"galaxy_distance", "hubble_constant"}),),
            cues=("hubble",),
            excludes=("critical density",),
            nonnegative=True,
        ),
    ),
    formula(
        "critical_density",
        "gravitation",
        "Critical density",
        r"\rho_c",
        base_latex=r"\rho_c = \frac{3H^2}{8\pi G}",
        expression="3*hubble_constant**2/(8*pi*G_grav)",
        variables=(
            var(
                "hubble_constant",
                "H",
                "1 / second",
                words=("hubble",),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("critical density",),
            result=("kilogram / meter ** 3",),
            inputs=(frozenset({"hubble_constant"}),),
            cues=("critical density",),
            nonnegative=True,
        ),
    ),
    formula(
        "stellar_luminosity",
        "modern",
        "Stellar luminosity",
        "L",
        base_latex=r"L = 4\pi R^2\sigma T^4",
        assumptions=("a black spherical star",),
        expression="4*pi*star_radius**2*sigma*temp**4",
        variables=(
            var("star_radius", "R", "meter", words=("radius",), needs_words=True),
            var("temp", "T", "kelvin", words=("temperature",), needs_words=True),
        ),
        binding=Binding(
            asks=("luminosity",),
            result=("watt",),
            inputs=(frozenset({"star_radius", "temp"}),),
            cues=("star", "stellar"),
            nonnegative=True,
        ),
    ),
    formula(
        "luminosity_flux",
        "modern",
        "Flux from a point source",
        "F",
        base_latex=r"F = \frac{L}{4\pi r^2}",
        expression="luminosity/(4*pi*star_distance**2)",
        variables=(
            var("luminosity", "L", "watt", words=("luminosity",), needs_words=True),
            var(
                "star_distance",
                "r",
                "meter",
                words=("distance", "away"),
                needs_words=True,
            ),
        ),
        binding=Binding(
            asks=("radiant flux", "flux"),
            result=("watt / meter ** 2",),
            inputs=(frozenset({"luminosity", "star_distance"}),),
            cues=("luminosity",),
            nonnegative=True,
        ),
    ),
    formula(
        "hawking_temperature",
        "modern",
        "Hawking temperature",
        "T_H",
        base_latex=r"T_H = \frac{\hbar c^3}{8\pi G M k_B}",
        expression="hbar*c_light**3/(8*pi*G_grav*M*k_B)",
        variables=(var("M", "M", "kilogram", fallback="body_mass"),),
        binding=Binding(
            asks=("hawking temperature", "temperature"),
            result=("kelvin",),
            inputs=(frozenset({"M"}),),
            cues=("hawking",),
            nonnegative=True,
        ),
    ),
    formula(
        "bekenstein_entropy",
        "modern",
        "Bekenstein-Hawking entropy",
        "S",
        base_latex=r"S = \frac{k_B c^3 A}{4 G \hbar}",
        expression="k_B*c_light**3*area/(4*G_grav*hbar)",
        variables=(var("area", "A", "meter ** 2", words=("area",), needs_words=True),),
        binding=Binding(
            asks=("entropy",),
            result=("joule / kelvin",),
            inputs=(frozenset({"area"}),),
            cues=("bekenstein", "black hole entropy", "black-hole entropy"),
            nonnegative=True,
        ),
    ),
)
