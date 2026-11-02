"""A school exercise gets a note beside it: the textbook's answer, at its level
(2026-10-30, a Class 8 physical science book, then a Class 9 book in every subject).
Any other question about the world gets the lighter factual note."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.chat.message_notes import message_notes
from app.modules.chat.prompt_constants.school_question import (
    FACTUAL_QUESTION_NOTE,
    SCHOOL_QUESTION_NOTE,
    question_hint,
    school_question_hint,
)


@pytest.mark.parametrize(
    "query",
    [
        "Hoisting a flag is related to [ ] a) push b) pull c) Push and pull both d) pressure",
        "The lowest temperature at which a substance catches fire is called its a) Ignition "
        "temperature b) Maximum temperature c) Room temperature d) Normal temperature",
        "Let the forces F1 and F2 act on the table in opposite directions, F1 > F2, the "
        "Fnet = a) F1-F2 b) F1+F2 c) 0 d) 2F2-F1",
        "Give two examples each for a contact force and a force at a distance.",
        "Explain the physical properties of metals with suitable examples.",
        "Distinguish between a contact force and a force at a distance.",
        "How is the property malleability of metals used in our daily life?",
        "Suppose you have to go out on that day. Would you carry an umbrella? Explain.",
        "Do you agree with the statement “friction is both good and evil”? Explain.",
        "Why do tools meant for cutting always have sharp edges? (AS1)",
        # A Class 9 book (2026-10-30): the shapes every textbook prints, in any subject.
        "If a plant is unable to transport food from leaves to roots which tissue is "
        "malfunctioning?\n(i) Xylem\n(ii) Phloem\n(iii) Epidermis\n(iv) Sclerenchyma",
        "Two similar animal cells are placed in two different solutions. Which statement "
        "provides the correct explanation?\n(i) Salt molecules moved into Cell Y, causing "
        "it to shrink.\n(ii) Water moved into Cell X and more water moved out of Cell Y than "
        "the salt solution entered in it.\n(iii) Water moved into Cell X and moved out of "
        "Cell Y through the cell membrane.\n(iv) Solute movement caused osmosis in both.",
        "Assertion: Cardiac muscle can contract continuously without fatigue.\nReason: "
        "Cardiac muscle cells have a high number of mitochondria.",
        "Fill in the blanks. Power is defined as the ______ at which work is done.",
        "Two students, Renu and Rohit, were having a discussion on the plastids. Who is "
        "correct? Justify your answer.",
        "A farmer wants to produce a large number of genetically identical plants quickly. "
        "Suggest suitable reproduction methods.",
        "A car starts from rest and its velocity reaches 24 m/s in 6 s. Find the average "
        "acceleration and the distance travelled in these 6 s.",
        "Determine the formula unit mass of (i) ammonium nitrate (NH4NO3), (ii) phosphoric "
        "acid (H3PO4), (iii) sodium hydrogencarbonate (NaHCO3).",
        "Identify the pair that incorrectly matches the cell organelle with its function.",
        "Write the formulae for the compounds formed by magnesium and nitrogen.",
        "A vehicle's parking sensor emits ultrasonic waves at 40 kHz. When the beep starts "
        "at 1.2 m from the obstacle, how much time does the wave take to come back?",
    ],
)
def test_a_school_exercise_gets_the_note(query: str) -> None:
    hint = school_question_hint(query)
    assert hint is not None and hint.startswith(SCHOOL_QUESTION_NOTE)


def test_a_multiple_choice_question_is_told_to_name_one_option_first() -> None:
    hint = school_question_hint("Which is a natural fibre? a) Rayon b) Nylon c) Polyester d) Silk")
    assert hint is not None and "name the one correct option" in hint


@pytest.mark.parametrize(
    "query",
    [
        "Why do cats purr?",
        "Explain how a mortgage works",
        "What are the differences between a Roth and a traditional IRA?",
        "Give me two examples of good cover letter openings",
        "I bought a) bread b) milk c) eggs today",
        "Plan: a) gym b) lunch c) call mom",
        "Should we pick a) Postgres b) Mongo c) Dynamo for the new service?",
        "Do you agree with the statement that AI will replace jobs?",
        "Is this a good idea? Why?",
        # Review (2026-10-30): code, checklists and requests that use an exercise's words.
        "Why does def f(x=[]): keep growing between calls?",
        "const items = []; items.push(1) why is this allowed with const?",
        "- [ ] buy milk\n- [ ] call mom\nturn this into a schedule",
        "Define a Python function that reverses a string.",
        "Write a short note to my landlord saying the heater is broken.",
        "Classify the following emails as urgent or not",
        "Give reasons for choosing Postgres over MongoDB for our app",
        "Explain Python decorators with an example",
        "In the experiment we ran last week, conversion went up 3%",
        "Explain.",
        "Should I refinance now or wait? Explain why.",
        "What are the opening hours of a) the Louvre b) the Musee d Orsay c) the Pompidou",
        "How are these stocks doing: a) Tesla b) Nvidia c) Apple",
        "Plan a 5-day itinerary covering a) Rome b) Florence c) Venice",
        "Write three taglines for a coffee brand: a) playful b) premium c) eco",
        "What is the current Fed funds rate? a) 3.5% b) 4.25% c) 5%",
        # Second review (2026-10-30): taste, every option wanted, adult definitions, code.
        "Summarize these options for the team: a) hire b) outsource c) wait",
        "Which of these pizza toppings go well together: a) pineapple b) ham c) anchovies",
        "Which is better for a beginner: a) Python b) JavaScript c) Rust",
        "Help pick a name for the cat: a) Milo b) Luna c) Oliver",
        "Which sounds more professional in an email: a) Hi b) Hello c) Dear",
        "Define gaslighting.",
        "Give two examples of good cover letter openings for a software engineer.",
        'Do you agree with the statement "remote work kills culture"?',
        "What does the error TypeError: undefined is not a function mean in JavaScript? Explain.",
    ],
)
def test_anyone_elses_question_is_no_exercise(query: str) -> None:
    assert school_question_hint(query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Rohan studies from 6 PM to 7:30 PM. The minute hand is 7 cm long. What is its "
        "(i) distance travelled, (ii) displacement, (iii) speed, and (iv) velocity?",
        "Fill in the blanks.\n(i) Work done = ______ × ______\n(ii) 1 joule is done when a "
        "force of ______ newton acts\n(iii) Power is the ______ at which work is done.",
        "If a species has 11 protons, (i) what is its atomic number? (ii) is it neutral, a "
        "cation or an anion? (iii) write its electronic configuration.",
    ],
)
def test_parts_are_not_options(query: str) -> None:
    hint = school_question_hint(query)
    assert hint is not None and "It asks you to choose" not in hint


def _user() -> SimpleNamespace:
    return SimpleNamespace(emoji_use="some", locale="en", custom_instructions=None)


def test_the_note_sits_beside_the_message() -> None:
    notes = message_notes("Distinguish between metals and non-metals.", [], _user())
    assert any(note.startswith(SCHOOL_QUESTION_NOTE) for note in notes)


def test_a_lesson_keeps_its_own_way() -> None:
    notes = message_notes(
        "Teach me friction. Distinguish between static and sliding friction.", [], _user()
    )
    assert not any(note.startswith(SCHOOL_QUESTION_NOTE) for note in notes)


# The rerun (2026-10-30) still opened "Most pans actually do have metal handles" and
# "it doesn't, really": any question about the world gets the textbook answer first too.
@pytest.mark.parametrize(
    "query",
    [
        "Why don't cooking pans have metal handles?",
        "Why does the image in a plane mirror suffer lateral inversion?",
        "Why is phosphorus preserved in water?",
        "Why do cats purr?",
        "Explain how a rainbow forms",
        "Mitochondria and chloroplasts are two organelles. Discuss how they are similar.",
        "Electrons move around the nucleus in orbits. Why do they not fly away?",
    ],
)
def test_a_question_about_the_world_gets_the_factual_note(query: str) -> None:
    assert question_hint(query) == FACTUAL_QUESTION_NOTE


@pytest.mark.parametrize(
    "query",
    [
        "Why is my car battery dead?",
        "What is the current price of gold?",
        "What metal is best for a wedding ring?",
        "Why does my code throw a TypeError?",
        "Write a poem about the rain",
        "Translate 'good morning' into French",
        "hi",
        "Which laptop would you recommend for video editing?",
    ],
)
def test_a_personal_current_taste_or_task_message_gets_no_note(query: str) -> None:
    assert question_hint(query) is None


@pytest.mark.parametrize(
    ("content", "nothing"),
    [
        (
            "The lowest temperature at which a substance catches fire is called its "
            "a) Ignition temperature b) Maximum temperature c) Room temperature "
            "d) Normal temperature",
            True,
        ),
        ("What is the SI unit of force?", True),
        ("Who won the champions league final?", False),
        ("What is the current Fed funds rate? a) 3.5% b) 4.25% c) 5%", False),
    ],
)
def test_a_textbook_question_has_nothing_to_look_up(content: str, nothing: bool) -> None:
    # Its note said not to search, and the reply searched anyway (2026-10-30).
    from app.modules.chat.tool_loop.reply_calls import _nothing_to_look_up

    assert _nothing_to_look_up(content, None) is nothing


# Review (2026-10-30): anyone's own matter is no exercise, whatever its shape, and so is
# never kept from searching.
@pytest.mark.parametrize(
    "query",
    [
        "Biden said inflation is falling. Is that correct?",
        "Mark says Bitcoin will hit 200k. Is he right?",
        "Elon claims Mars colonies by 2030. Is that realistic?",
        "Predict who will win the Super Bowl",
        "Hello! Which is more popular: a) Taylor Swift b) Drake c) Beyoncé?",
        "Some friends want to go to Bali for 7 days with 2000 each. Is that enough?",
        "Which neighbourhood is safer: (a) Brooklyn (b) Queens (c) Bronx?",
        "What's the difference between (a) an LLC and (b) an S-corp for taxes?",
        "Estimate how long it takes to drive from Boston to New York",
        "Is intermittent fasting healthy for diabetics? Explain why.",
        "Determine the root cause of the 502s on our nginx server",
        "Predict the output of print(2**10)",
        "Quick questions: (a) is Rust memory safe? (b) does it have a GC?",
        "Calculate my BMI if I weigh 80 kg and am 1.8 m tall",
        "Two options: a) take the job in Berlin b) stay in Toronto. Thoughts?",
        "John says we should refactor the database layer. What do you think?",
        "Indicate your availability for next Tuesday",
        "Justify your previous answer",
        "State whether you can access the internet",
        "Complete the following sentence for my wedding toast: Love is",
        "Classify the following tweets as positive or negative",
        "Sarah and John were arguing about whether to move to Austin. Who is correct?",
    ],
)
def test_anyones_own_matter_is_no_exercise(query: str) -> None:
    assert school_question_hint(query) is None


@pytest.mark.parametrize(
    "query",
    [
        "Write a short note on the Harappan civilisation.",
        "Give an account of the Mughal administration.",
        "Mention two uses of baking soda.",
        "What is meant by the term 'osmosis'? Give an example.",
        "Define photosynthesis. Write the balanced chemical equation for it.",
        "Change the following sentences into passive voice: He wrote a letter.",
        "A ball is thrown vertically upwards with a velocity of 49 m/s. Calculate the maximum "
        "height.",
        "A car accelerates from rest to 72 km/h in 5 minutes. Find the acceleration.",
        # NCERT Class 10 (2026-10-30): got a photo above its equations.
        "Write one equation each for decomposition reactions where energy is supplied in the "
        "form of heat, light or electricity.",
        "Write a balanced chemical equation for the reaction of zinc with dilute sulphuric acid.",
    ],
)
def test_more_textbook_shapes_are_exercises(query: str) -> None:
    assert school_question_hint(query) is not None


@pytest.mark.parametrize(
    "query",
    [
        "Why don't cooking pans have metal handles?",
        "Why is phosphorus preserved in water?",
        "Why does the image in a plane mirror suffer lateral inversion?",
        "What causes earthquakes?",
        "How do we hear sound?",
    ],
)
def test_a_plain_science_question_has_nothing_to_look_up(query: str) -> None:
    # Main kept these from searching (1278d63b6); the factual note must not undo it.
    from app.modules.chat.tool_loop.reply_calls import _nothing_to_look_up

    assert _nothing_to_look_up(query, None) is True


@pytest.mark.parametrize(
    "query",
    [
        "Can you set a reminder for 5pm?",
        "What's a good name for a cat?",
        "Is a 5-star hotel worth it in Paris?",
        "Is it normal to feel anxious before a job interview?",
        "What does the Fed's rate cut mean for mortgages?",
    ],
)
def test_a_task_feeling_taste_or_news_gets_no_factual_note(query: str) -> None:
    assert question_hint(query) is None


# Second review (2026-10-30): a book's "current", "cost", "President" and "World War I"
# are no news, and an exercise's note never keeps a changing question from its search.
@pytest.mark.parametrize(
    "query",
    [
        "A resistor of 10 Ω is connected to a 5 V battery. Find the current.",
        "A current of 2 A flows through a wire for 5 minutes. Calculate the charge.",
        "What is the direction of induced current in a coil? Explain.",
        "Find the cost of fencing a rectangular field 120 m long and 80 m wide at Rs 15 per metre.",
        "Who was the first President of the United States?",
        "Outline the causes of World War I.",
        "Why do we need a fuse in an electric circuit?",
        "Give reasons: Aluminium is used for making cooking utensils.",
        "Account for the fact that ionic compounds have high melting points.",
    ],
)
def test_a_books_words_are_no_news(query: str) -> None:
    assert question_hint(query) is not None


@pytest.mark.parametrize(
    "query",
    [
        "Which of the following should our team prioritize next quarter?\na) onboarding\n"
        "b) billing\nc) search",
        "Which of the following will the Fed do in December? a) cut b) hold c) hike",
        "Which of the following teams won the 2026 World Series?\n(a) Dodgers\n(b) Yankees\n(c) Mets",
        "Which of the following is a good investment: a) gold b) bonds c) stocks",
        "Was there an earthquake in Japan?",
        "When is the next total solar eclipse?",
        "Is Ozempic safe for weight loss?",
        "How many Starlink satellites are in orbit?",
        "Which car brand is more reliable, Toyota or Honda?",
    ],
)
def test_a_changing_or_everyday_question_keeps_its_search_and_lane(query: str) -> None:
    from app.modules.turn_reading.school_question import (
        has_nothing_to_look_up,
        needs_reasoned_choice,
    )

    assert not has_nothing_to_look_up(query)
    assert not needs_reasoned_choice(query)


# NCERT Class 10 (2026-10-30): "pH" read as a camel-cased identifier, "What will happen if"
# as a forecast, and "Explain your answer." went unread, so these got no note at all.
@pytest.mark.parametrize(
    "query",
    [
        "Fresh milk has a pH of 6. How do you think the pH will change as it turns into curd? "
        "Explain your answer.",
        "Why does a solution of pH 2 have more hydrogen ions than one of pH 6?",
        "What will happen if we kill all the organisms in one trophic level?",
        "What role does mRNA play in making proteins?",
    ],
)
def test_a_books_science_words_and_hypotheticals_get_a_note(query: str) -> None:
    assert question_hint(query) is not None


@pytest.mark.parametrize(
    "query",
    [
        "Why does useState not update right away?",
        "What does getUserById return when the row is missing?",
        "What will happen to Bitcoin after the halving?",
        "What will happen in the election?",
        "What will happen if I quit my job?",
        # Review: a forecast, a product and research that changes keep their search.
        "What will happen if the volcano erupts again?",
        "What will happen if the gold price drops?",
        "Is the iPhone 17 screen more reflective than the 16?",
        "Are mRNA vaccines linked to heart inflammation?",
        "Why is xValue undefined after the loop?",
        "What is a uFunc in numpy?",
        "How do I update iOS on my phone?",
        "Write a formula in Excel to sum column B.",
    ],
)
def test_code_news_and_ones_own_still_get_no_note(query: str) -> None:
    assert question_hint(query) is None


# 2026-11-01: a name in code ending in capitals read as a science term, so a developer's
# question got a textbook note; science written the same way still gets one.
@pytest.mark.parametrize(
    ("query", "note"),
    [
        ("What does innerHTML return for an empty div?", False),
        ("Why does toJSON drop undefined fields?", False),
        ("What is the difference between userID and userId in the schema?", False),
        ("When should parseURL be called before fetch?", False),
        ("What is the pOH of a solution whose pH is 3?", True),
        ("What is the pKa of acetic acid?", True),
        ("How does siRNA silence a gene?", True),
        ("Why is mtDNA inherited from the mother?", True),
        ("What does cAMP do in cell signalling?", True),
        ("Convert 760 mmHg to kPa.", True),
        ("How many kWh does a 2 kW heater use in 3 hours?", True),
        ("What is the energy in keV of a photon of wavelength 0.1 nm?", True),
        # Review of #2200: longer prefixes on a nucleic acid, and inches of mercury.
        ("What does circRNA do in a cell?", True),
        ("What does microRNA do in a cell?", True),
        ("How does tracrRNA guide Cas9?", True),
        # Third review: any lower case word ending in capitals may be a lab term.
        ("What is a high hsCRP?", True),
        ("What does oxLDL do in arteries?", True),
        ("How does ddPCR work?", True),
        ("What is sdLDL?", True),
        ("Why does isNaN return true for a string?", False),
        ("How do I read the baseURL from config?", False),
        ("How is rtPCR used to detect a virus?", True),
        ("Convert 30 inHg to kPa.", True),
    ],
)
def test_a_name_in_code_is_code_and_a_science_term_is_science(query: str, note: bool) -> None:
    assert (question_hint(query) is not None) is note


@pytest.mark.parametrize(
    "query",
    [
        "Was Napoleon a good leader? Explain your answer.",
        "Is coffee bad for you? Explain your answer.",
    ],
)
def test_an_opinion_closing_on_your_answer_is_no_exercise(query: str) -> None:
    assert school_question_hint(query) is None


@pytest.mark.parametrize(
    "query",
    [
        "A ball of mass 2 kg falls from 10 m. Does it gain or lose energy? Explain your answer.",
        "Is sound a longitudinal wave? Justify your answer.",
        "Can a metal displace hydrogen from water? Give reasons for your answer.",
    ],
)
def test_an_exercise_closing_on_your_answer_is_an_exercise(query: str) -> None:
    assert school_question_hint(query) is not None


# A blank is a word to fill in a sentence of its own; a run of dots or underscores in a chat
# message is punctuation (2026-11-01: "so......", "lol ok ___ whatever" and "Trip
# ideas.......... Paris or Rome?" read as a textbook's blank, so their replies lost their
# emoji and the trip question its search).
@pytest.mark.parametrize(
    ("query", "blank"),
    [
        ("The process by which plants make food is called ________.", True),
        ("The ........ is the powerhouse of the cell.", True),
        ("The …… is the powerhouse of the cell.", True),
        ("Water boils at ___ °C", True),
        ("Fill in the blanks. Power is defined as the ______ at which work is done.", True),
        ("complete the sentence: If I had known you were coming, I ___", True),
        # A worksheet's equation or label (PR review).
        ("5 + 3 = ___", True),
        ("Solve: 12 ÷ 4 = ____", True),
        ("___ + 3 = 8", True),
        ("Capital of France: ____", True),
        ("so......", False),
        ("so...... what do you think", False),
        ("wait……", False),
        ("lol ok ___ whatever", False),
        ("Trip ideas.......... Paris or Rome?", False),
    ],
)
def test_a_blank_is_a_word_missing_from_a_sentence(query: str, blank: bool) -> None:
    from app.modules.turn_reading.school_question import has_nothing_to_look_up, in_textbook_form

    assert in_textbook_form(query) is blank
    assert has_nothing_to_look_up(query) is blank
