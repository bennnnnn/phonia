import { retagMoleculeMathToSmiles } from "@/lib/chemistry/fence";
import {
  collapseAdjacentMoleculeFences,
  dropRedundantMolecule3dFences,
} from "@/lib/chemistry/moleculePair";
import { attachAnswerHeadingToFence } from "@/lib/markdown/attachAnswerHeading";
import { codeNotation } from "@/lib/markdown/notationSpans";
import { breakListItemTitles } from "@/lib/markdown/listItemTitles";
import {
  convertCalloutBlocks,
  normalizeQuoteAttributionDashes,
  promoteCalloutBlockquotes,
  promoteQuotedAttributions,
  splitBlockquoteInlineAttribution,
} from "@/lib/markdown/preprocessCallouts";
import {
  convertBlockMath,
  repairCorruptedPriceTierMarkdown,
  unwrapCorruptedMathFences,
} from "@/lib/markdown/preprocessMathBlocks";
import { layoutCheckVerificationLines } from "@/lib/markdown/preprocessMathChecks";
import {
  breakAttachedMathFences,
  closeInterruptedMathFences,
  dedentMisindentedMarkdownSteps,
  inlineShortMathFences,
  liftMathFencesOutOfLists,
  unwrapProseMathBackticks,
} from "@/lib/markdown/preprocessMathFences";
import {
  normalizeBoldInlineMath,
  protectMathEscapes,
  separateConsecutiveMathLines,
  unwrapDollarsAroundCode,
} from "@/lib/markdown/preprocessMathInline";
import {
  breakMidlineAtxHeadings,
  convertDetailsBlocks,
  mergeStrandedColons,
  retagVegaFences,
  separateStandaloneBoldLines,
  stripBoldListLabelContinuationColons,
  trimBoldDelimiterWhitespace,
  wrapBareVegaJson,
} from "@/lib/markdown/preprocessNormalize";
import {
  normalizeMarkdownTables,
  unwrapNonCodeFences,
} from "@/lib/markdown/preprocessTables";
import { retagMathAndDiagramFences } from "@/lib/math/fenceRetag";
import { normalizeImplicitMath } from "@/lib/math/normalizeImplicit";
import { applyOutsideFences } from "@/lib/mdFenceScan";
import { layoutCalculations } from "@/lib/markdown/calculationLayout";
import { presentAssistantMarkdown } from "@/lib/markdown/presentation";
import { repairBrokenMarkdownLinks } from "@/lib/places/placesList";

export { markdownHasNestedMathView, splitInlineMath } from "@/lib/markdown/inlineMath";
export { breakAttachedMathFences, unwrapProseMathBackticks } from "@/lib/markdown/preprocessMathFences";
export { layoutCheckVerificationLines } from "@/lib/markdown/preprocessMathChecks";
export { normalizeBoldInlineMath } from "@/lib/markdown/preprocessMathInline";
export {
  breakMidlineAtxHeadings,
  mergeStrandedColons,
  separateStandaloneBoldLines,
  stripBoldListLabelContinuationColons,
  trimBoldDelimiterWhitespace,
} from "@/lib/markdown/preprocessNormalize";
export { normalizeMarkdownTables } from "@/lib/markdown/preprocessTables";

export type PreprocessOptions = {
  /** The server presented this text before saving it (isServerPresentedRow):
   * its prose is shown as saved, not presented again. */
  presented?: boolean;
};

export function preprocessMarkdown(
  content: string,
  mathFormat?: (expr: string) => string,
  options: PreprocessOptions = {},
): string {
  // SMILES ("CC(=O)O") becomes code first: the maths passes read "(=O)" as maths.
  let out = codeNotation(repairBrokenMarkdownLinks(content));
  out = trimBoldDelimiterWhitespace(out);
  // Do this before math normalization can reinterpret a punctuation-only
  // continuation line.
  out = stripBoldListLabelContinuationColons(out);
  out = repairCorruptedPriceTierMarkdown(out);
  out = normalizeImplicitMath(out, mathFormat);
  out = normalizeBoldInlineMath(out);
  // The model often wraps inline math in backticks (`` `$x^2 = 4$` ``), which
  // markdown renders as inline CODE → raw literal `$...$`. Un-wrap backtick-
  // wrapped `$...$` so it renders as math inline with the prose (in sync with
  // the text, no late fence pop-in).
  out = applyOutsideFences(out, (prose) =>
    prose.replace(/`(\$[^`\n]+?\$)`/g, "$1"),
  );
  // And the reverse: code the model wrapped in dollars stays code.
  out = unwrapDollarsAroundCode(out);

  out = promoteCalloutBlockquotes(out);
  out = promoteQuotedAttributions(out);
  out = normalizeQuoteAttributionDashes(out);
  out = splitBlockquoteInlineAttribution(out);
  out = convertCalloutBlocks(out);

  out = convertDetailsBlocks(out);

  out = convertBlockMath(out);
  out = breakAttachedMathFences(out);
  out = closeInterruptedMathFences(out);
  out = dedentMisindentedMarkdownSteps(out);
  out = unwrapCorruptedMathFences(out);

  out = normalizeMarkdownTables(out);

  // Re-tag Vega fences / bare JSON with linear scans (no nested [\s\S]*? ReDoS).
  out = retagVegaFences(out);
  out = wrapBareVegaJson(out);

  // Molecule formulas before math retag — otherwise bare `O=O` becomes ```math.
  out = retagMoleculeMathToSmiles(out);
  out = retagMathAndDiagramFences(out);

  out = unwrapNonCodeFences(out);

  out = protectMathEscapes(out);
  out = mergeStrandedColons(out);
  out = breakMidlineAtxHeadings(out);
  out = breakAttachedMathFences(out);
  out = closeInterruptedMathFences(out);
  out = dedentMisindentedMarkdownSteps(out);
  out = liftMathFencesOutOfLists(out);
  out = inlineShortMathFences(out);
  out = unwrapProseMathBackticks(out);
  out = separateConsecutiveMathLines(out);
  out = collapseAdjacentMoleculeFences(out);
  out = dropRedundantMolecule3dFences(out);
  // After fence inlining: a trailing ✓ used to abort the = split, and
  // inlineShortMathFences can glue `$...$` back onto `For x = 3:`.
  out = layoutCheckVerificationLines(out);
  out = separateStandaloneBoldLines(out);
  // Some math normalizers rebuild the surrounding prose while preserving the
  // model's original delimiter padding. Make this the final prose cleanup so
  // malformed bold closers can never reach markdown-it as literal `**`.
  out = trimBoldDelimiterWhitespace(out);
  // Presented text skips the prose repairs the server already made. The passes
  // above still build maths of their own from it (display maths and retagged
  // fences become ```math), so the calculation rows are laid out either way.
  return attachAnswerHeadingToFence(
    breakListItemTitles(
      options.presented
        ? layoutCalculations(out)
        : presentAssistantMarkdown(out),
    ),
  );
}
