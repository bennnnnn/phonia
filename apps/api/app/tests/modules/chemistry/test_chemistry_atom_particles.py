"""One atom's or ion's particles from any facts a question gives (2026-10-30, a Class 9 book):
"An atom 70X has 31 electrons. How many neutrons?" was answered 70 - 31 = 40."""

from __future__ import annotations

import pytest

from app.modules.chemistry.block import build_verified_chemistry
from app.modules.chemistry.direct import maybe_direct_chemistry_reply
from app.modules.chemistry.extract import extract_chemistry_intent
from app.modules.chemistry.request import is_chemistry_question


def _answer(question: str) -> str | None:
    intent = extract_chemistry_intent(question)
    if intent is None or intent.chemistry_op != "atom_particles":
        return None
    verified = build_verified_chemistry(intent)
    return None if verified is None else verified.result.answer


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        (
            "An atom 70X has 31 electrons. How many neutrons are there in its nucleus?",
            "Neutrons = 39",
        ),
        (
            "An atom has 79 protons and a mass number of 197. Calculate (i) the number of "
            "neutrons, and (ii) the number of electrons.",
            "Neutrons = 118\nElectrons = 79",
        ),
        (
            "For an atom of magnesium with a mass number of 24 and atomic number 12, determine "
            "the number of (i) protons, (ii) neutrons, (iii) electrons, and also illustrate the "
            "arrangement of electrons in a magnesium atom.",
            "Protons = 12\nNeutrons = 12\nElectrons = 12\nElectronic configuration = 2, 8, 2",
        ),
        (
            "An element has atomic number 15 and 16 neutrons. What are its mass number, number "
            "of protons, number of electrons?",
            "Protons = 15\nElectrons = 15\nMass number A = 31",
        ),
        (
            "If a species has 11 protons, 12 neutrons and 10 electrons then (i) what is its "
            "atomic number and mass number? (ii) is it neutral, a cation or an anion? (iii) "
            "write its electronic configuration. (iv) name the species.",
            "Atomic number Z = 11\nMass number A = 23\nElectronic configuration = 2, 8\n"
            "Species = Sodium cation (Na⁺)\nType = cation",
        ),
        (
            "How many protons, neutrons and electrons are in 27Al?",
            "Protons = 13\nNeutrons = 14\nElectrons = 13",
        ),
        ("What is the number of electrons in Na+?", "Electrons = 10"),
        ("An ion has 17 protons and 18 electrons. What is its charge?", "Charge = -1"),
        ("What is the valency of an element with atomic number 16?", "Valency = 2"),
    ],
)
def test_every_quantity_asked_is_derived(question: str, answer: str) -> None:
    assert is_chemistry_question(question)
    assert _answer(question) == answer


@pytest.mark.parametrize(
    ("question", "operation"),
    [
        # One number a one-line law reads keeps that law's layout.
        ("How many neutrons are in carbon-14?", "neutron_count"),
        (
            "Oxygen has atomic number 8 and 10 electrons. What is the charge of the ion?",
            "ion_charge",
        ),
        # Past calcium the shell rule stops: the aufbau reader answers, or the ion declines.
        ("What is the electron configuration of Fe?", "electron_configuration"),
        ("How many valence electrons does nitrogen have?", "valence_electrons"),
    ],
)
def test_another_reader_keeps_its_question(question: str, operation: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is not None and intent.chemistry_op == operation


@pytest.mark.parametrize(
    "question",
    [
        "Calculate the mass of 2 moles of electrons",
        "The species 27Al, 80Br- and 201Hg2+ have 13, 35 and 80 protons, respectively. How "
        "many electrons and neutrons do they have?",
        "Imagine all the electrons are replaced with hypothetical particles 500 times heavier.",
        "Write the electron configuration of Fe3+.",
    ],
)
def test_more_than_one_atom_or_an_amount_is_not_read(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op != "atom_particles"


def test_a_question_with_more_parts_than_answers_goes_to_the_model() -> None:
    question = (
        "An element X has a mass number of 35 and contains 18 neutrons. (i) How many electrons "
        "and protons does X have? (ii) What is its atomic number? (iii) Identify the element X. "
        "(iv) Write its electronic configuration. (v) How many valence electrons does it have? "
        "(vi) What will be the mass number if two neutrons are added? (vii) What will be the "
        "relation of X with the new atom?"
    )
    intent = extract_chemistry_intent(question)
    # Part (v) asks for valence electrons, some of the electrons: the reader leaves the
    # whole question to the model (2026-10-30), and no instant reply answers one part.
    if intent is None:
        return
    verified = build_verified_chemistry(intent)
    assert verified is not None
    assert (
        maybe_direct_chemistry_reply(verified, has_image_attachment=False, user_text=question)
        is None
    )


# Review (2026-10-30): electrons gained or lost make the charge; a shell's count is no total.
@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("An atom with 17 protons gains 1 electron. What is the charge of the ion?", "Charge = -1"),
        (
            "Magnesium loses 2 electrons. What is the electronic configuration of the ion?",
            "Electronic configuration = 2, 8",
        ),
        (
            "An element with atomic number 8 gains 2 electrons. How many protons and what charge?",
            "Protons = 8\nCharge = -2",
        ),
        (
            "An atom has 3 electrons in its outermost shell and atomic number 13. What is its "
            "valency?",
            "Valency = 3",
        ),
        ("An element X has atomic number 7. Its ion X3- has how many electrons?", "Electrons = 10"),
        ("Carbon-14 has how many neutrons and electrons?", "Neutrons = 8\nElectrons = 6"),
        (
            "Uranium-238 has 92 protons. How many neutrons and electrons?",
            "Neutrons = 146\nElectrons = 92",
        ),
    ],
)
def test_gained_lost_and_shell_counts_read_right(question: str, answer: str) -> None:
    assert _answer(question) == answer


@pytest.mark.parametrize(
    "question",
    [
        "How many electrons pass through a wire if a charge of 10C flows?",
        "A capacitor stores 12C of charge. How many electrons is that?",
        "How many electrons does a 24V battery push?",
        "How many electrons per second flow through a 100W bulb?",
        "My B-12 levels are low, how many protons do I need?",
        "Our 40K salary: how many electrons?",
    ],
)
def test_a_unit_is_no_nuclide(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op != "atom_particles"


@pytest.mark.parametrize(
    "question",
    [
        "An atom has 11 protons, 12 neutrons and mass number 25. How many electrons?",
        "A Na+ ion has 11 electrons. How many protons?",
        "An atom with mass number 12 and 14 neutrons: how many protons?",
    ],
)
def test_givens_that_disagree_verify_nothing(question: str) -> None:
    assert _answer(question) is None


@pytest.mark.parametrize(
    "question",
    [
        "Atomic number 26, mass number 56: protons, neutrons, electrons and electronic "
        "configuration?",
        "What is the electronic configuration of magnesium? How many protons?",
    ],
)
def test_a_reply_that_would_drop_an_ask_is_the_models(question: str) -> None:
    intent = extract_chemistry_intent(question)
    # Part (v) asks for valence electrons, some of the electrons: the reader leaves the
    # whole question to the model (2026-10-30), and no instant reply answers one part.
    if intent is None:
        return
    verified = build_verified_chemistry(intent)
    assert verified is not None
    assert (
        maybe_direct_chemistry_reply(verified, has_image_attachment=False, user_text=question)
        is None
    )


@pytest.mark.parametrize(
    "question",
    [
        # Second review (2026-10-30): decay, orbits, counts of ions, comparisons, masses
        # and an ion named only in words are not one atom's particles to read.
        "A 238U nucleus emits an alpha particle. How many protons and neutrons does the "
        "daughter have?",
        "A 14C nucleus undergoes beta decay. How many protons and neutrons does the product have?",
        "Find the radius of the orbit of an electron in a He+ ion.",
        "How many electrons are in 3 Na+ ions?",
        "How many electrons are in Na and Na+?",
        "Which has more electrons, F- or Ne?",
        "How many electrons are in Cl- compared with Ar?",
        "A 2 kg block has how many protons if made of carbon-12?",
        "Oxygen has atomic number 8 and mass number 16. How many electrons are in the oxide ion?",
        "What is the speed of an electron in an atom with 1 proton?",
    ],
)
def test_not_one_atoms_particles(question: str) -> None:
    intent = extract_chemistry_intent(question)
    assert intent is None or intent.chemistry_op != "atom_particles"


def test_an_ions_configuration_asked_as_its_configuration() -> None:
    question = "How many electrons does N3- have and what is its configuration?"
    assert _answer(question) == "Electrons = 10\nElectronic configuration = 2, 8"
