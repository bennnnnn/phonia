/**
 * Every press target is something a screen reader can name and act on.
 *
 * A raw Pressable or Touchable is read with no role unless it states one, so VoiceOver
 * and TalkBack never say "button" or "link" and the reader cannot tell it from text.
 * One that draws only an icon also has no words to read: it is announced as nothing.
 * The UI kit asks for both (IconButton, HeaderButton and AddFab require a label); this
 * holds the raw ones the app still draws.
 *
 * Exempt: a target hidden from the reader on purpose (`accessible={false}`, or hidden
 * with its subtree), one whose props come from a spread, and the child of an
 * expo-router `<Link asChild>`, which passes `role="link"` itself.
 */
import * as ts from "typescript";

import { appFiles, isTest, readSource, relative } from "./support/sourceFiles";

const PRESS_TARGET = /^(Pressable|AnimatedPressable|Touchable(Opacity|Highlight|WithoutFeedback|NativeFeedback))$/;
/** Children whose words name the target: Text, and kit pieces given a title or label. */
const WORDS = /(Text|Label|Title)$/;

type Finding = { at: string; problem: "no role" | "icon only, no label" };

function attributes(element: ts.JsxOpeningLikeElement): { props: Map<string, string>; spread: boolean } {
  const props = new Map<string, string>();
  let spread = false;
  for (const attribute of element.attributes.properties) {
    if (ts.isJsxSpreadAttribute(attribute)) spread = true;
    else props.set(attribute.name.getText(), attribute.initializer?.getText() ?? "true");
  }
  return { props, spread };
}

function hasWords(element: ts.JsxElement): boolean {
  let found = false;
  const visit = (node: ts.Node): void => {
    if (found) return;
    if (ts.isJsxText(node) && node.getText().trim()) found = true;
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node;
      const { props } = attributes(opening);
      if (WORDS.test(opening.tagName.getText()) || props.has("title") || props.has("label")) found = true;
    }
    ts.forEachChild(node, visit);
  };
  element.children.forEach(visit);
  return found;
}

function isLinkChild(node: ts.Node): boolean {
  const parent = node.parent;
  if (!parent || !ts.isJsxElement(parent)) return false;
  const opening = parent.openingElement;
  return opening.tagName.getText() === "Link" && attributes(opening).props.has("asChild");
}

function findingsIn(file: string): Finding[] {
  const source = ts.createSourceFile(file, readSource(file), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const findings: Finding[] = [];
  const visit = (node: ts.Node): void => {
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) {
      const opening = ts.isJsxElement(node) ? node.openingElement : node;
      if (PRESS_TARGET.test(opening.tagName.getText())) {
        const { props, spread } = attributes(opening);
        const hidden =
          props.get("accessible") === "{false}" ||
          props.has("accessibilityElementsHidden") ||
          /no-hide-descendants/.test(props.get("importantForAccessibility") ?? "");
        if (!hidden && !spread && !isLinkChild(node)) {
          const line = source.getLineAndCharacterOfPosition(opening.getStart()).line + 1;
          const at = `${relative(file)}:${line}`;
          if (!props.has("accessibilityRole") && !props.has("role")) findings.push({ at, problem: "no role" });
          const named = props.has("accessibilityLabel") || props.has("aria-label");
          if (!named && !(ts.isJsxElement(node) && hasWords(node))) {
            findings.push({ at, problem: "icon only, no label" });
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return findings;
}

describe("press targets", () => {
  const files = appFiles().filter((file) => file.endsWith(".tsx") && !isTest(file));

  it("finds the press targets it guards", () => {
    const count = files
      .map((file) => readSource(file).match(/<(Pressable|AnimatedPressable|Touchable\w+)\b/g)?.length ?? 0)
      .reduce((sum, n) => sum + n, 0);
    expect(count).toBeGreaterThan(100);
  });

  it("each state a role, and one that draws only an icon has a label", () => {
    expect(files.flatMap(findingsIn)).toEqual([]);
  });
});
