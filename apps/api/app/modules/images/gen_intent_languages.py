# ruff: noqa: RUF001 - Turkish dotless i and Cyrillic are the words matched
"""Picture requests in the app's other languages: the few shapes ``gen_intent_local`` reads.

Only two unmistakable shapes draw in Spanish, French, German, Italian, Portuguese,
Russian, Turkish and Amharic:

- "draw me": a draw verb addressed to the assistant with "me" ("dibújame", "¿me
  dibujas …?", "dessine-moi", "zeichne mir", "kannst du mir … zeichnen?", "mi disegni
  …?", "me desenhe", "нарисуй мне", "bana … çiz", "… ሳልልኝ");
- "create a picture of": create or generate, a picture noun, then "of" ("crea una
  imagen de", "erstelle ein Bild von", "… resmi oluştur", "создай картинку …").

Everything else ("Dibuja un gato", "Illustra il problema", "Mal den Teufel nicht an die
Wand") is answered in words, as on main. A shape is written as slots: "a|b ?c d" is "a"
or "b", then an optional "c", then "d"; "_" joins the words of one choice ("peux_tu").
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product


def _w(words: str) -> frozenset[str]:
    return frozenset(words.split())


def _phrases(words: str) -> tuple[tuple[str, ...], ...]:
    """ "por_favor porfa": one phrase per word, "_" joining its words."""
    return tuple(tuple(phrase.split("_")) for phrase in words.split())


def _expand(pattern: str) -> frozenset[tuple[str, ...]]:
    """Every word sequence ``pattern`` writes ("me puedes|podrías dibujar")."""
    slots: list[list[tuple[str, ...]]] = []
    for slot in pattern.split():
        choices = [tuple(choice.split("_")) for choice in slot.lstrip("?").split("|")]
        slots.append([*choices, ()] if slot.startswith("?") else choices)
    return frozenset(tuple(word for part in seq for word in part) for seq in product(*slots))


@dataclass(frozen=True)
class Shape:
    """A request: one of ``leads``, the subject, then one of ``tails`` (``()`` is none)."""

    leads: frozenset[tuple[str, ...]]
    tails: frozenset[tuple[str, ...]]
    # Amharic "የድመት ምስል ፍጠር": "of" is the subject's first letter.
    of_prefix: str = ""
    # Their lengths, longest first: a set lookup per length, not a scan of every phrase.
    lead_sizes: tuple[int, ...] = ()
    tail_sizes: tuple[int, ...] = ()


def _shape(lead: str = "", tail: str = "", of_prefix: str = "") -> Shape:
    leads = _expand(lead) if lead else frozenset({()})
    tails = _expand(tail) if tail else frozenset({()})
    sizes = [tuple(sorted({len(seq) for seq in seqs}, reverse=True)) for seqs in (leads, tails)]
    return Shape(leads, tails, of_prefix, *sizes)


@dataclass(frozen=True)
class Language:
    code: str
    shapes: tuple[Shape, ...]
    polite: tuple[tuple[str, ...], ...] = ()
    # Said between the lead and the subject: "zeichne mir bitte …", "zeichne mir mal …".
    fillers: frozenset[str] = frozenset()
    # A subject that points back ("eso", "das"): only the chat could name it.
    pronouns: frozenset[str] = frozenset()
    # A definite subject ("la pirámide alimenticia", "das Verdauungssystem", "l'anatomie
    # de l'œil") is a school figure or a known thing far more often than a picture to
    # invent: "un dragón", "einen Drachen" draw.
    definite: frozenset[str] = frozenset()
    # Turkish marks a definite object by its ending ("sistemini", "kediyi"): "bir kedi".
    definite_endings: tuple[str, ...] = ()
    again: tuple[tuple[str, ...], ...] = ()
    # German separable verbs: "zeichne mir das auf" writes it down, "male mir aus" imagines.
    particles: frozenset[str] = frozenset()


# Spanish.
_ES_ME = "dibújame|dibujame|dibújeme|dibujeme|píntame|pintame"
_ES_YOU = "dibujas|dibujarías|dibujarias|pintas"
_ES_CAN = "puedes|podrías|podrias|puede|podría|podria|podés"
_ES_TO_ME = "dibujarme|pintarme"
_ES_TO = "dibujar|pintar"
_ES_CREATE = "crea|genera|haz|cree|genere|haga|créame|creame|genérame|generame|hazme|hágame|hagame"
_ES_TO_CREATE = "crear|generar|hacer|crearme|generarme|hacerme"
_ES_PICTURE = "?una|un imagen|ilustración|ilustracion|dibujo de"

SPANISH = Language(
    "es",
    shapes=(
        _shape(_ES_ME),
        _shape(f"me {_ES_YOU}"),
        _shape(f"?me {_ES_CAN} {_ES_TO_ME}"),
        _shape(f"me {_ES_CAN} {_ES_TO}"),
        _shape(f"{_ES_CREATE} {_ES_PICTURE}"),
        _shape(f"?me {_ES_CAN} {_ES_TO_CREATE} {_ES_PICTURE}"),
    ),
    polite=_phrases("por_favor porfa porfavor"),
    pronouns=_w("eso esto ello aquello ese esa este esta estos estas esos esas mí lo"),
    definite=_w("el la los las le al del"),
    again=_phrases("otra_vez de_nuevo nuevamente"),
)

# French: "dessine-moi" is "dessine" then "moi" (gen_intent_local splits the clitic).
_FR_DRAW = "dessine|dessinez|peins|peignez"
_FR_YOU = "dessines|dessinerais|dessinez|dessineriez|peins"
_FR_CAN = (
    "peux_tu|pouvez_vous|pourrais_tu|pourriez_vous|tu_peux|vous_pouvez|tu_pourrais|vous_pourriez"
)
_FR_CREATE = "crée|créez|cree|creez|génère|générez|genere|generez"
_FR_TO_CREATE = "créer|creer|générer|generer"
_FR_PICTURE = "une|un image|illustration|dessin de|d'"

FRENCH = Language(
    "fr",
    shapes=(
        _shape(f"{_FR_DRAW} moi"),
        _shape(f"tu|vous me {_FR_YOU}"),
        _shape(f"{_FR_CAN} me dessiner|peindre"),
        _shape(f"{_FR_CREATE} ?moi {_FR_PICTURE}"),
        _shape(f"{_FR_CAN} ?me {_FR_TO_CREATE} {_FR_PICTURE}"),
    ),
    polite=_phrases("s'_il_te_plaît s'_il_te_plait s'_il_vous_plaît s'_il_vous_plait stp svp"),
    pronouns=_w("ça ca cela ceci ce cet cette ces moi"),
    definite=_w("le la les l' du des au aux"),
    again=_phrases("encore à_nouveau a_nouveau de_nouveau"),
)

# German: "kannst du mir eine Katze zeichnen?" closes with its verb.
_DE_DRAW = "zeichne|zeichnet|male|mal|zeichnen_sie|malen_sie"
_DE_CAN = "kannst_du|könntest_du|koenntest_du|können_sie|könnten_sie"
_DE_CREATE = "erstelle|erstell|generiere|generier|erzeuge|erzeug"
_DE_PICTURE = "ein|eine bild|zeichnung|illustration von"

GERMAN = Language(
    "de",
    shapes=(
        _shape(f"{_DE_DRAW} mir|uns"),
        _shape(f"{_DE_CAN} mir|uns", "zeichnen|malen"),
        _shape(f"{_DE_CREATE} ?mir|uns {_DE_PICTURE}"),
        _shape(f"{_DE_CAN} ?mir|uns {_DE_PICTURE}", "erstellen|generieren|erzeugen"),
    ),
    polite=_phrases("bitte"),
    fillers=_w("bitte mal doch einfach schnell"),
    pronouns=_w("es dies dieses diese diesen ihn mir mich davon dazu darüber"),
    definite=_w("das die den der dem des vom zum zur"),
    again=_phrases("nochmal noch_mal noch_einmal erneut wieder"),
    particles=_w("auf ab aus an ein vor"),
)

# Italian.
_IT_ME = "disegnami|dipingimi"
_IT_YOU = "disegni|dipingi|disegneresti|dipingeresti"
_IT_CAN = "puoi|potresti|può|potrebbe"
_IT_CREATE = "crea|genera|creami|generami"
_IT_TO_CREATE = "creare|generare|crearmi|generarmi"
_IT_PICTURE = "un'|una|un immagine|illustrazione|disegno di|d'"

ITALIAN = Language(
    "it",
    shapes=(
        _shape(_IT_ME),
        _shape(f"mi {_IT_YOU}"),
        _shape(f"{_IT_CAN} disegnarmi|dipingermi"),
        _shape(f"mi {_IT_CAN} disegnare|dipingere"),
        _shape(f"{_IT_CREATE} {_IT_PICTURE}"),
        _shape(f"?mi {_IT_CAN} {_IT_TO_CREATE} {_IT_PICTURE}"),
    ),
    polite=_phrases("per_favore per_piacere perfavore"),
    pronouns=_w("questo questa quello quella questi queste quelli ciò cio me"),
    definite=_w("il lo la i gli le l' del della dello dei degli delle"),
    again=_phrases("di_nuovo ancora"),
)

# Portuguese: "desenha-me" is "desenha" then "me".
_PT_DRAW = "desenha|desenhe|desenhas"
_PT_CAN = (
    "pode|podes|poderia|consegue|você_pode|voce_pode|você_poderia|voce_poderia|"
    "você_consegue|voce_consegue|tu_podes"
)
_PT_CREATE = "crie|cria|gere|gera"
_PT_PICTURE = "uma|um imagem|ilustração|ilustracao|desenho de"

PORTUGUESE = Language(
    "pt",
    shapes=(
        _shape(f"{_PT_DRAW} me"),
        _shape(f"?você|voce|tu me {_PT_DRAW}"),
        _shape(f"{_PT_CAN} me desenhar"),
        _shape(f"{_PT_CAN} desenhar me"),
        _shape(f"{_PT_CREATE} ?me {_PT_PICTURE}"),
        _shape(f"{_PT_CAN} ?me criar|gerar {_PT_PICTURE}"),
    ),
    polite=_phrases("por_favor pfv"),
    pronouns=_w("isso isto aquilo este esta esse essa aquele aquela estes estas esses essas mim"),
    definite=_w("o a os as do da dos das ao"),
    again=_phrases("de_novo outra_vez novamente"),
)

# Russian: "создай картинку льва" names the subject without an "of".
_RU_DRAW = "нарисуй|нарисуйте|нарисуешь|нарисуете"
_RU_CAN = "можешь|можете|ты_можешь|вы_можете"
_RU_CREATE = "создай|создайте|сгенерируй|сгенерируйте"
_RU_PICTURE = "изображение|картинку|рисунок|иллюстрацию"

RUSSIAN = Language(
    "ru",
    shapes=(
        _shape(f"{_RU_DRAW} мне|нам"),
        _shape(f"{_RU_CAN} нарисовать мне|нам"),
        _shape(f"{_RU_CAN} мне|нам нарисовать"),
        _shape(f"{_RU_CREATE} ?мне|нам {_RU_PICTURE}"),
        _shape(f"{_RU_CAN} ?мне|нам создать|сгенерировать {_RU_PICTURE}"),
    ),
    polite=_phrases("пожалуйста плиз пж"),
    pronouns=_w("это этого эту этот эти его её ее их то того тот ту меня"),
    again=_phrases("ещё_раз еще_раз снова опять заново"),
)

# Turkish closes with its verb: "Bana bir kedi çiz", "Bir aslan resmi oluştur".
_TR_DRAW = (
    "çiz|çizin|çizsene|çizer_misin|çizer_misiniz|çizebilir_misin|çizebilir_misiniz|"
    "çizermisin|çizebilirmisin"
)
_TR_CREATE = (
    "oluştur|oluşturun|oluştursana|üret|üretin|oluşturur_musun|oluşturabilir_misin|"
    "üretir_misin|üretebilir_misin"
)

TURKISH = Language(
    "tr",
    shapes=(
        _shape("bana|bize", _TR_DRAW),
        _shape("?bana|bize", f"resmi|resmini|görseli|görselini {_TR_CREATE}"),
    ),
    polite=_phrases("lütfen lutfen"),
    pronouns=_w("bunu onu şunu bunları onları şunları bu şu o"),
    definite_endings=("nı", "ni", "nu", "nü", "yı", "yi", "yu", "yü"),
    again=_phrases("tekrar yine yeniden"),
)

# Amharic: "ድመት ሳልልኝ" (draw me a cat); bare "ሳል" is also "a cough" and draws nothing.
_AM_DRAW = "ሳልልኝ|ሣልልኝ|ሳይልኝ|ሣይልኝ|ሳሉልኝ|ሣሉልኝ"
_AM_CREATE = "ፍጠርልኝ|ፍጠሪልኝ|ፍጠሩልኝ|ፍጠር|ፍጠሪ|ፍጠሩ"
_AM_PICTURE = "ምስል|ስዕል|ሥዕል|ስእል"

AMHARIC = Language(
    "am",
    shapes=(
        _shape(tail=f"{_AM_PICTURE} {_AM_DRAW}", of_prefix="የ"),
        _shape(tail=f"{_AM_PICTURE} {_AM_CREATE}", of_prefix="የ"),
        _shape(tail=_AM_DRAW),
    ),
    polite=_phrases("እባክህ እባክሽ እባካችሁ እባክዎ እባክዎን"),
    pronouns=_w("ይህን ይሄን ያንን እሱን እሷን እነሱን"),
    again=_phrases("እንደገና"),
)

LANGUAGES: tuple[Language, ...] = (
    SPANISH,
    FRENCH,
    GERMAN,
    ITALIAN,
    PORTUGUESE,
    RUSSIAN,
    TURKISH,
    AMHARIC,
)

# Dropped before the subject ("dibújame un gato" draws "gato").
ARTICLES = _w("un una uno un' une ein eine einen einem einer um uma bir")

# "Zeichne mir auch eine Katze", "dibújame también un gato": "also" after the lead.
ALSO = _w(
    "also también además aussi également auch außerdem ausserdem zudem anche inoltre pure "
    "também tambem além disso ayrıca также тоже ещё еще እንዲሁም ደግሞ ደግሞም"
)
