import { isUnfinishedJson, readJson } from "@/lib/jsonFence";

describe("isUnfinishedJson", () => {
  it.each([
    ['{"question": "What will', true],
    ['{"values": [1, 2', true],
    ['{"question": "a } b', true],
    ["", true],
    ["plain text", true],
    ['{"question": "Q"}', false],
    ["[1, 2]", false],
    // Finished but broken: braces closed, JSON still does not parse.
    ['{"values": [1, 2,]}', false],
    ['{"question": "a\nb"}', false],
    // A brace inside a string does not count.
    ['{"question": "a { b"}', false],
  ])("%j → %s", (content, unfinished) => {
    expect(isUnfinishedJson(content)).toBe(unfinished);
  });
});

describe("readJson", () => {
  it.each([
    ['{"a": 1}', { value: { a: 1 } }],
    ["[1, 2]", { value: [1, 2] }],
    // JSON's null is a value, not a failure.
    ["null", { value: null }],
    ["0", { value: 0 }],
    ['"text"', { value: "text" }],
    ["", null],
    ["plain text", null],
    ['{"a": 1,}', null],
  ])("%j → %j", (text, read) => {
    expect(readJson(text)).toEqual(read);
  });
});
