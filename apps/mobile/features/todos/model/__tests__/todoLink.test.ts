import { hasTodoLink, stripTodoLinkFences } from "@/features/todos/model/todoLink";
import { deriveAssistantMessageContent } from "@/lib/markdown/assistantMessageContent";
import { markdownToCopyText, markdownToSpeechText } from "@/lib/markdown/plain";

const REPLY = "Puedes añadirlo en **Tareas**.\n\n```todo_link\n```";

describe("todo_link", () => {
  it("is a button under the reply, not part of its text", () => {
    const derived = deriveAssistantMessageContent({
      content: REPLY,
      layoutFrozen: false,
      isUser: false,
      priorUserText: null,
      messageId: "m1",
      isGenerating: false,
    });
    expect(derived.showTodoLink).toBe(true);
    expect(derived.markdownContent).toBe("Puedes añadirlo en **Tareas**.");
  });

  it("never shows its fence while it streams", () => {
    expect(stripTodoLinkFences("Puedes añadirlo en Tareas.\n\n```todo_l")).toBe(
      "Puedes añadirlo en Tareas.\n\n```todo_l",
    );
    expect(stripTodoLinkFences("Puedes añadirlo en Tareas.\n\n```todo_link\n")).toBe(
      "Puedes añadirlo en Tareas.",
    );
    expect(hasTodoLink("Puedes añadirlo en Tareas.\n\n```todo_link\n")).toBe(false);
  });

  it.each([
    ["no fence", "Hoy tienes: llamar a mamá."],
    ["a user row", REPLY],
  ])("shows no button for %s", (name, content) => {
    const derived = deriveAssistantMessageContent({
      content,
      layoutFrozen: false,
      isUser: name === "a user row",
      priorUserText: null,
      messageId: "m1",
      isGenerating: false,
    });
    expect(derived.showTodoLink).toBe(false);
  });

  it("is left out of Copy and Read aloud", () => {
    expect(markdownToCopyText(REPLY)).not.toContain("todo_link");
    expect(markdownToSpeechText(REPLY)).not.toContain("todo_link");
  });
});
