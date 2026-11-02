import { mermaidTitleKey } from "@/lib/mermaidKind";

describe("mermaidTitleKey", () => {
  it.each([
    ["graph TD; A-->B", "rich.mermaid_kind_flowchart"],
    ["flowchart LR\n  A --> B", "rich.mermaid_kind_flowchart"],
    ["sequenceDiagram\n  App->>API: login", "rich.mermaid_kind_sequence"],
    ["erDiagram\n  BOOKS ||--o{ LOANS : has", "rich.mermaid_kind_er"],
    ["classDiagram\n  class Book", "rich.mermaid_kind_class"],
    ["stateDiagram-v2\n  [*] --> Red", "rich.mermaid_kind_state"],
    ["gantt\n  title Plan", "rich.mermaid_kind_gantt"],
    ["pie title Pets\n  \"Dogs\" : 3", "rich.mermaid_kind_pie"],
    ["mindmap\n  root((Energy))", "rich.mermaid_kind_mindmap"],
    ["timeline\n  title Apollo", "rich.mermaid_kind_timeline"],
    // A kind without a name of its own, or no declaration, is a diagram.
    ["quadrantChart\n  title Reach", "rich.diagram"],
    ["", "rich.diagram"],
  ])("titles %j", (source, key) => {
    expect(mermaidTitleKey(source)).toBe(key);
  });

  it("reads past front matter, comments and directives", () => {
    const source = [
      "---",
      "title: Login",
      "---",
      "%%{init: {'theme': 'dark'}}%%",
      "%% the OAuth dance",
      "sequenceDiagram",
      "  App->>Google: sign in",
    ].join("\n");
    expect(mermaidTitleKey(source)).toBe("rich.mermaid_kind_sequence");
  });
});
