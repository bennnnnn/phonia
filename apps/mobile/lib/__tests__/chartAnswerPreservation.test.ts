import { preprocessMarkdown } from "@/lib/markdown/preprocess";

describe("chart answer preservation", () => {
  it.each(["42", "$42$", "**42**", "```answer\n42\n```", "```\n42\n```"])(
    "keeps a potentially requested result after a chart: %s", (answer) => {
      const chart = '```chart\n{"data":{"values":[{"x":1}]},"mark":"bar"}\n```';
      const output = preprocessMarkdown(`${chart}\n\n${answer}`);
      expect(output).toContain("42");
      expect(output).toContain("```chart");
    },
  );
});
