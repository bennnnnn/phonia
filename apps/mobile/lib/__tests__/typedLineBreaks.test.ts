import { withTypedLineBreaks } from "@/lib/markdown/typedLineBreaks";

describe("withTypedLineBreaks", () => {
  it.each([
    [
      "the two lines a clarify card sends",
      "Budget range: $1,200 - $2,500\nPrimary use: Programming & development",
      "Budget range: $1,200 - $2,500  \nPrimary use: Programming & development",
    ],
    ["a line already ending in spaces", "one  \ntwo", "one  \ntwo"],
    ["a blank line stays a paragraph break", "one\n\ntwo", "one\n\ntwo"],
    ["one line is untouched", "just one line", "just one line"],
    [
      "fenced code keeps its lines exactly",
      "look:\n```python\nx = 1\ny = 2\n```\nthanks",
      "look:\n```python\nx = 1\ny = 2\n```\nthanks",
    ],
  ])("%s", (_name, text, expected) => {
    expect(withTypedLineBreaks(text)).toBe(expected);
  });
});
