import { astText, astTextWithBreaks, type AstNode } from "@/components/markdown/markdownAstHelpers";

describe("astTextWithBreaks", () => {
  it("inserts newlines for softbreaks so quote attribution can match", () => {
    const node: AstNode = {
      key: "bq",
      type: "blockquote",
      children: [
        {
          key: "p",
          type: "paragraph",
          children: [
            { key: "t1", type: "text", content: "To be or not to be." },
            { key: "br", type: "softbreak" },
            { key: "t2", type: "text", content: "— Shakespeare" },
          ],
        },
      ],
    };
    expect(astText(node)).toBe("To be or not to be.— Shakespeare");
    expect(astTextWithBreaks(node)).toBe("To be or not to be.\n— Shakespeare");
  });
});
