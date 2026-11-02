"""A checklist the user asked for: Markdown task lines the phone draws as checkboxes.

"Give me a packing checklist" came back as bold-led bullets, with nothing to
tick. The phone renders ``- [ ]`` / ``- [x]`` (GFM task lists) as boxes, so an
explicit request for a checklist, to-do list or task list asks for them. A
list that is only mentioned ("thanks for the checklist"), one that already
exists ("send me my to-do list"), or how to make one in an app ("a checklist in
Notion") is not a request for one.
"""

from __future__ import annotations

CHECKLIST_FORMAT_HINT = (
    "This turn asked for a checklist. Write every item to tick off as a Markdown task "
    "line, `- [ ] Item`, so it shows as a checkbox; nothing else in the list. Group items "
    "under short `###` headings when they fall into categories. One line per item: the "
    "thing, then a few words of detail after a colon only when it helps. Use `- [x]` only "
    "for an item the user said is already done. Never a pipe table."
)
