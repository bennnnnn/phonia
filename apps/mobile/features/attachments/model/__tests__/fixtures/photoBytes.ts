/**
 * Photo bytes for the attachment tests.
 *
 * GEOTAGGED_JPEG is a real 16x8 JPEG (Pillow 13) whose EXIF says what a phone
 * camera writes: Make, Model, Orientation 6 and a GPS IFD (40°44'54.36"N
 * 73°59'8.36"W). The GIF parts build small, valid GIFs block by block.
 */

export const GEOTAGGED_JPEG = Uint8Array.from(atob(
  "/9j/4AAQSkZJRgABAQAAAQABAAD/4QC8RXhpZgAATU0AKgAAAAgABAEPAAIAAAAHAAAAPgEQAAIAAAAIAAAARgESAAMAAAABAAYAAIglAAQAAAABAAAATgAAAABSZWNhbGwAAEZpeHR1cmUAAAQAAQACAAAAAk4AAAAAAgAFAAAAAwAAAIQAAwACAAAAAlcAAAAABAAFAAAAAwAAAJwAAAAAAAAAKAAAAAEAAAAsAAAAAQAABU8AAAAZAAAASQAAAAEAAAA7AAAAAQAAANEAAAAZ/9sAQwAGBAUGBQQGBgUGBwcGCAoQCgoJCQoUDg8MEBcUGBgXFBYWGh0lHxobIxwWFiAsICMmJykqKRkfLTAtKDAlKCko/9sAQwEHBwcKCAoTCgoTKBoWGigoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgo/8AAEQgACAAQAwEiAAIRAQMRAf/EAB8AAAEFAQEBAQEBAAAAAAAAAAABAgMEBQYHCAkKC//EALUQAAIBAwMCBAMFBQQEAAABfQECAwAEEQUSITFBBhNRYQcicRQygZGhCCNCscEVUtHwJDNicoIJChYXGBkaJSYnKCkqNDU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6g4SFhoeIiYqSk5SVlpeYmZqio6Slpqeoqaqys7S1tre4ubrCw8TFxsfIycrS09TV1tfY2drh4uPk5ebn6Onq8fLz9PX29/j5+v/EAB8BAAMBAQEBAQEBAQEAAAAAAAABAgMEBQYHCAkKC//EALURAAIBAgQEAwQHBQQEAAECdwABAgMRBAUhMQYSQVEHYXETIjKBCBRCkaGxwQkjM1LwFWJy0QoWJDThJfEXGBkaJicoKSo1Njc4OTpDREVGR0hJSlNUVVZXWFlaY2RlZmdoaWpzdHV2d3h5eoKDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uLj5OXm5+jp6vLz9PX29/j5+v/aAAwDAQACEQMRAD8A4qiiivAP1s//2Q==",
), (char) => char.charCodeAt(0));

const EXIF_HEADER = [0x45, 0x78, 0x69, 0x66, 0x00, 0x00];
const GPS_IFD_TAG = 0x8825;

/** Whether a JPEG's EXIF names a GPS IFD (tag 0x8825 in IFD0), the block that holds its position. */
export function jpegHasGps(bytes: Uint8Array): boolean {
  let index = 2;
  while (index + 4 <= bytes.length && bytes[index] === 0xff) {
    const marker = bytes[index + 1]!;
    if (marker === 0xda || marker === 0xd9) return false;
    const length = (bytes[index + 2]! << 8) | bytes[index + 3]!;
    const body = index + 4;
    if (marker === 0xe1 && EXIF_HEADER.every((byte, i) => bytes[body + i] === byte)) {
      const tiff = body + EXIF_HEADER.length;
      const little = bytes[tiff] === 0x49;
      const u16 = (at: number) => (little ? bytes[at]! | (bytes[at + 1]! << 8) : (bytes[at]! << 8) | bytes[at + 1]!);
      const u32 = (at: number) => (little ? u16(at) + u16(at + 2) * 0x10000 : u16(at) * 0x10000 + u16(at + 2));
      const ifd0 = tiff + u32(tiff + 4);
      for (let entry = 0; entry < u16(ifd0); entry += 1) {
        if (u16(ifd0 + 2 + entry * 12) === GPS_IFD_TAG) return true;
      }
    }
    index += 2 + length;
  }
  return false;
}

const ascii = (text: string): number[] => [...text].map((char) => char.charCodeAt(0));

function subBlocks(data: number[]): number[] {
  const out: number[] = [];
  for (let start = 0; start < data.length; start += 255) {
    const chunk = data.slice(start, start + 255);
    out.push(chunk.length, ...chunk);
  }
  return [...out, 0x00];
}

/** XMP's magic trailer: whatever byte a decoder reads as a length, it lands on the final terminator. */
const XMP_MAGIC_TRAILER = [0x01, ...Array.from({ length: 256 }, (_, i) => 0xff - i), 0x00];

export const gifParts = {
  /** "GIF89a", the logical screen and a two-colour global table. */
  header: (width: number, height: number): number[] => [
    ...ascii("GIF89a"), width & 0xff, width >> 8, height & 0xff, height >> 8, 0x80, 0x00, 0x00,
    0x00, 0x00, 0x00, 0xff, 0xff, 0xff,
  ],
  /** Loop forever (NETSCAPE2.0). */
  loop: [0x21, 0xff, 0x0b, ...ascii("NETSCAPE2.0"), 0x03, 0x01, 0x00, 0x00, 0x00],
  /** A graphic control (delay, in hundredths) and one 1x1 frame. */
  frame: (delay: number): number[] => [
    0x21, 0xf9, 0x04, 0x04, delay & 0xff, delay >> 8, 0x00, 0x00,
    0x2c, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44, 0x01, 0x00,
  ],
  /** An XMP packet as Adobe embeds it: raw after the identifier, then the magic trailer. */
  xmp: (packet: string): number[] => [0x21, 0xff, 0x0b, ...ascii("XMP DataXMP"), ...ascii(packet), ...XMP_MAGIC_TRAILER],
  comment: (text: string): number[] => [0x21, 0xfe, ...subBlocks(ascii(text))],
  trailer: [0x3b],
};

export const GPS_XMP = '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description exif:GPSLatitude="40,44.906N" exif:GPSLongitude="73,59.139W"/></rdf:RDF></x:xmpmeta>';

export function gifBytes(...parts: number[][]): Uint8Array {
  return new Uint8Array(parts.flat());
}

export function containsText(bytes: Uint8Array, text: string): boolean {
  return String.fromCharCode(...bytes).includes(text);
}
