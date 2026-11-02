import { TEXT_ASCENT, TEXT_DESCENT, type CircuitLayout, type TextMark } from "@/lib/physics/circuit";

/** Every label's box, for overlap checks: [left, top, right, bottom] in layout units. */
export function circuitLabelBoxes(layout: CircuitLayout): [number, number, number, number][] {
  const marks: TextMark[] = [
    ...layout.parts.flatMap((part) => [part.label, part.detail]),
    ...layout.groups.map((group) => group.text),
    layout.source.label,
    layout.current?.label,
  ].filter((mark): mark is TextMark => Boolean(mark));
  return marks.map((mark) => [mark.x, mark.y - TEXT_ASCENT, mark.x + mark.width, mark.y + TEXT_DESCENT]);
}
