import { sanitizeMermaidNodeLabels } from "@/lib/mermaidSanitize";

const GRIND = "D --> E[Grind Beans (Medium Grind)]";
const GRIND_QUOTED = 'D --> E["Grind Beans (Medium Grind)"]';

describe("sanitizeMermaidNodeLabels", () => {
  it("quotes a parenthetical rectangle label", () => {
    expect(sanitizeMermaidNodeLabels(GRIND)).toBe(GRIND_QUOTED);
  });

  it("leaves already-quoted labels unchanged", () => {
    expect(sanitizeMermaidNodeLabels(GRIND_QUOTED)).toBe(GRIND_QUOTED);
  });

  it("leaves stadium start([Start]) unchanged", () => {
    const line = "start([Start]) --> step[Do the work]";
    expect(sanitizeMermaidNodeLabels(line)).toBe(line);
  });

  // Same cases as the server twin (test_mermaid_sanitize.py).
  it.each([
    // A cylinder stays a cylinder, not a box reading "(Database)".
    ["API --> DB[(Database)]", "API --> DB[(Database)]"],
    ["Cache[(Cache<br>Redis/Memcached)]", "Cache[(Cache<br>Redis/Memcached)]"],
    ["DB[(Primary (rw))]", 'DB[("Primary (rw)")]'],
    // Brackets that open and close the label are not a cylinder.
    ["A[(a) and (b)]", 'A["(a) and (b)"]'],
    ["S[[Validate (strict)]]", 'S[["Validate (strict)"]]'],
    ["S[[Validate]] --> T", "S[[Validate]] --> T"],
    ["I[/Read input (CSV)/]", 'I[/"Read input (CSV)"/]'],
    ["T[\\Manual step (optional)/]", 'T[\\"Manual step (optional)"/]'],
    ["start([Begin (now)])", 'start(["Begin (now)"])'],
  ])("keeps the shape of %s", (line, want) => {
    expect(sanitizeMermaidNodeLabels(line)).toBe(want);
  });
});
