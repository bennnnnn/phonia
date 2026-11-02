import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";

jest.mock("@/components/LinkPreviewCard", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    LinkPreviewCard: ({ url }: { url: string }) => <Text>{url}</Text>,
  };
});

const QUIZ =
  '```quiz\n{"label": "Exercise 1", "question": "What does d.get(\\"z\\", 0) return?", ' +
  '"options": ["0", "None"], "answer": 0}\n```';

/** A Teach-me lesson as the model streams it: prose, a table, then a quiz. */
const LESSON = `Step 1/3: lookups.\n\n| Key | Value |\n| --- | --- |\n| a | 1 |\n\n${QUIZ}\n\nNext: loops.`;

/** Every text node a reader could see, joined. */
function visibleText(view: ReturnType<typeof render> extends Promise<infer R> ? R : never): string {
  const parts: string[] = [];
  const walk = (node: unknown) => {
    if (typeof node === "string") {
      parts.push(node);
      return;
    }
    if (!node || typeof node !== "object") return;
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    walk((node as { children?: unknown }).children);
  };
  walk(view.toJSON());
  return parts.join("");
}

describe("a streaming lesson never shows half a card or half a table (S7.4, S7.5, S7.8)", () => {
  it("shows no raw quiz JSON and no literal table pipes at any point of the stream", async () => {
    for (let end = 1; end <= LESSON.length; end += 3) {
      const view = await render(<MarkdownContent content={LESSON.slice(0, end)} streaming />);
      const shown = visibleText(view);
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining('"question"') });
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining('"options"') });
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining("|") });
      await view.unmount();
    }
  });

  it("draws the quiz card and the table once the reply is complete", async () => {
    const view = await render(<MarkdownContent content={LESSON} />);
    const shown = visibleText(view);
    expect(shown).toContain('What does d.get("z", 0) return?');
    expect(shown).toContain("Check answer");
    expect(view.getByText("Value")).toBeOnTheScreen();
    expect(shown).not.toContain('"question"');
  });
});
