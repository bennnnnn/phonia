import { encodePcm16Wav } from "@/lib/audio/wav";

function decode(base64: string): DataView {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new DataView(bytes.buffer);
}

function ascii(view: DataView, offset: number, length: number): string {
  return String.fromCharCode(...Array.from({ length }, (_, i) => view.getUint8(offset + i)));
}

describe("encodePcm16Wav", () => {
  it("writes a 16-bit mono PCM header, then the samples little-endian", () => {
    const samples = [0, 1, -1, 32767, -32768];
    const view = decode(encodePcm16Wav(Int16Array.from(samples), 22_050));

    expect(view.byteLength).toBe(44 + 10);
    expect(ascii(view, 0, 4)).toBe("RIFF");
    expect(view.getUint32(4, true)).toBe(36 + 10);
    expect(ascii(view, 8, 8)).toBe("WAVEfmt ");
    expect([view.getUint32(16, true), view.getUint16(20, true), view.getUint16(22, true)]).toEqual([16, 1, 1]);
    expect([view.getUint32(24, true), view.getUint32(28, true)]).toEqual([22_050, 44_100]);
    expect([view.getUint16(32, true), view.getUint16(34, true)]).toEqual([2, 16]);
    expect(ascii(view, 36, 4)).toBe("data");
    expect(view.getUint32(40, true)).toBe(10);
    expect(samples.map((_, i) => view.getInt16(44 + i * 2, true))).toEqual(samples);
  });
});
