"""The ```worked block: a calculation no solver checked, written as parts the app lays out.

Told the worked layout in words, the model followed it on one turn and not the next: a
displacement came back as bold inline "**Given:** …", no Answer heading and no card
(2026-11-01). The block's records are read and laid out by the server
(``chat.worked_solution``, ``chat.worked_render``) with the renderer of every verified
reply, so a reply the model works out itself looks the same as a checked one.
"""

from __future__ import annotations

WORKED_BLOCK_CONTRACT = (
    "Worked calculation: this question asks for a value and no server check stands behind "
    "it, so the app lays your working out itself, the same way as every checked answer "
    "(Given, Required, Solution, the formula under its name, Substitution, Answer). Start your reply with one ```worked "
    "block holding the whole solution, and write no working outside it: no heading, no "
    "sentence before it, no Given, Formula, Step or Answer lines of your own, also when the "
    "sum is short. Only a message that asks for no value at all (an explanation, a "
    "definition, a choice between options, a reminder) is answered as usual, with no "
    "block. A graph, chart or diagram it asks for comes after the block. "
    'Inside the block, one record per line, its fields split by " | ", maths in LaTeX '
    "without $, units as plain text (m/s, km/h, kg, °C), and words in the language of "
    "your reply:\n"
    "given: symbol | value | unit | what it is | the value in the unit the formula needs, "
    "only when that differs (LaTeX with its unit)\n"
    "required: symbol | what is asked\n"
    'formula: the name of the law or rule, which heads the formula ("Average speed" '
    "reads Average speed formula) | the formula\n"
    "solve_for: symbol | the formula rearranged for it\n"
    "step: an equation | the move that reached it (for an equation solved one move at a "
    "time, with no formula)\n"
    "substitution: the values put into the formula, one state per line, the last one the "
    "value with its unit\n"
    "answer: symbol | value | unit | a direction or a short note, only if the answer needs "
    "one\n"
    "A question in parts: `part: a | what it finds` before each part's formula, "
    "substitution and answer; the givens and what is asked come once, first. Before the "
    "answer record, check the result: put it back into the formula and redo each "
    "multiplication and division. For example:\n"
    "```worked\n"
    "given: d | 3 | km | distance | 3000\\,\\mathrm{m}\n"
    "given: t | 15 | min | time | 900\\,\\mathrm{s}\n"
    "required: v | average speed\n"
    "formula: Average speed | v = \\frac{d}{t}\n"
    "substitution: v = \\frac{3000}{900}\n"
    "substitution: v = 3.33\\,\\mathrm{m/s}\n"
    "answer: v | 3.33 | m/s\n"
    "```"
)
