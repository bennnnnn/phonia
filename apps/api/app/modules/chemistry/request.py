"""Chemistry request gating and compound-name extraction.

The gate is a cheap classifier that runs on every chat turn, so it must stay
linear on hostile input and must not claim everyday language. Numeric/formula
extraction belongs in ``extract.py`` so this gate cannot accidentally solve.

Cues come in three strengths:

* strong: a phrase only chemistry uses ("molar mass", "titration", "ΔH");
* case-sensitive symbols (``pH``, ``Ka``, ``Kp``) that lose meaning in lowercase;
* weak single words ("acid", "boiling", "nuclear", "mole") that also appear in
  cooking, weather and politics. Weak cues count only in pairs, or next to a
  formula such as ``H2SO4``.
"""

from __future__ import annotations

import re

from app.modules.chemistry.elements import BY_SYMBOL
from app.modules.chemistry.input_text import HYDRATE_DOT, read_chemistry_text
from app.modules.chemistry.particle_cues import PARTICLE_WORD, asks_about_particles
from app.modules.chemistry.species import ARROWS
from app.modules.chemistry.species_facts import ELEMENT_NAMES, is_formula

# Formula characters are case-sensitive on purpose. Under ``re.IGNORECASE`` a
# lowercase word such as "sodium" splits into "so" + "di" + "um" in Fibonacci-many
# ways, which made a 32-letter run cost seconds. Callers keep their own flags for
# the words around a formula; ``(?-i:…)`` pins only the formula itself.
CHEMICAL_FORMULA = (
    r"(?-i:(?:e-|[A-Z][a-z]?[0-9]*(?:\([A-Za-z0-9]+\)[0-9]*)*"
    r"(?:[A-Z][a-z]?[0-9]*(?:\([A-Za-z0-9]+\)[0-9]?)?)*)"
    r"(?:\^(?:\{\d*[+-]\}|\d*[+-])|\d*[+-])?"
    r"(?:\((?:aq|s|l|g)\))?)"
)
# A formula has ended: no letter or digit follows, and no hydrate dot carries it on. A reader
# that does not take a hydrate declines CuSO4·5H2O instead of reading the CuSO4 of it.
FORMULA_END = rf"(?![A-Za-z0-9{HYDRATE_DOT}])"
# A formula with the water (or second salt) of a hydrate: CuSO4·5H2O, Na2CO3·10H2O. The input
# reader (``input_text``) writes every hydrate dot as this one character.
SAMPLE_FORMULA = (
    rf"{CHEMICAL_FORMULA}"
    rf"(?-i:(?:{HYDRATE_DOT}\d{{0,2}}(?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+)*)"
)
_ARROW = "(?:" + "|".join(re.escape(arrow) for arrow in ARROWS) + ")"
# Coefficients stop at two digits so a nuclide such as 238U is not "238 U".
_TERM = rf"(?:\d{{1,2}}\s*)?{CHEMICAL_FORMULA}"
# A match may not start inside a token ("CuSO4.5H2O" must not truncate to
# "H2O -> …") and may not end where a bracket, hydrate dot or digit continues.
# A period that ends a sentence ("… -> H2O.") is still allowed.
# A side has at most this many species. Unbounded, a long "Al + Al + …" with no arrow
# was rescanned from every term: quadratic, 0.14 s on the 4,000-character gate window.
# A match never starts after a "+", so a longer side matches nothing rather than its
# last few species.
_MAX_TERMS_PER_SIDE = 24
EQUATION_RE = re.compile(
    rf"(?<![A-Za-z0-9·\[])(?<![A-Za-z0-9]\.)(?<!\+)(?<!\+\s)(?<!\+\s\s)"
    rf"((?:{_TERM}\s*\+\s*){{0,{_MAX_TERMS_PER_SIDE}}}{_TERM}\s*{_ARROW}\s*"
    rf"(?:{_TERM}\s*\+\s*){{0,{_MAX_TERMS_PER_SIDE}}}{_TERM})"
    rf"(?![A-Za-z0-9·\]]|\.\d)"
)

# Longest message the gate reads. The head and tail windows keep a question that
# follows a long pasted passage without scanning 32k characters.
_GATE_WINDOW = 2000

_STRONG_CUE = re.compile(
    r"\b(?:stoichiometr\w*|molar\s+(?:mass|volume|absorptivity|concentration)|"
    r"molarity|molality|mole\s+fraction|formula\s+units?|M1V1|mass\s+percent|pOH|"
    r"parts\s+per\s+(?:million|billion)|(?:ppm|ppb)(?=\s+of\b)|"
    r"volume\s+percent|percent(?:age)?\s+by\s+(?:volume|mass)|mass/volume\s+percent|"
    r"%\s*(?:\(\s*)?(?:by\s+(?:mass|volume)|w/w|m/m|v/v|w/v|m/v)|"
    r"thermochem\w*|enthalpy|specific\s+heat|calorimet\w*|"
    r"reaction\s+quotient|equilibrium\s+(?:constant|expression)|ice\s+(?:table|equilibrium)|"
    r"rate\s+(?:constant|law)|first[- ]order|second[- ]order|zero[- ]order|arrhenius|"
    r"electrochem\w*|half[- ]reactions?|nernst|electrolysis|cell\s+potential|faraday'?s?\s+law|"
    r"galvanic|radioactive|nuclear\s+(?:equation|mass|activity)|decay\s+constant|"
    r"exponential\s+decay|mass\s+defect|binding\s+energy|electron\s+capture|"
    r"beer[- ]lambert|absorbance|transmittance|ionic\s+strength|"
    r"optical\s+purity|specific\s+rotation|enantiomeric\s+excess|"
    r"hydrogen\s+deficiency|degree\s+of\s+unsaturation|"
    r"partition\s+coefficient|distribution\s+coefficient|kirchhoff|"
    r"van\s+der\s+waals|compressibility|phase\s+rule|molar\s+heat\s+capacity|"
    r"clapeyron|langmuir|eyring|molar\s+conductivity|"
    r"neutron|ion\s+charge|shell\s+capacity|bond\s+order|wavenumber|quantum\s+yield|"
    r"tetrahedral\s+splitting|moles\s+of\s+electrons|hill\s+equation|freundlich|"
    r"degree\s+of\s+polymerization|polydispersity|carothers|extent\s+of\s+reaction|"
    r"polymerization\s+rate|butler[- ]volmer|tafel|electrochemical\s+potential|"
    r"chemical\s+potential|activity\s+coefficient|larmor|chemical\s+shift|"
    r"magnetic\s+sector|mass\s+spectrometer|interplanar|lever\s+rule|"
    r"mean[- ]square\s+displacement|stokes[- ]einstein|relative\s+standard\s+deviation|"
    r"conjugate\s+fraction|acid\s+fraction|"
    r"percent\s+(?:yield|composition|error)|atom\s+economy|"
    r"avogadro|"
    r"pv\s*=\s*nrt|ideal\s+gas|gas\s+law|combined\s+gas|partial\s+pressures?|"
    r"effus(?:ion|es?|ing)|graham'?s?\s+law|molar\s+solubility|"
    r"molecular\s+descriptor|logp|tpsa|periodic\s+table|atomic\s+(?:mass|number|weight)|"
    r"electronegativity|electron\s+configuration|valence\s+electrons?|"
    r"empirical\s+formula|molecular\s+formula|combustion|hydrate|titration|ksp|hess'?s?\s+law|vsepr|"
    r"lewis\s+(?:structure|dot)|formal\s+charge|oxidation\s+(?:state|number)|"
    r"(?:boyle|charles|dalton|graham|henry)'?s?\s+law|clausius|functional\s+groups?|isomer\w*|"
    r"coordination\s+(?:complex|compound|number)|polyprotic|amphiprotic|diprotic|common[- ]ion|"
    r"bond\s+enthalpy|formation\s+enthalpy|van\s*'?t\s*hoff|weak\s+(?:acid|base)|strong\s+(?:acid|base)|"
    r"boiling[- ]point\s+elevation|freezing[- ]point\s+depression|osmotic\s+pressure|raoult|"
    r"total\s+vapor\s+pressure|"
    r"collected\s+over\s+water|precipitation\s+reaction|stereochemistry|"
    r"crystal\s+field|magnetic\s+moment|"
    r"relative\s+uncertainty|retention\s+factor|limit\s+of\s+detection|limit\s+of\s+quantitation|"
    r"LOD|LOQ|capacity\s+factor|selectivity|Rs|plate\s+number|plate\s+height|"
    r"peak\s+resolution|Michaelis[- ]Menten|IUPAC|"
    r"IR\s+(?:ranges|peak)|NMR\s+(?:ranges|peak|splitting)|molecular\s+ion|"
    r"HBr\s+addition|HCl\s+addition|HI\s+addition|bromine\s+addition|acid\s+hydration|"
    r"catalytic\s+hydrogenation|hydroxide\s+substitution|"
    r"esterification|calibration\s+curve|gravimetric|standard\s+addition|"
    r"calorimeter\s+constant|gibbs\s+(?:free\s+)?energy|Δ[GHS]|delta\s*[GHS](?=\s*=))\b",
    re.IGNORECASE,
)
# A standard deviation or standard error of a bare number list is statistics, not
# chemistry. It is chemistry's when the numbers are lab data: replicate readings,
# trials, a titration, or values with a chemistry unit.
_DATA_STATISTIC = re.compile(r"\bstandard\s+(?:deviation|error)\b", re.IGNORECASE)
_LAB_DATA = re.compile(
    r"\b(?:measurements?|trials?|replicates?|readings?|runs|titrations?|titres?|titers?|"
    r"absorbances?|concentrations?|masses|yields?)\b|"
    r"\d\s*(?:mL|L|g|mg|kg|mol|mmol|M|mM|ppm|ppb|%)(?![A-Za-z])",
    re.IGNORECASE,
)
# "Chemistry" names the subject, except in the idiom for getting along ("great chemistry").
_SUBJECT_CUE = re.compile(r"\bchemistry\b", re.IGNORECASE)
_CHEMISTRY_IDIOM = re.compile(
    r"\b(?:great|good|bad|no|real|instant|amazing|natural|undeniable|zero|romantic|"
    r"on-?screen|team|special|incredible)\s+chemistry\b(?!\s+(?:textbook|book|teacher|"
    r"class|course|homework|question|problem|tutor|lab|notes?|exam|test|lesson)s?\b)|"
    r"\bchemistry\s+(?:between|together)\b|"
    r"\bchemistry\s+with\s+(?:him|her|them|you|me|us|each\s+other|someone)\b",
    re.IGNORECASE,
)
# A battery or a habit has a half-life too: chemistry's has a number, a nuclide or a decay.
_HALF_LIFE = re.compile(r"\bhalf[- ]life\b", re.IGNORECASE)
_DECAY_CONTEXT = re.compile(
    r"\d|\b(?:decay\w*|radioactiv\w*|isotopes?|nuclides?|first[- ]order|reaction|"
    r"sample|rate\s+constant)\b",
    re.IGNORECASE,
)
# "How many grams of oxygen are in 10 g of H2O?": an element's share of a sample.
_ELEMENT_IN_SAMPLE = re.compile(
    r"\b(?:grams?|mass)\s+of\s+(?:"
    + "|".join(sorted(ELEMENT_NAMES, key=len, reverse=True))
    + r")\s+(?:(?:is|are)\s+)?(?:there\s+)?(?:present\s+|contained\s+)?in\b",
    re.IGNORECASE,
)
_MOLAR_SOLUTION = re.compile(r"\b(?<!\.)\d+(?:\.\d+)?\s*M\s+([A-Z][A-Za-z0-9()]*)")
# A stock of a stated molarity: "a 6.0 M stock solution", "12 M HCl stock". "3 M Company stock"
# is a share price.
_MOLAR_STOCK = re.compile(
    r"\b(?<!\.)\d+(?:\.\d+)?\s*M\s+(?:(?P<formula>[A-Z][A-Za-z0-9()]*)\s+)?stock(?P<solution>\s+solution)?\b"
)


def _molar_stock(text: str) -> bool:
    return any(
        match.group("solution") or (match.group("formula") and is_formula(match.group("formula")))
        for match in _MOLAR_STOCK.finditer(text)
    )


# A dilution's labelled concentrations: "M1 = 12 M", "C2 = 0.50 mol/L".
_LABELLED_MOLARITY = re.compile(
    r"(?<![A-Za-z0-9])[MC][12]\s*=\s*(?:\d+(?:\.\d+)?|\.\d+)\s*(?:M|mol/L)(?![A-Za-z])"
)
_VMAX = re.compile(r"(?<![A-Za-z])Vmax(?![A-Za-z])")
_KM = re.compile(r"(?<![A-Za-z])Km(?![A-Za-z])")
# "the shape of NH3": a shape is chemistry's only when what it is of is a real formula.
_SHAPE_OF = re.compile(
    r"\b(?:shape|geometry)\s+of\s+(?:an?\s+|the\s+)?([A-Z][A-Za-z0-9()]*)(?![A-Za-z0-9(])",
    re.IGNORECASE,
)
# "Ka", "Kb", "pH", "Rf" and "Kp" are words in lowercase ("kb" file size, "ph.d.").
_SYMBOL_CUE = re.compile(
    r"(?<![A-Za-z0-9])(?:pH|pOH|pKa|pKb|Ka|Kb|Kc|Kp|Qc|Ksp|Rf|Δ[GHS])(?![A-Za-z])"
    # A standard potential, E° or E°cell: physics' E is an energy or a field, never E°.
    r"|(?<![A-Za-z0-9])E\s*[°º]\s*(?:cell)?|(?<![A-Za-z0-9])Ecell\b"
)
_WEAK_CUE = re.compile(
    r"\b(?:acid|base|boiling|freezing|nuclear|mol(?:e|es)?|molecules?|molar|dilut\w*|buffer|"
    r"equilibrium|entropy|kinetic\w*|empirical|oxidation|coordination|calibration|"
    r"precipitation|gibbs|faraday|hess|boyle|charles|dalton|lewis|reaction|compound|"
    r"chemical|atoms?|bond|neutrali[sz]\w*|isotopes?|diffus\w*)\b",
    re.IGNORECASE,
)
# An element followed by a digit ("H2O", "Fe2") or a capital run ("NaOH").
_FORMULA_HINT = re.compile(r"\b[A-Z][a-z]?\d|\b(?:[A-Z][a-z]?){2,4}\b")
_FORMULA_WORD = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9()]*)")

# "What % of Fe2O3 is iron?": an element's share of a compound written as a formula.
_SHARE_OF_COMPOUND = re.compile(
    r"(?:%|\b[Pp]ercent(?:age)?)\s+(?:by\s+mass\s+)?of\s+(?:the\s+mass\s+of\s+)?"
    r"([A-Z][A-Za-z0-9()]*)\s+(?:by\s+mass\s+)?is\s+(?:made\s+up\s+of\s+)?([A-Za-z]+)\b"
)

# Two gases of a mixture, each with its pressure: "He at 0.40 atm, Ne at 0.25 atm",
# "P(N2) = 600 mmHg". A tank "B at 3 atm" is not a gas.
_NOBLE_GASES = frozenset({"He", "Ne", "Ar", "Kr", "Xe", "Rn"})
_GAS_NAMES = frozenset(
    {
        "hydrogen",
        "helium",
        "nitrogen",
        "oxygen",
        "fluorine",
        "neon",
        "chlorine",
        "argon",
        "krypton",
        "xenon",
        "radon",
    }
)
_GAS_PRESSURE = re.compile(
    r"(?:\b|\B(?<![A-Za-z0-9]))(?:P\()?([A-Za-z][A-Za-z0-9]*)\)?\s*(?:at|=|:)\s*\d+(?:\.\d+)?\s*"
    r"(?:atm|kPa|mmHg|torr|bar|Pa)(?![A-Za-z])"
)


def _gas_mixture(text: str) -> bool:
    gases = {
        match.group(1)
        for match in _GAS_PRESSURE.finditer(text)
        if match.group(1) in _NOBLE_GASES
        or match.group(1).lower() in _GAS_NAMES
        or is_formula(match.group(1))
    }
    return len(gases) >= 2


# "What's the name of Fe2(SO4)3?": a compound written as a formula, its name asked.
_NAME_OF_FORMULA = re.compile(
    r"\bname\s+(?:of|for)\s+(?:the\s+)?(?:compound\s+)?([A-Z(][A-Za-z0-9()]*)"
)

# "the formula for iron(III) oxide": a salt the ion table names.
_FORMULA_FOR = re.compile(
    r"\bformula\s+(?:of|for)\s+(?:the\s+)?([A-Za-z]+(?:\s*\(\s*[IVXivx]+\s*\))?\s+[A-Za-z]+)",
    re.IGNORECASE,
)


def _salt_named(text: str) -> bool:
    from app.modules.chemistry.nomenclature import salt_from_name

    return any(salt_from_name(match.group(1)) is not None for match in _FORMULA_FOR.finditer(text))


def _element_share(text: str) -> bool:
    for match in _SHARE_OF_COMPOUND.finditer(text):
        compound, element = match.groups()
        if names_compound(compound) and (element in BY_SYMBOL or element.lower() in ELEMENT_NAMES):
            return True
    return False


def names_compound(text: str) -> bool:
    """A compound written as a formula: two element symbols or more, and a digit or a
    lowercase letter, so a shouted word ("NO", "HI", "OK") is not one."""
    return any(
        sum(char.isupper() for char in token) >= 2
        and any(char.islower() or char.isdigit() for char in token)
        and is_formula(token)
        for token in _FORMULA_WORD.findall(text)
    )


_BALANCE_CUE = re.compile(r"\b(?:bal+[ae]nce[ds]?|coefficient)\b", re.IGNORECASE)
_EQUATION_WORDS = re.compile(
    r"\b(?:moles?|grams?|limiting|yield)\b|(?<![A-Za-z0-9])(?:Kc|Qc)(?![A-Za-z])",
    re.IGNORECASE,
)

# The user asked about a molecule, so any name-shaped phrase after these is a lookup.
_EXPLICIT_NAME_RE = re.compile(
    r"\b(?:(?:lewis\s+)?structure\s+of|molecular\s+formula\s+of|formula\s+of|"
    r"draw\s+(?:the\s+)?(?:lewis\s+)?structure\s+of|"
    r"show(?:\s+me)?\s+(?:the\s+)?(?:lewis\s+)?structure\s+of|"
    r"draw\s+(?:the\s+)?molecule|show\s+me\s+(?:the\s+)?molecule|"
    r"describe(?:\s+the)?\s+molecule|smiles\s+for|smiles\s+of|"
    r"chemical\s+structure\s+of|the\s+compound|"
    r"(?:log\s*p|tpsa|polar\s+surface\s+area|drug[-\s]?likeness)\s+(?:of|for))\s*"
    r"([a-zA-Z][a-zA-Z0-9\-\s]{2,40}?)"
    r"(?:\?|$|\.|,|\s+(?:and|or|with|in|at|for|to|is|are|the)\b)",
    re.IGNORECASE,
)
# Bare "what is X" is ordinary language ("what is love"), so X must look like a
# compound: a common name or a systematic ending.
_BARE_NAME_RE = re.compile(
    r"\b(?:what\s+is|what's|tell\s+me\s+about|describe(?:\s+the)?|draw|show\s+me)\s+"
    r"([a-zA-Z][a-zA-Z0-9\-\s]{2,40}?)"
    r"(?:\?|$|\.|,|\s+(?:and|or|with|in|at|for|to|is|are|the)\b)",
    re.IGNORECASE,
)
_COMMON_COMPOUNDS = frozenset(
    {
        "aspirin",
        "caffeine",
        "ibuprofen",
        "paracetamol",
        "acetaminophen",
        "penicillin",
        "insulin",
        "morphine",
        "nicotine",
        "dopamine",
        "serotonin",
        "adrenaline",
        "epinephrine",
        "cholesterol",
        "glucose",
        "fructose",
        "sucrose",
        "lactose",
        "ammonia",
        "methane",
        "ethane",
        "propane",
        "butane",
        "pentane",
        "hexane",
        "ethylene",
        "propylene",
        "acetylene",
        "benzene",
        "toluene",
        "phenol",
        "aniline",
        "ethanol",
        "methanol",
        "propanol",
        "glycerol",
        "glycerin",
        "acetone",
        "urea",
        "formaldehyde",
        "acetaldehyde",
        "chloroform",
        "menthol",
        "vanillin",
        "retinol",
        "adenosine",
        "adenine",
        "guanine",
        "cytosine",
        "thymine",
        "uracil",
        "dna",
        "glycine",
        "alanine",
        "cysteine",
        "tryptophan",
        "histamine",
        "melatonin",
        "testosterone",
        "estradiol",
        "cortisol",
        "capsaicin",
        "limonene",
        "camphor",
        "naphthalene",
        "ozone",
        "hydrogen peroxide",
        "salt",
        "sugar",
        "vinegar",
    }
)
_COMPOUND_ENDINGS = (
    "oxide",
    "dioxide",
    "chloride",
    "bromide",
    "iodide",
    "fluoride",
    "sulfate",
    "sulfite",
    "sulfide",
    "nitrate",
    "nitrite",
    "hydroxide",
    "carbonate",
    "bicarbonate",
    "phosphate",
    "acetate",
    "cyanide",
    "peroxide",
    "acid",
    "amine",
    "amide",
    "ester",
    "ether",
    "ketone",
    "aldehyde",
    "alcohol",
    "glycol",
)
_NAME_STOPWORDS = frozenset(
    {
        "the",
        "of",
        "a",
        "an",
        "and",
        "for",
        "to",
        "in",
        "on",
        "at",
        "with",
        "from",
        "about",
        "this",
        "that",
        "your",
        "my",
        "you",
        "me",
        "it",
        "is",
        "are",
    }
)
_FALSE_POSITIVES = frozenset(
    {
        "the",
        "this",
        "that",
        "it",
        "a",
        "an",
        "light",
        "energy",
        "time",
        "space",
        "code",
        "data",
        "file",
        "image",
        "text",
    }
)
# "compound interest", "compound sentence": not a chemical compound.
_NOT_A_COMPOUND = re.compile(
    r"\bcompound\s+(?:interest|word|sentence|noun|fracture|growth|annual|return|verb|eye)\b",
    re.IGNORECASE,
)
_STRUCTURE_VERB = re.compile(
    r"\b(?:structure|formula|what\s+is|tell\s+me\s+about|draw|show|describe)\b", re.IGNORECASE
)
_STRUCTURE_NOUN = re.compile(
    r"\b(?:molecules?|smiles|molecular|chemical|compounds?)\b", re.IGNORECASE
)


def _window(content: str) -> str:
    cleaned = content.strip()
    if len(cleaned) <= 2 * _GATE_WINDOW:
        return cleaned
    return f"{cleaned[:_GATE_WINDOW]}\n{cleaned[-_GATE_WINDOW:]}"


def _has_equation(text: str) -> bool:
    return re.search(_ARROW, text) is not None and EQUATION_RE.search(text) is not None


def is_chemistry_question(content: str) -> bool:
    """True for supported calculations or plausible compound lookup requests."""
    cleaned = read_chemistry_text(_window(content))
    if not cleaned:
        return False
    if _STRONG_CUE.search(cleaned) or _SYMBOL_CUE.search(cleaned):
        return True
    if _DATA_STATISTIC.search(cleaned) and _LAB_DATA.search(cleaned):
        return True
    if _SUBJECT_CUE.search(cleaned) and not _CHEMISTRY_IDIOM.search(cleaned):
        return True
    if _HALF_LIFE.search(cleaned) and _DECAY_CONTEXT.search(cleaned):
        return True
    if _ELEMENT_IN_SAMPLE.search(cleaned):
        return True
    # A concentration of a named formula: "6 M HCl".
    if any(is_formula(match.group(1)) for match in _MOLAR_SOLUTION.finditer(cleaned)):
        return True
    if _LABELLED_MOLARITY.search(cleaned) or _molar_stock(cleaned):
        return True
    # Michaelis-Menten written by its constants alone: "Vmax = 10 μmol/min, Km = 2 mM".
    if _VMAX.search(cleaned) and _KM.search(cleaned):
        return True
    shape = _SHAPE_OF.search(cleaned)
    if shape is not None and is_formula(shape.group(1)):
        return True
    weak = {match.group(0).lower() for match in _WEAK_CUE.finditer(cleaned)}
    if len(weak) >= 2 or (weak and _FORMULA_HINT.search(cleaned)):
        return True
    if asks_about_particles(cleaned):
        return True
    if PARTICLE_WORD.search(cleaned) and names_compound(cleaned):
        return True
    if _element_share(cleaned) or _gas_mixture(cleaned):
        return True
    if any(names_compound(match.group(1)) for match in _NAME_OF_FORMULA.finditer(cleaned)):
        return True
    if _salt_named(cleaned):
        return True
    if _has_equation(cleaned) and (_BALANCE_CUE.search(cleaned) or _EQUATION_WORDS.search(cleaned)):
        return True
    if _NOT_A_COMPOUND.search(cleaned):
        return False
    if _STRUCTURE_VERB.search(cleaned) and _STRUCTURE_NOUN.search(cleaned):
        return True
    if extract_compound_name(cleaned) is not None:
        return True
    # No cue word, but one law ("how many moles in 36 g of water?"), a reaction or a shape.
    from app.modules.chemistry.binding import bind_chemistry_intent as binds
    from app.modules.chemistry.extractors.described import reaction_question
    from app.modules.chemistry.extractors.shapes import shape_question

    return bool(reaction_question(cleaned) or shape_question(cleaned) or binds(cleaned))


def _clean_name(raw: str) -> str | None:
    name = raw.strip().lower()
    name = re.sub(r"\s(?:the|a|an|of|for|with)$", "", name).strip()
    name = re.sub(r"^(?:the\s+)?(?:lewis\s+)?structure\s+of\s+", "", name).strip()
    name = re.sub(r"^(?:molecule|compound)\s+", "", name).strip()
    if not name or name in _FALSE_POSITIVES or not 3 <= len(name) <= 40:
        return None
    words = name.split()
    # "what is the capital of France" matches the same lead as "what is aspirin".
    # A real compound name has no function words.
    if len(words) > 3 or any(word in _NAME_STOPWORDS for word in words):
        return None
    return name


def _looks_like_compound(name: str) -> bool:
    if name in _COMMON_COMPOUNDS:
        return True
    return any(
        word in _COMMON_COMPOUNDS or word.endswith(_COMPOUND_ENDINGS) for word in name.split()
    )


def extract_compound_name(content: str) -> str | None:
    """Return a conservative PubChem lookup candidate."""
    if _NOT_A_COMPOUND.search(content):
        return None
    explicit = _EXPLICIT_NAME_RE.search(content)
    if explicit is not None:
        return _clean_name(explicit.group(1))
    bare = _BARE_NAME_RE.search(content)
    if bare is None:
        return None
    name = _clean_name(bare.group(1))
    if name is None or not _looks_like_compound(name):
        return None
    return name
