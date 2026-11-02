import { classifyFence, classifyOpenFencePreview } from "@/lib/fenceDispatch";

describe("classifyFence — explicit tags win", () => {
  it.each([
    ["python", "x = 2", "code"],
    ["javascript", "const x = 2", "code"],
    ["rust", "let x = 2;", "code"],
    // Every ```answer fence is the one card (AnswerBlock draws the check only for
    // the server's mark); a bare number in a soft fence is plain math.
    ["answer", "verified: true\nx = 2", "answer"],
    ["answer", "label: answer\nverified: true\nx = 2", "answer"],
    ["answer", "verified: true\nnotation: chemistry\npH = 2.00", "answer"],
    ["answer", "x = 2", "answer"],
    ["result", "x = 2", "answer"],
    ["answer", "notation: chemistry\npH = 2.87", "answer"],
    ["answer", "Verified: TRUE\nx = 7", "answer"],
    ["math", "x^2 + 1", "math"],
    ["latex", String.raw`\frac{x^2}{2}`, "math"],
    ["geometry", '{"type":"square"}', "rich"],
    ["smiles", "CCO", "rich"],
    ["copy", "120", "math"],
    ["", "120", "math"],
    ["", "x = 2 or x = -2", "math"],
    ["text", String.raw`\boxed{29.9}`, "math"],
    ["plain", "x = 2 or x = -3", "math"],
    ["image", '{"prompt":"a cat"}', "hide"],
    ["photo", "Ethiopia location map", "hide"],
  ] as const)("%s %j → %s", (lang, body, kind) => {
    expect(classifyFence(lang, body).kind).toBe(kind);
  });

  it("hides a reply's photo request while it streams", () => {
    expect(classifyOpenFencePreview("photo", "Ethiopia loc")).toBe("hide");
  });

  it("does not run the math-answer heuristic on tagged source code", () => {
    expect(classifyOpenFencePreview("python", "x = 2")).toBe("code");
    expect(classifyOpenFencePreview("javascript", "x = 2")).toBe("code");
    expect(classifyOpenFencePreview("math", String.raw`\frac{x^2}{2}`)).toBe("math");
    // An answer-shaped soft fence streams as math; an ```answer streams as the
    // card, whose check waits for the settled reply.
    expect(classifyOpenFencePreview("", "x = 2")).toBe("math");
    expect(classifyOpenFencePreview("answer", "x = 7")).toBe("answer");
  });

  it("demotes leaked drafting instructions to normal prose", () => {
    const leaked =
      "fence!\n(Or paste their number if SMS and you want it formatted for texting.)";
    expect(classifyFence("message", leaked).kind).toBe("prose");
    expect(classifyFence("copy", leaked).kind).toBe("prose");
  });

  it.each([
    ["message", "¡Feliz cumpleaños! Espero que tengas un día maravilloso."],
    ["email", "Asunto: Vacaciones\n\nHola Ana,\n\nEstaré fuera el viernes."],
    ["social", "新しい仕事を始めることになりました。応援してくださった皆さん、ありがとうございます。"],
  ])("keeps a genuine multilingual %s draft rich", (lang, body) => {
    expect(classifyFence(lang, body).kind).toBe("rich");
  });

  it("trusts an explicit social tag even when the post contains a comparison", () => {
    const post =
      "Python is a strong choice for prototyping, while JavaScript shines on the frontend. Both belong in a modern toolkit.";
    expect(classifyFence("linkedin", post).kind).toBe("rich");
    expect(classifyFence("facebook", post).kind).toBe("rich");
    expect(classifyFence("instagram", post).kind).toBe("rich");
  });

  it("demotes an email fence that swallowed a capabilities list", () => {
    const leaked = [
      "to reschedule a meeting or ```sms to confirm plans)",
      "## phases with numbered tasks",
      "",
      "**Planning & Productivity**",
      "- Design an app",
    ].join("\n");
    expect(classifyFence("email", leaked).kind).toBe("prose");
    expect(classifyFence("sms", leaked).kind).toBe("prose");
  });

  it("does not render an indented solve-step as a code card", () => {
    const body = ["2. **Simplify:**", "", "```math", "x = 1", "```"].join("\n");
    expect(classifyFence("", body).kind).toBe("prose");
  });

  it.each(["email", "message", "sms", "reply", "linkedin", "social", "facebook", "instagram", "copy"])(
    "streams an open %s fence as prose, never as code",
    (lang) => {
      expect(classifyOpenFencePreview(lang, "Draft still streaming")).toBe("prose");
    },
  );
});
