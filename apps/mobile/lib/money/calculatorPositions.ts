/** Where the user left a calculator's sliders, so they stay put when the list recycles the card. */

type Positions = Readonly<Record<string, number>>;

const positions = new Map<string, Positions>();
/** Cards kept; the least recently moved goes first. */
const MAX_CARDS = 100;

export function calculatorPositions(content: string): Positions | undefined {
  return positions.get(content);
}

export function saveCalculatorPositions(content: string, values: Positions): void {
  positions.delete(content);
  positions.set(content, values);
  while (positions.size > MAX_CARDS) positions.delete(positions.keys().next().value as string);
}

/** Sign-out: the next account sees every card at the values it asked about. */
export function clearCalculatorPositions(): void {
  positions.clear();
}
