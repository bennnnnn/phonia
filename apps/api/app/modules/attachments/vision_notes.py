"""What the model is told beside the photos it is shown.

A real photo is never "a placeholder or a failed generation". One it cannot read (blurry,
cropped, dark, too small) is said to be unclear, with what is unclear, and the user is asked
for a better one; the model never guesses at text or numbers it cannot see. The maths
scanner says the same in its own words ("Couldn't read that. Check the photo or retake.").
"""

IMAGE_REAL_NOTE = "These images are real. Do not call them placeholders or a failed generation."

UNCLEAR_IMAGE_NOTE = (
    "If a photo is blurry, cropped, too dark or too small to read, say what you cannot make "
    "out and ask for a clearer photo instead of guessing; answer only what is clearly visible."
)

VISION_NOTE = f"{IMAGE_REAL_NOTE} {UNCLEAR_IMAGE_NOTE}"

# Said when a sent photo could not be decoded or did not fit the turn's image budget.
PHOTOS_LEFT_OUT_NOTE = (
    "Not every attached photo could be included. Say that you cannot see the missing one "
    "instead of guessing what it shows."
)
