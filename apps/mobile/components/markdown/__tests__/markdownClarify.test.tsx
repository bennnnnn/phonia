import { fireEvent, render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { ClarifyActionsProvider, ClarifyMessageScope } from "@/components/rich/clarifyContext";
import { markdownToCopyText } from "@/lib/markdown/plain";

jest.mock("@/components/LinkPreviewCard", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    LinkPreviewCard: ({ url }: { url: string }) => <Text>{url}</Text>,
  };
});

const CARD =
  "```clarify\n" +
  '{"questions":[{"id":"priority","label":"Main priority","question":"What matters most to you?",' +
  '"options":["💰 Making money","🌿 Quality of life","🛡️ Safety"],"values":["Making money",' +
  '"Quality of life","Safety"]},{"id":"region","label":"Geographic preference",' +
  '"question":"Which region are you considering?","options":["🌍 Anywhere","🇪🇺 Europe"],' +
  '"values":["Anywhere","Europe"]}],"request":"Recommend the best country for me.",' +
  '"closing":"Compare the strongest options with practical pros and cons.",' +
  '"submit":"Find my best country"}\n```';

/** A reply that starts an answer, asks what "best" means, then the card (docs/clarify.md). */
const REPLY =
  "🇨🇭 **Switzerland — best for quality of life**\n\n**But let me ask you one thing.**\n\n" +
  `What do you mean by *best*?\n\n${CARD}`;

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

describe("a reply that asks with a clarify card", () => {
  it("never shows the card's JSON while it streams", async () => {
    for (let end = 1; end <= REPLY.length; end += 7) {
      const view = await render(<MarkdownContent content={REPLY.slice(0, end)} streaming />);
      const shown = visibleText(view);
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining('"questions"') });
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining('"label"') });
      await view.unmount();
    }
  });

  it("draws the card under the question once the reply is complete, and sends the picks", async () => {
    const send = jest.fn(async (_text: string) => true);
    const view = await render(
      <ClarifyActionsProvider send={send} busy={false}>
        <ClarifyMessageScope latest nextUserText={null}>
          <MarkdownContent content={REPLY} />
        </ClarifyMessageScope>
      </ClarifyActionsProvider>,
    );
    const shown = visibleText(view);
    expect(shown).toContain("But let me ask you one thing.");
    expect(shown).toContain("What matters most to you?");
    expect(shown).not.toContain('"questions"');
    await fireEvent.press(view.getByText("🛡️ Safety"));
    await fireEvent.press(view.getByText("Find my best country"));
    expect(send).toHaveBeenCalledWith(
      "Recommend the best country for me. Main priority: Safety. Geographic preference: Anywhere. " +
        "Compare the strongest options with practical pros and cons.",
    );
  });

  it("copies the questions and their choices, not the JSON", () => {
    const copied = markdownToCopyText(REPLY);
    expect(copied).toContain("What matters most to you? (Making money / Quality of life / Safety)");
    expect(copied).not.toContain('"questions"');
  });
});
