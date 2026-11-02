/**
 * Geometry for the Skia-free wave on the image-gen card: a strip of soft
 * accent bands, tilted down-right, that slides under a cover with dot-shaped
 * holes (`dotHolesPath`). Only the strip's translate animates.
 *
 * The strip repeats every `period` along its length and is one period longer
 * than the card's diagonal. Sliding it by exactly one period and starting
 * over shows the same picture, so the loop has no seam.
 */

/** Direction of travel, clockwise from the x-axis: down and to the right. */
const WAVE_BAND_ANGLE_DEG = 53;

type WaveBand = {
  /** Strip box in card coordinates, before the rotate and slide. */
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
  /** Distance between bands; the slide per loop. */
  readonly period: number;
  readonly angleDeg: number;
};

/**
 * Strip for a card. It is centered on the card, so rotating about its center
 * keeps it over the card. `height` is the card diagonal, so it covers the card
 * at any angle; one band crosses the card per period. Rotate it by `angleDeg`,
 * then slide it along its length by `-period / 2 + progress * period` with
 * progress looping 0 → 1: starting half a period back keeps the card covered
 * at both ends of the loop.
 */
export function waveBandLayout(cardWidth: number, cardHeight: number): WaveBand {
  const span = Math.max(1, Math.ceil(Math.hypot(cardWidth, cardHeight)));
  const period = span;
  const width = span + period;
  return {
    left: (cardWidth - width) / 2,
    top: (cardHeight - span) / 2,
    width,
    height: span,
    period,
    angleDeg: WAVE_BAND_ANGLE_DEG,
  };
}

type BandStop = { readonly offset: number; readonly opacity: number };

/**
 * Gradient stops along the strip (offset 0–1): one soft band per period,
 * peaking at `peak` opacity in the middle of each period and fading to clear
 * about a third of a period either side.
 */
export function waveBandStops(band: WaveBand, peak: number): BandStop[] {
  const count = Math.max(1, Math.round(band.width / band.period));
  const shape: [number, number][] = [
    [-0.32, 0],
    [-0.15, 0.45],
    [0, 1],
    [0.15, 0.45],
    [0.32, 0],
  ];
  const stops: BandStop[] = [];
  for (let k = 0; k < count; k += 1) {
    const center = (k + 0.5) * band.period;
    for (const [shift, level] of shape) {
      stops.push({
        offset: (center + shift * band.period) / band.width,
        opacity: level * peak,
      });
    }
  }
  return stops;
}
