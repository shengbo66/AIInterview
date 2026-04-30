/**
 * PCM <-> base64 conversion used by the interview WS protocol.
 * Pulled out of page.tsx so we can unit-test it without bringing up React.
 */

export function base64FromInt16(int16: Int16Array): string {
  // View same bytes as Uint8Array to build the binary string efficiently.
  const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength);
  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

export function int16FromBase64(b64: string): Int16Array {
  const binary = atob(b64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
  // Ensure even byte count before viewing as Int16Array
  const evenLen = bytes.byteLength - (bytes.byteLength % 2);
  return new Int16Array(bytes.buffer, 0, evenLen / 2);
}
