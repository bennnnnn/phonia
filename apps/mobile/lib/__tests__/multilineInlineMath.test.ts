import { preprocessMarkdown } from '@/lib/markdown/preprocess';
import { prepareStreamingMathText } from '@/lib/math/streaming';
import { preprocessMarkdownForStream, type StreamingPreprocessCache } from '@/lib/markdown/preprocessStream';
import { splitInlineMath } from '@/lib/markdown/inlineMath';
import { restoreMathEscapes } from '@/lib/math/text';
import { markdownItInstance } from '@/lib/markdown/parser';

const C04_RESPONSE = "The partial derivative of \\(x^2 y\\) with respect to \\(y\\) is:  \n**\\(x^2\\)**  \n\n### Explanation\n- When differentiating with respect to \\(y\\), treat \\(x\\) as a constant.  \n- The derivative of \\(y\\) (with respect to \\(y\\)) is 1, so:  \n  \\(\n  \\frac{\\partial}{\\partial y}(x^2 y) = x^2 \\cdot 1 = x^2.\n  \\)";

const formula = String.raw`\frac{\partial}{\partial y}(x^2 y) = x^2 \cdot 1 = x^2.`;
const formulaSteps = [
  String.raw`\frac{\partial}{\partial y}(x^2 y) = x^2 \cdot 1`,
  String.raw`\frac{\partial}{\partial y}(x^2 y) = x^2.`,
];
function parsedFormulae(text: string): string[] {
  return markdownItInstance.parse(text, {}).flatMap((token) =>
    token.type === 'inline' ? (token.children ?? []).flatMap((child) =>
      child.type === 'text' ? splitInlineMath(child.content).filter((part) => part.type === 'math').map((part) => restoreMathEscapes(part.value)) : []) : []);
}
describe('multiline explicit inline math', () => {
  it('keeps the exact saved C04 derivative in one parseable math span inside the list', () => {
    const prepared = preprocessMarkdown(C04_RESPONSE);
    for (const step of formulaSteps) expect(parsedFormulae(prepared)).toContain(step);
    expect(prepared).not.toContain('$\n');
  });
  it.each(['\n', '\r\n'])('folds source newlines, keeping TeX matrix row separators (%j)', (newline) => {
    const matrix = String.raw`\begin{matrix}1 & 2 \\ 3 & 4\end{matrix}`;
    const input = `Use \\(${newline} ${matrix}${newline} \\).`;
    expect(parsedFormulae(preprocessMarkdown(input))).toContain(matrix);
    expect(parsedFormulae(prepareStreamingMathText(input).text)).toContain(matrix);
  });
  it.each([
    'A literal \\` **separator** before $\\{1,2\\}$.',
    'An unmatched ` **separator** before $\\{1,2\\}$.',
  ])('keeps protecting math after a literal backtick: %s', (source) => {
    expect(parsedFormulae(preprocessMarkdown(source))).toContain(String.raw`\{1,2\}`);
  });
  it('handles every incremental C04 delimiter prefix without exposing a partial derivative command', () => {
    const source = `- The derivative is:\n  \\(\n  ${formula}\n  \\)`;
    let cache: StreamingPreprocessCache | null = null;
    const formulaStart = source.indexOf('\\(');
    for (let end = formulaStart + 2; end <= source.length; end += 1) {
      const partial = source.slice(0, end);
      const streamed = preprocessMarkdownForStream(partial, cache);
      cache = streamed.cache;
      const tail = prepareStreamingMathText(streamed.prepared.slice(cache.preparedStable.length));
      if (end < source.length) {
        expect(tail.pending).toBe(true);
        expect(tail.text).not.toMatch(/\\frac|\\partial|\$/);
      } else {
        expect(tail.pending).toBe(false);
        for (const step of formulaSteps) {
          expect(parsedFormulae(cache.preparedStable + tail.text)).toContain(step);
        }
      }
    }
    const completed = preprocessMarkdownForStream(`${source}\n`, cache);
    expect(completed.prepared).toBe(preprocessMarkdown(`${source}\n`));
    for (const step of formulaSteps) expect(parsedFormulae(completed.prepared)).toContain(step);
  });
  it('leaves a multiline backticked source span literal in the live preview', () => {
    const source = '`\\(\n\\frac{1}{2}\n\\)`';
    expect(prepareStreamingMathText(source)).toEqual({text: source, pending: false});
  });
  it.each([
    '```python\nvalue = r"\\(\n\\frac{1}{2}\n\\)"\n```',
    '~~~python\nvalue = r"\\(\n\\frac{1}{2}\n\\)"\n~~~',
    'Price: $5 and $10.',
    String.raw`Price: \$5 and \$10.`,
  ])('preserves code and currency: %s', (source) => {
    expect(preprocessMarkdown(source)).toBe(source);
    // Fenced regions are dispatched before the inline live-tail helper.
    if (!source.startsWith('~~~')) expect(prepareStreamingMathText(source)).toEqual({text: source, pending: false});
  });
});
