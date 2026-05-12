/**
 * Build the final WebSocket URL by appending style_id and lang to the base URL.
 * Kept as a pure function so it can be unit-tested without React.
 */
export function buildWsUrl(
  baseUrl: string,
  styleId: string | null,
  lang: "zh" | "en"
): string {
  const sep = baseUrl.includes("?") ? "&" : "?";
  const params = new URLSearchParams();
  if (styleId) params.set("style_id", styleId);
  params.set("lang", lang);
  return `${baseUrl}${sep}${params.toString()}`;
}
