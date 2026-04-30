import { describe, expect, it } from "vitest";
import { base64FromInt16, int16FromBase64 } from "./audio-codec";

describe("audio-codec", () => {
  it("round-trips a simple sine-ish sample", () => {
    const original = new Int16Array([0, 1000, -1000, 32767, -32768, 16384, -16384]);
    const b64 = base64FromInt16(original);
    const decoded = int16FromBase64(b64);
    expect(decoded.length).toBe(original.length);
    for (let i = 0; i < original.length; i++) {
      expect(decoded[i]).toBe(original[i]);
    }
  });

  it("handles empty input", () => {
    const empty = new Int16Array(0);
    const b64 = base64FromInt16(empty);
    expect(b64).toBe("");
    const decoded = int16FromBase64(b64);
    expect(decoded.length).toBe(0);
  });

  it("round-trips a 100ms 16kHz PCM chunk (1600 samples)", () => {
    const n = 1600;
    const arr = new Int16Array(n);
    for (let i = 0; i < n; i++) arr[i] = ((i * 37) % 65536) - 32768;
    const b64 = base64FromInt16(arr);
    const decoded = int16FromBase64(b64);
    expect(decoded.length).toBe(n);
    for (let i = 0; i < n; i++) expect(decoded[i]).toBe(arr[i]);
  });

  it("handles large buffer crossing the 0x8000 chunk boundary", () => {
    // base64FromInt16 chunks at 0x8000 bytes; use a buffer > 64 KB (32768 i16 samples)
    const n = 50_000;
    const arr = new Int16Array(n);
    for (let i = 0; i < n; i++) arr[i] = (i * 13) & 0xffff;
    const b64 = base64FromInt16(arr);
    const decoded = int16FromBase64(b64);
    expect(decoded.length).toBe(n);
    expect(decoded[0]).toBe(arr[0]);
    expect(decoded[n - 1]).toBe(arr[n - 1]);
    // Spot check middle
    expect(decoded[25000]).toBe(arr[25000]);
  });

  it("tolerates odd-byte-length base64 (gracefully truncates)", () => {
    // Craft a base64 whose decoded length is odd (3 bytes) — function should
    // truncate to 1 sample (2 bytes) rather than crashing.
    const b64 = btoa("\x01\x02\x03");
    const decoded = int16FromBase64(b64);
    expect(decoded.length).toBe(1);
    // Little-endian: bytes 0x01 0x02 -> 0x0201 = 513
    expect(decoded[0]).toBe(0x0201);
  });

  it("base64 output is valid base64 (decodable by atob)", () => {
    const arr = new Int16Array([42, -42, 1234, -1234]);
    const b64 = base64FromInt16(arr);
    expect(() => atob(b64)).not.toThrow();
    // Length must be multiple of 4 (base64 padding rule)
    expect(b64.length % 4).toBe(0);
  });
});
