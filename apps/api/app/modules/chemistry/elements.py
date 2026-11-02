"""Complete periodic table used by formula, structure, and element lookup.

Masses for the elements that already shipped stay at those exact values.
A mass marked with ``*`` in the source table is the mass number of a
long-lived isotope, not a CIAAW standard atomic weight. Noble gases with no
Pauling electronegativity omit that field (helium must not become 0).
"""

from __future__ import annotations

from dataclasses import dataclass

# number|symbol|name|mass|period|group|electronegativity|oxidation states|configuration
# Empty group or electronegativity means the value is not assigned.
# f-block elements other than La and Ac have no group.
_ROWS = """
1|H|Hydrogen|1.008|1|1|2.20|1,-1|1s1
2|He|Helium|4.003|1|18|| |1s2
3|Li|Lithium|6.941|2|1|0.98|1|[He] 2s1
4|Be|Beryllium|9.012|2|2|1.57|2|[He] 2s2
5|B|Boron|10.811|2|13|2.04|3|[He] 2s2 2p1
6|C|Carbon|12.011|2|14|2.55|-4,2,4|[He] 2s2 2p2
7|N|Nitrogen|14.007|2|15|3.04|-3,3,5|[He] 2s2 2p3
8|O|Oxygen|15.999|2|16|3.44|-2,-1|[He] 2s2 2p4
9|F|Fluorine|18.998|2|17|3.98|-1|[He] 2s2 2p5
10|Ne|Neon|20.180|2|18|| |[He] 2s2 2p6
11|Na|Sodium|22.990|3|1|0.93|1|[Ne] 3s1
12|Mg|Magnesium|24.305|3|2|1.31|2|[Ne] 3s2
13|Al|Aluminum|26.982|3|13|1.61|3|[Ne] 3s2 3p1
14|Si|Silicon|28.085|3|14|1.90|4|[Ne] 3s2 3p2
15|P|Phosphorus|30.974|3|15|2.19|-3,3,5|[Ne] 3s2 3p3
16|S|Sulfur|32.06|3|16|2.58|-2,4,6|[Ne] 3s2 3p4
17|Cl|Chlorine|35.45|3|17|3.16|-1,1,5,7|[Ne] 3s2 3p5
18|Ar|Argon|39.948|3|18|| |[Ne] 3s2 3p6
19|K|Potassium|39.098|4|1|0.82|1|[Ar] 4s1
20|Ca|Calcium|40.078|4|2|1.00|2|[Ar] 4s2
21|Sc|Scandium|44.956|4|3|1.36|3|[Ar] 3d1 4s2
22|Ti|Titanium|47.867|4|4|1.54|4|[Ar] 3d2 4s2
23|V|Vanadium|50.942|4|5|1.63|5|[Ar] 3d3 4s2
24|Cr|Chromium|51.996|4|6|1.66|3,6|[Ar] 3d5 4s1
25|Mn|Manganese|54.938|4|7|1.55|2,4,7|[Ar] 3d5 4s2
26|Fe|Iron|55.845|4|8|1.83|2,3|[Ar] 3d6 4s2
27|Co|Cobalt|58.933|4|9|1.88|2,3|[Ar] 3d7 4s2
28|Ni|Nickel|58.693|4|10|1.91|2|[Ar] 3d8 4s2
29|Cu|Copper|63.546|4|11|1.90|1,2|[Ar] 3d10 4s1
30|Zn|Zinc|65.38|4|12|1.65|2|[Ar] 3d10 4s2
31|Ga|Gallium|69.723|4|13|1.81|3|[Ar] 3d10 4s2 4p1
32|Ge|Germanium|72.63|4|14|2.01|4|[Ar] 3d10 4s2 4p2
33|As|Arsenic|74.922|4|15|2.18|-3,3,5|[Ar] 3d10 4s2 4p3
34|Se|Selenium|78.96|4|16|2.55|-2,4,6|[Ar] 3d10 4s2 4p4
35|Br|Bromine|79.904|4|17|2.96|-1,1,5|[Ar] 3d10 4s2 4p5
36|Kr|Krypton|83.798|4|18|3.00||[Ar] 3d10 4s2 4p6
37|Rb|Rubidium|85.468|5|1|0.82|1|[Kr] 5s1
38|Sr|Strontium|87.62|5|2|0.95|2|[Kr] 5s2
39|Y|Yttrium|88.906|5|3|1.22|3|[Kr] 4d1 5s2
40|Zr|Zirconium|91.224|5|4|1.33|4|[Kr] 4d2 5s2
41|Nb|Niobium|92.906|5|5|1.60|5|[Kr] 4d4 5s1
42|Mo|Molybdenum|95.95|5|6|2.16|6|[Kr] 4d5 5s1
43|Tc|Technetium|98*|5|7|1.90|7|[Kr] 4d5 5s2
44|Ru|Ruthenium|101.07|5|8|2.20|4|[Kr] 4d7 5s1
45|Rh|Rhodium|102.906|5|9|2.28|3|[Kr] 4d8 5s1
46|Pd|Palladium|106.42|5|10|2.20|2|[Kr] 4d10
47|Ag|Silver|107.868|5|11|1.93|1|[Kr] 4d10 5s1
48|Cd|Cadmium|112.41|5|12|1.69|2|[Kr] 4d10 5s2
49|In|Indium|114.818|5|13|1.78|3|[Kr] 4d10 5s2 5p1
50|Sn|Tin|118.71|5|14|1.96|2,4|[Kr] 4d10 5s2 5p2
51|Sb|Antimony|121.76|5|15|2.05|-3,3,5|[Kr] 4d10 5s2 5p3
52|Te|Tellurium|127.60|5|16|2.10|-2,4,6|[Kr] 4d10 5s2 5p4
53|I|Iodine|126.904|5|17|2.66|-1,5,7|[Kr] 4d10 5s2 5p5
54|Xe|Xenon|131.293|5|18|2.60||[Kr] 4d10 5s2 5p6
55|Cs|Cesium|132.91|6|1|0.79|1|[Xe] 6s1
56|Ba|Barium|137.327|6|2|0.89|2|[Xe] 6s2
57|La|Lanthanum|138.905|6|3|1.10|3|[Xe] 5d1 6s2
58|Ce|Cerium|140.116|6||1.12|3,4|[Xe] 4f1 5d1 6s2
59|Pr|Praseodymium|140.908|6||1.13|3|[Xe] 4f3 6s2
60|Nd|Neodymium|144.242|6||1.14|3|[Xe] 4f4 6s2
61|Pm|Promethium|145*|6|||3|[Xe] 4f5 6s2
62|Sm|Samarium|150.36|6||1.17|3|[Xe] 4f6 6s2
63|Eu|Europium|151.964|6|||2,3|[Xe] 4f7 6s2
64|Gd|Gadolinium|157.25|6||1.20|3|[Xe] 4f7 5d1 6s2
65|Tb|Terbium|158.925|6|||3|[Xe] 4f9 6s2
66|Dy|Dysprosium|162.500|6||1.22|3|[Xe] 4f10 6s2
67|Ho|Holmium|164.930|6||1.23|3|[Xe] 4f11 6s2
68|Er|Erbium|167.259|6||1.24|3|[Xe] 4f12 6s2
69|Tm|Thulium|168.934|6||1.25|3|[Xe] 4f13 6s2
70|Yb|Ytterbium|173.045|6|||2,3|[Xe] 4f14 6s2
71|Lu|Lutetium|174.967|6||1.27|3|[Xe] 4f14 5d1 6s2
72|Hf|Hafnium|178.49|6|4|1.30|4|[Xe] 4f14 5d2 6s2
73|Ta|Tantalum|180.948|6|5|1.50|5|[Xe] 4f14 5d3 6s2
74|W|Tungsten|183.84|6|6|2.36|6|[Xe] 4f14 5d4 6s2
75|Re|Rhenium|186.207|6|7|1.90|7|[Xe] 4f14 5d5 6s2
76|Os|Osmium|190.23|6|8|2.20|4|[Xe] 4f14 5d6 6s2
77|Ir|Iridium|192.217|6|9|2.20|4|[Xe] 4f14 5d7 6s2
78|Pt|Platinum|195.08|6|10|2.28|2,4|[Xe] 4f14 5d9 6s1
79|Au|Gold|196.967|6|11|2.54|1,3|[Xe] 4f14 5d10 6s1
80|Hg|Mercury|200.59|6|12|2.00|1,2|[Xe] 4f14 5d10 6s2
81|Tl|Thallium|204.38|6|13|1.62|1,3|[Xe] 4f14 5d10 6s2 6p1
82|Pb|Lead|207.2|6|14|2.33|2,4|[Xe] 4f14 5d10 6s2 6p2
83|Bi|Bismuth|208.98|6|15|2.02|3|[Xe] 4f14 5d10 6s2 6p3
84|Po|Polonium|209*|6|16|2.00|2,4|[Xe] 4f14 5d10 6s2 6p4
85|At|Astatine|210*|6|17|2.20|-1|[Xe] 4f14 5d10 6s2 6p5
86|Rn|Radon|222*|6|18|||[Xe] 4f14 5d10 6s2 6p6
87|Fr|Francium|223*|7|1|0.70|1|[Rn] 7s1
88|Ra|Radium|226*|7|2|0.90|2|[Rn] 7s2
89|Ac|Actinium|227*|7|3|1.10|3|[Rn] 6d1 7s2
90|Th|Thorium|232.038|7||1.30|4|[Rn] 6d2 7s2
91|Pa|Protactinium|231.036|7||1.50|5|[Rn] 5f2 6d1 7s2
92|U|Uranium|238.03|7||1.38|6|[Rn] 5f3 6d1 7s2
93|Np|Neptunium|237*|7||1.36|5|[Rn] 5f4 6d1 7s2
94|Pu|Plutonium|244*|7||1.28|4|[Rn] 5f6 7s2
95|Am|Americium|243*|7||1.30|3|[Rn] 5f7 7s2
96|Cm|Curium|247*|7||1.30|3|[Rn] 5f7 6d1 7s2
97|Bk|Berkelium|247*|7|||3|[Rn] 5f9 7s2
98|Cf|Californium|251*|7|||3|[Rn] 5f10 7s2
99|Es|Einsteinium|252*|7|||3|[Rn] 5f11 7s2
100|Fm|Fermium|257*|7|||3|[Rn] 5f12 7s2
101|Md|Mendelevium|258*|7|||3|[Rn] 5f13 7s2
102|No|Nobelium|259*|7|||2|[Rn] 5f14 7s2
103|Lr|Lawrencium|266*|7|||3|[Rn] 5f14 7s2 7p1
104|Rf|Rutherfordium|267*|7|4||4|[Rn] 5f14 6d2 7s2
105|Db|Dubnium|268*|7|5||5|[Rn] 5f14 6d3 7s2
106|Sg|Seaborgium|269*|7|6||6|[Rn] 5f14 6d4 7s2
107|Bh|Bohrium|270*|7|7|||[Rn] 5f14 6d5 7s2
108|Hs|Hassium|269*|7|8|||[Rn] 5f14 6d6 7s2
109|Mt|Meitnerium|278*|7|9|||[Rn] 5f14 6d7 7s2
110|Ds|Darmstadtium|281*|7|10|||[Rn] 5f14 6d8 7s2
111|Rg|Roentgenium|282*|7|11|||[Rn] 5f14 6d9 7s2
112|Cn|Copernicium|285*|7|12|||[Rn] 5f14 6d10 7s2
113|Nh|Nihonium|286*|7|13|||[Rn] 5f14 6d10 7s2 7p1
114|Fl|Flerovium|289*|7|14|||[Rn] 5f14 6d10 7s2 7p2
115|Mc|Moscovium|290*|7|15|||[Rn] 5f14 6d10 7s2 7p3
116|Lv|Livermorium|293*|7|16|||[Rn] 5f14 6d10 7s2 7p4
117|Ts|Tennessine|294*|7|17|||[Rn] 5f14 6d10 7s2 7p5
118|Og|Oganesson|294*|7|18|||[Rn] 5f14 6d10 7s2 7p6
"""


@dataclass(frozen=True)
class Element:
    """One element from the canonical 118-element table."""

    number: int
    symbol: str
    name: str
    mass: float
    period: int
    group: int | None
    electronegativity: float | None
    oxidation_states: tuple[int, ...]
    configuration: str
    mass_is_isotope: bool


def _optional_int(raw: str) -> int | None:
    text = raw.strip()
    return int(text) if text else None


def _optional_float(raw: str) -> float | None:
    text = raw.strip()
    return float(text) if text else None


def _oxidation_states(raw: str) -> tuple[int, ...]:
    text = raw.strip()
    if not text:
        return ()
    return tuple(int(part) for part in text.split(","))


def _parse_row(line: str) -> Element:
    number, symbol, name, mass, period, group, en, oxidation, configuration = line.split("|")
    isotope = mass.endswith("*")
    return Element(
        number=int(number),
        symbol=symbol,
        name=name,
        mass=float(mass.rstrip("*")),
        period=int(period),
        group=_optional_int(group),
        electronegativity=_optional_float(en),
        oxidation_states=_oxidation_states(oxidation),
        configuration=configuration.strip(),
        mass_is_isotope=isotope,
    )


ELEMENTS: tuple[Element, ...] = tuple(
    _parse_row(line) for line in _ROWS.splitlines() if line.strip()
)
BY_SYMBOL: dict[str, Element] = {element.symbol: element for element in ELEMENTS}
BY_NUMBER: dict[int, Element] = {element.number: element for element in ELEMENTS}


def valence_electrons(symbol: str) -> int | None:
    """Main-group valence count. Transition and f-block elements return None."""
    element = BY_SYMBOL.get(symbol)
    if element is None or element.group is None:
        return None
    if symbol == "He":
        return 2
    if element.group <= 2:
        return element.group
    if element.group >= 13:
        return element.group - 10
    return None
