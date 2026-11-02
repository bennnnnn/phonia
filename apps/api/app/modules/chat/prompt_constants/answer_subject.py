"""The one thing a turn asks about ("what is a capybara"), for the photo above the answer.

The general photo rule sits deep in a long prompt, and the small chat model skipped
it: "what is a capybara", "tell me about Lalibela" and "who is Haile Gebrselassie"
came back without a photo, while "where is kenya", which gets its own short hint,
always opened with one. This names the subject in a hint of its own; the model
still decides whether the thing is worth seeing ("what is recursion" is not).
"""

from __future__ import annotations


def subject_photo_hint(subject: str) -> str:
    """The photo rule for this turn's one subject; the model judges if it is worth seeing."""
    return (
        f'This turn asks about "{subject}". If that is something people would want to see (a '
        "place, landmark, animal, plant, person, food, product, vehicle or artwork), open the "
        f"reply with ```photo\n{subject}\n```, then answer as usual. An idea, a word, a feeling, "
        "or a process or concept from science, history or economics gets no photo, even when "
        'something visible is involved ("photosynthesis", "recursion", "inflation", "love").'
    )
