/**
 * ```todo_link: a reply asked to add or change a to-do in a language other than
 * English. Chat only reads to-dos in those languages; the change is made in the
 * To-do screen, which the reply offers as a button (the server writes the fence:
 * apps/api/app/modules/todos/chat_language.py). The fence has no body.
 */
import { collectClosedFenceBodies, stripLangFence } from "@/lib/mdFenceScan";

const LANG = "todo_link";

/** The reply ends on an Open To-do button. */
export function hasTodoLink(content: string): boolean {
  return content.includes("```todo_link") && collectClosedFenceBodies(content, LANG).length > 0;
}

/** The reply's text without the fence, settled or still streaming. */
export function stripTodoLinkFences(content: string): string {
  if (!content.includes("```todo_link")) return content;
  return stripLangFence(content, LANG)
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
