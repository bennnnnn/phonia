import { ReactNode } from "react";

import { LinkPreviewCard } from "@/components/LinkPreviewCard";
import { renderBlockquote } from "@/components/markdown/blockquoteRender";
import { useReplyStreaming } from "@/components/markdown/ReplyStreaming";
import {
  type AstNode,
  astText,
  detectStandaloneLink,
  inTableCell,
  inTableHeader,
  parentHasType,
} from "@/components/markdown/markdownAstHelpers";
import type {
  MdMathStyles,
  MdTableStyles,
  StyleMap,
} from "@/components/markdown/markdownContentStyles";
import { wrapInlineChildren } from "@/components/markdown/rules/inline";
import { lessonStepParts, renderLessonStep } from "@/components/markdown/rules/lesson";
import {
  renderWorkoutPart,
  renderWorkoutSection,
  workoutPartParts,
  workoutSectionParts,
} from "@/components/markdown/rules/workout";
import { mathRunLineHeight } from "@/lib/math/text";
import type { Theme } from "@/lib/theme";

/**
 * A paragraph that is one link: its preview card once the reply has settled.
 * While it streams the link may still be growing, so it is drawn as text.
 */
function StandaloneLink({ url, text }: { url: string; text: ReactNode }) {
  const streaming = useReplyStreaming();
  return streaming ? <>{text}</> : <LinkPreviewCard url={url} />;
}

export function blockRules(t: Theme, mdTable: MdTableStyles, mdMath: MdMathStyles) {
  const paragraphBody = (
    node: AstNode,
    children: ReactNode,
    parent: unknown,
    styles: StyleMap,
  ): ReactNode => {
    if (inTableCell(parent)) {
      // Table cell paragraphs need the same mathRunLineHeight treatment as
      // body paragraphs — without it, a stacked \frac / \sqrt View inside
      // the cell's Text gets clipped to the cell's default lineHeight.
      const cellRaw = astText(node);
      const cellRunHeight = mathRunLineHeight(cellRaw);
      return wrapInlineChildren(
        node,
        children,
        [
          mdTable.cellText,
          inTableHeader(parent) && mdTable.headerText,
          cellRunHeight != null && { lineHeight: cellRunHeight },
        ],
        mdMath.inlineWrap,
      );
    }
    const section = workoutSectionParts(node);
    if (section) {
      return renderWorkoutSection(node.key, section, styles, t);
    }
    const part = workoutPartParts(node);
    if (part) {
      return renderWorkoutPart(node.key, part, styles, t);
    }
    const step = lessonStepParts(node);
    if (step) {
      return renderLessonStep(node.key, step, styles, t);
    }
    // Prose-only paragraphs stay a single Text so "An **open circle**"
    // wraps as one run. Stacked frac/sqrt must leave that Text — iOS
    // sizes a View-in-Text as 0×0 and paints the numerator over the
    // previous line. Do not use `styles.paragraph` — mergeStyle copies
    // the library's flexDirection/flexWrap/width onto that key.
    const raw = astText(node);
    const runHeight = mathRunLineHeight(raw);
    // A loose list's paragraph: the item gap separates items, not a block gap.
    const inListItem = parentHasType(parent, "list_item");
    return wrapInlineChildren(
      node,
      children,
      [
        styles.body,
        styles.text,
        styles.paragraphRun,
        inListItem && styles.listParagraph,
        runHeight != null && { lineHeight: runHeight },
      ],
      [mdMath.inlineWrap, styles.paragraphRun, inListItem && styles.listParagraph],
    );
  };
  return {
    blockquote: (node: AstNode, children: ReactNode) => renderBlockquote(node, children),
    paragraph: (
      node: AstNode,
      children: ReactNode,
      parent: unknown,
      styles: StyleMap,
    ) => {
      const body = paragraphBody(node, children, parent, styles);
      const url = detectStandaloneLink(node);
      return url ? <StandaloneLink key={node.key} url={url} text={body} /> : body;
    },
  };
}
