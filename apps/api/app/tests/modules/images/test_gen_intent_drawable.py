"""A picture asked in another language draws only a subject made of listed words.

Review 5 found a third of its task-style draw-me lines drawn under the old block-list
("Dibújame un cuadro comparativo", "Zeichne mir einen Grundriss"). Round 6 listed the
head noun; review 6 then found 170 of 207 lines drawn through what followed a listed
head ("un gato en ASCII", "un árbol binario", "un puente de Wheatstone", "un perro y
sugiéreme nombres"). Now every word of the subject must be a listed noun, a plain
descriptor or a function word. ``language_pictures.json`` holds everyday requests that
must still draw.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.images.gen_intent import extract_image_gen_prompt
from app.modules.images.gen_intent_drawable import DESCRIBE, GLUE, NOUNS, names_drawable
from app.modules.images.intent import composer_image_intent
from app.tests.modules.images.test_gen_intent_languages import read_in

_PICTURES: dict[str, list[str]] = json.loads(
    Path(__file__).with_name("language_pictures.json").read_text(encoding="utf-8")
)
PICTURES = [(lang, text) for lang, texts in _PICTURES.items() for text in texts]


@pytest.mark.parametrize(("lang", "text"), PICTURES)
def test_an_everyday_picture_still_draws(lang: str, text: str) -> None:
    assert composer_image_intent(text, []).request is not None
    assert read_in(text)[:1] == [lang]


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        # Sizes, looks, numbers and "my" before the noun; colours, places and poses after.
        ("Dibújame dos gatitos", "dos gatitos"),
        ("Dibújame mi casa", "mi casa"),
        ("Dibújame un gato negro en la playa", "gato negro en la playa"),
        ("Dibújame un unicornio con alas", "unicornio con alas"),
        ("Dibújame un perro y un gato", "perro y un gato"),
        ("Dessine-moi un petit chat", "petit chat"),
        ("Dessine-moi un chat qui joue du piano", "chat qui joue du piano"),
        ("Disegnami un bel tramonto", "bel tramonto"),
        ("Genera un'immagine di un castello tra le nuvole", "castello tra le nuvole"),
        ("Me desenhe um pôr do sol", "pôr do sol"),
        ("Me desenhe um cachorro de óculos", "cachorro de óculos"),
        ("Dibujame un leon", "leon"),
        # German: adjective endings, compounds of listed parts.
        ("Zeichne mir einen süßen Hund mit Hut", "süßen Hund mit Hut"),
        ("zeichne mir einen süßen hund", "süßen hund"),
        ("Zeichne mir einen Feuerdrachen", "Feuerdrachen"),
        ("Zeichne mir ein Piratenschiff", "Piratenschiff"),
        ("Erstelle ein Bild von einem Leuchtturm im Sturm", "Leuchtturm im Sturm"),
        # Russian: adjective and noun cases made from the listed forms.
        ("Нарисуй мне белого медведя", "белого медведя"),
        ("Нарисуй мне божью коровку", "божью коровку"),
        ("Создай картинку с котом", "с котом"),
        ("Нарисуйте мне замок в облаках", "замок в облаках"),
        ("Нарисуй мне принцессу в замке", "принцессу в замке"),
        # Turkish closes with the noun; "with", "in" and compound forms are made.
        ("Bana bir kutup ayısı çiz", "kutup ayısı"),
        ("Bana bir ayı çiz", "ayı"),
        ("Bana bir gün batımı çiz", "gün batımı"),
        ("Bana bir uzay gemisi çiz", "uzay gemisi"),
        ("Bana şapkalı bir kedi çiz", "şapkalı bir kedi"),
        ("Bulutlarda bir kale resmi oluştur", "Bulutlarda bir kale"),
        ("Gün batımında bir aslan resmi oluştur", "Gün batımında bir aslan"),
        ("ቀይ መኪና ሳልልኝ", "ቀይ መኪና"),
    ],
)
def test_a_subject_of_listed_words_draws(text: str, subject: str) -> None:
    assert extract_image_gen_prompt(text) == subject


@pytest.mark.parametrize(
    "text",
    [
        # Not on any list: a table, a plan, a story, a portrait, a map, the future.
        "Dibújame un cuadro comparativo entre iPhone y Android",
        "Zeichne mir einen Grundriss meiner Wohnung",
        "Нарисуй мне сказку на ночь",
        "Bana bir uyku masalı çiz",
        "Dibújame un retrato de mi gato",
        "Dibújame un mapa del tesoro",
        "Dessine-moi un avenir meilleur",
        "Dibújame una ciudad del futuro",
        # A German compound: its last part ends no compound, or its first is no listed word.
        "Zeichne mir einen Muskelkater",
        "Zeichne mir eine Eselsbrücke",
        "Zeichne mir einen Stammbaum",
        "Zeichne mir eine Glühlampe",
        "Zeichne mir einen Zufallswald",
        "Zeichne mir einen Binärbaum",
        "Zeichne mir eine Wheatstone-Brücke",
        "Zeichne mir eine Tabelle mit Katzen",
        "Нарисуй мне строение цветка",
        # Definite in Turkish: the bear, the lion.
        "Bana ayıyı çiz",
        "Bana aslanı çiz",
        # Something more than a picture said with a verb: answered, not drawn.
        "ኮፍያ ያደረገች ድመት ሳልልኝ",
    ],
)
def test_a_subject_with_an_unlisted_noun_is_answered(text: str) -> None:
    assert extract_image_gen_prompt(text) is None
    assert composer_image_intent(text, []).request is None


@pytest.mark.parametrize(
    "text",
    [
        # Text or code asked for as a drawing.
        "Dibújame un gato en ASCII",
        "Dessine-moi un chat en SVG",
        "Zeichne mir einen Roboter in Python",
        "Disegnami un gatto con le emoji",
        "Desenha-me um gato em LaTeX",
        "Нарисуй мне кота символами",
        "Bana ASCII ile bir kedi çiz",
        "በASCII ድመት ሳልልኝ",
        # Data structures and circuits on a listed tree, forest or bridge.
        "Dibújame un árbol binario",
        "Dessine-moi une forêt aléatoire",
        "Disegnami un albero rosso e nero",
        "Нарисуй мне красно-чёрное дерево",
        "Нарисуй мне диодный мост",
        "Bana bir ikili ağaç çiz",
        "Dibújame un puente de Wheatstone",
        # Maths and physics on an everyday noun; figures of speech.
        "Dibújame una pizza dividida en fracciones",
        "Zeichne mir einen Kuchen mit den Prozenten der Wahl",
        "Dessine-moi une étoile dans un repère orthonormé",
        "Dibújame un gato con una tabla de multiplicar",
        "Dibújame un volcán con sus partes",
        "Zeichne mir eine Blume mit ihren Teilen",
        "Нарисуй мне дерево вероятностей",
        "Dibújame una montaña de deudas",
        "Bana bir soy ağacı çiz",
        "የቤተሰብ ዛፍ ሳልልኝ",
    ],
)
def test_a_listed_noun_with_an_unlisted_word_is_answered(text: str) -> None:
    assert extract_image_gen_prompt(text) is None
    assert composer_image_intent(text, []).request is None


@pytest.mark.parametrize(
    "text",
    [
        "Dibújame un perro y sugiéreme nombres",
        "Dessine-moi un chien et propose-moi des noms",
        "Zeichne mir einen Hund und gib ihm Namen",
        "Disegnami un cane e suggeriscimi nomi",
        "Desenha-me um cachorro e sugira nomes",
        "Нарисуй мне собаку и придумай ей имя",
        "Bana bir köpek çiz ve isim öner",
        "ውሻ ሳልልኝና ስም ጠቁመኝ",
    ],
)
def test_a_second_request_after_the_picture_is_answered(text: str) -> None:
    """The second request is not swallowed into the picture's subject: the line is answered."""
    assert extract_image_gen_prompt(text) is None
    assert composer_image_intent(text, []).request is None


@pytest.mark.parametrize(
    ("code", "words"),
    [
        # "and" joins two drawable nouns, never a describing word alone.
        ("es", ["árbol", "rojo", "y", "negro"]),
        ("es", ["gato", "y"]),
        # A subject ends on a noun or a describing word, never on "of" or "with".
        ("es", ["gato", "con"]),
        ("fr", ["chat", "de"]),
        # A noun is needed: describing words alone draw nothing.
        ("de", ["kleine", "rote"]),
        # Turkish and Amharic close with the noun.
        ("tr", ["kedi", "kırmızı"]),
    ],
)
def test_a_subject_needs_its_nouns_in_place(code: str, words: list[str]) -> None:
    assert not names_drawable(code, words)


@pytest.mark.parametrize("code", sorted(NOUNS))
def test_every_language_lists_its_common_things(code: str) -> None:
    """About 300 to 450 entries a language (Amharic fewer: only the sure words)."""
    assert len(NOUNS[code].entries) >= (120 if code == "am" else 350)
    assert DESCRIBE[code] and GLUE[code]


@pytest.mark.parametrize(
    ("code", "word"),
    [
        ("es", "mapa"),
        ("es", "planta"),
        ("fr", "tableau"),
        ("de", "Herz"),
        ("it", "piano"),
        ("pt", "planta"),
        ("ru", "схему"),
        ("tr", "harita"),
        ("am", "ካርታ"),
    ],
)
def test_task_nouns_are_not_listed(code: str, word: str) -> None:
    assert not names_drawable(code, [word])


@pytest.mark.parametrize(
    ("code", "text", "words"),
    [
        ("es", "Dibújame un árbol binario", ["árbol", "binario"]),
        ("es", "Dibújame un gato en ASCII", ["gato", "en", "ascii"]),
        ("fr", "Dessine-moi un chat en ASCII", ["chat", "en", "ascii"]),
        ("de", "Zeichne mir einen binären Baum", ["binären", "baum"]),
    ],
)
def test_format_and_data_structure_words_are_not_listed(
    code: str, text: str, words: list[str]
) -> None:
    """A lone descriptor never draws (a subject needs a noun), so each word is read beside
    a listed noun: the noun draws, the subject with the word does not."""
    assert any(names_drawable(code, [word]) for word in words)
    assert not names_drawable(code, words)
    assert extract_image_gen_prompt(text) is None
