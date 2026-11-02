/**
 * A GIF's frames without the blocks that can say where, when or by whom it was made.
 *
 * A GIF has no EXIF, but an application extension can carry an XMP packet (GPS
 * included: exiftool and Photoshop write one) or a Photoshop/IPTC record, and a
 * comment extension any text. Everything the picture needs stays byte for byte:
 * the header and colour tables, every frame with its graphic control (delay,
 * transparency), plain-text extensions, the loop count and an ICC colour profile.
 * Every other extension goes, as does anything after the trailer. Pure: no files.
 */

const EXTENSION = 0x21;
const IMAGE = 0x2c;
const TRAILER = 0x3b;
const GRAPHIC_CONTROL = 0xf9;
const PLAIN_TEXT = 0x01;
const APPLICATION = 0xff;
const HEADER_BYTES = 13;
/** An application extension opens with one 11-byte sub-block: its identifier and code. */
const APPLICATION_ID_BYTES = 11;
/** The loop count (Netscape's, and its older twin) and a colour profile. */
const KEPT_APPLICATIONS: ReadonlySet<string> = new Set(["NETSCAPE2.0", "ANIMEXTS1.0", "ICCRGBG1012"]);

type StrippedGif = { width: number; height: number; bytes: Uint8Array };

function ascii(bytes: Uint8Array, start: number, end: number): string {
  return String.fromCharCode(...bytes.subarray(start, end));
}

function colorTableBytes(packed: number): number {
  return packed & 0x80 ? 3 * 2 ** ((packed & 0x07) + 1) : 0;
}

/** Index just past a run of data sub-blocks and its terminator, or -1 when it runs off the end. */
function afterSubBlocks(bytes: Uint8Array, start: number): number {
  let index = start;
  while (index < bytes.length) {
    const size = bytes[index]!;
    index += 1 + size;
    if (size === 0) return index;
  }
  return -1;
}

function keepsExtension(bytes: Uint8Array, start: number): boolean {
  const label = bytes[start + 1];
  if (label === GRAPHIC_CONTROL || label === PLAIN_TEXT) return true;
  if (label !== APPLICATION || bytes[start + 2] !== APPLICATION_ID_BYTES) return false;
  return KEPT_APPLICATIONS.has(ascii(bytes, start + 3, start + 3 + APPLICATION_ID_BYTES));
}

/** End of the block at `start` and whether it stays, or null for a byte no GIF block starts with. */
function block(bytes: Uint8Array, start: number): { end: number; keep: boolean } | null {
  if (bytes[start] === IMAGE) {
    // Descriptor (10 bytes), its colour table, the LZW minimum code size, then the data.
    const packed = bytes[start + 9] ?? 0;
    return { end: afterSubBlocks(bytes, start + 10 + colorTableBytes(packed) + 1), keep: true };
  }
  if (bytes[start] === EXTENSION) {
    return { end: afterSubBlocks(bytes, start + 2), keep: keepsExtension(bytes, start) };
  }
  return null;
}

function joined(bytes: Uint8Array, ranges: readonly (readonly [number, number])[]): Uint8Array {
  const out = new Uint8Array(ranges.reduce((total, [start, end]) => total + end - start, 0));
  let offset = 0;
  for (const [start, end] of ranges) {
    out.set(bytes.subarray(start, end), offset);
    offset += end - start;
  }
  return out;
}

/** The GIF's logical screen size and its bytes without metadata; null unless the bytes are one whole GIF. */
export function stripGifMetadata(bytes: Uint8Array): StrippedGif | null {
  if (bytes.length < HEADER_BYTES) return null;
  const signature = ascii(bytes, 0, 6);
  if (signature !== "GIF87a" && signature !== "GIF89a") return null;
  const width = bytes[6]! | (bytes[7]! << 8);
  const height = bytes[8]! | (bytes[9]! << 8);
  let index = HEADER_BYTES + colorTableBytes(bytes[10]!);
  const kept: [number, number][] = [[0, index]];
  while (index < bytes.length) {
    if (bytes[index] === TRAILER) {
      kept.push([index, index + 1]);
      return { width, height, bytes: joined(bytes, kept) };
    }
    const next = block(bytes, index);
    if (!next || next.end < 0) return null;
    if (next.keep) kept.push([index, next.end]);
    index = next.end;
  }
  // No trailer: a cut-off file, not one to send as it is.
  return null;
}
