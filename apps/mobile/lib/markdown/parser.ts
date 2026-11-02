import MarkdownIt from "markdown-it";
import taskLists from "markdown-it-task-lists";

// `tables` is a valid markdown-it option (GFM tables) but is missing from
// @types/markdown-it's Options interface, so cast the config to bypass it.
const mdOptions = {
  typographer: true,
  linkify: true,
  tables: true,
} as unknown as ConstructorParameters<typeof MarkdownIt>[0];

export const markdownItInstance = MarkdownIt(mdOptions).use(taskLists, {
  enabled: true,
  label: true,
});

// The task-list plugin leaves the space after `[ ]` at the start of the
// item's text; the checkbox already stands apart from it.
markdownItInstance.core.ruler.push("task_label_trim", (state) => {
  for (const token of state.tokens) {
    const children = token.type === "inline" ? token.children : null;
    if (!children) continue;
    const box = children.findIndex(
      (child) => child.type === "html_inline" && child.content.includes("task-list-item-checkbox"),
    );
    const label = box < 0 ? undefined : children.slice(box + 1).find((child) => child.type === "text");
    if (label) label.content = label.content.replace(/^\s+/, "");
  }
});

// Preserve literal variable labels like (c) and math shorthand like +/-.
// Smart quotes remain available independently of symbol substitutions.
markdownItInstance.core.ruler.disable("replacements");
