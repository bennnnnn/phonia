import { render } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { loanFence } from "@/lib/money/__tests__/loanFence";

jest.mock("@/components/LinkPreviewCard", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    LinkPreviewCard: ({ url }: { url: string }) => <Text>{url}</Text>,
  };
});
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

/** A mortgage reply as the server finishes it: the model's prose, then the card. */
const REPLY =
  "At 1% for 30 years, a $300,000 mortgage costs **$964.92 a month**.\n\n" +
  "```calculator\n" +
  JSON.stringify(loanFence()) +
  "\n```";

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

describe("a calculator card in a reply", () => {
  it("never shows its JSON while the reply streams", async () => {
    const start = REPLY.indexOf("```calculator");
    for (let end = start; end <= REPLY.length; end += 97) {
      const view = await render(<MarkdownContent content={REPLY.slice(0, end)} streaming />);
      const shown = visibleText(view);
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining('"controls"') });
      expect({ end, shown }).toEqual({ end, shown: expect.not.stringContaining('"label_key"') });
      await view.unmount();
    }
  });

  it("draws the card under the prose once the reply is complete", async () => {
    const view = await render(<MarkdownContent content={REPLY} />);
    const shown = visibleText(view);
    // The shared react-i18next mock answers with keys.
    expect(shown).toContain("money.title.mortgage");
    expect(view.getByTestId("calculator-card")).toBeOnTheScreen();
    expect(view.getByTestId("calculator-readout-payment")).toHaveTextContent("$964.92");
    expect(shown.indexOf("a month")).toBeLessThan(shown.indexOf("money.title.mortgage"));
    expect(shown).not.toContain('"readouts"');
  });
});
