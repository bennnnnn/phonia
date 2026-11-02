/**
 * The title a Mermaid card shows: the kind of diagram its source declares
 * ("Sequence diagram", "Flowchart"), or plain "Diagram" for a kind without
 * its own name. The tool's name is not something a reader needs.
 */

/** The declaration keyword (its first word) → the title's i18n key. */
const KIND_KEYS: Record<string, string> = {
  graph: "rich.mermaid_kind_flowchart",
  flowchart: "rich.mermaid_kind_flowchart",
  "flowchart-elk": "rich.mermaid_kind_flowchart",
  sequencediagram: "rich.mermaid_kind_sequence",
  erdiagram: "rich.mermaid_kind_er",
  classdiagram: "rich.mermaid_kind_class",
  "classdiagram-v2": "rich.mermaid_kind_class",
  statediagram: "rich.mermaid_kind_state",
  "statediagram-v2": "rich.mermaid_kind_state",
  gantt: "rich.mermaid_kind_gantt",
  pie: "rich.mermaid_kind_pie",
  mindmap: "rich.mermaid_kind_mindmap",
  timeline: "rich.mermaid_kind_timeline",
};

/** The first line that declares something: front matter, `%%` comments and directives skipped. */
function declarationLine(source: string): string {
  let inFrontMatter = false;
  for (const raw of source.split("\n")) {
    const line = raw.trim();
    if (line === "---") {
      inFrontMatter = !inFrontMatter;
      continue;
    }
    if (inFrontMatter || !line || line.startsWith("%%")) continue;
    return line;
  }
  return "";
}

/** The i18n key of the card title for this diagram source. */
export function mermaidTitleKey(source: string): string {
  const keyword = declarationLine(source).split(/[\s;:]/)[0]?.toLowerCase() ?? "";
  return KIND_KEYS[keyword] ?? "rich.diagram";
}
