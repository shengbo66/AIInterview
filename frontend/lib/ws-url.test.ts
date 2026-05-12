import { describe, expect, it } from "vitest";
import { buildWsUrl } from "./ws-url";

describe("buildWsUrl", () => {
  it("appends style_id and lang when no existing query string", () => {
    const url = buildWsUrl("ws://localhost:8000/ws/interview-demo", "abc-123", "zh");
    expect(url).toBe("ws://localhost:8000/ws/interview-demo?style_id=abc-123&lang=zh");
  });

  it("uses & separator when base URL already has query string", () => {
    const url = buildWsUrl("ws://localhost:8000/ws/interview-demo?token=xyz", "abc-123", "zh");
    expect(url).toBe("ws://localhost:8000/ws/interview-demo?token=xyz&style_id=abc-123&lang=zh");
  });

  it("omits style_id when null", () => {
    const url = buildWsUrl("ws://localhost:8000/ws/interview-demo", null, "zh");
    expect(url).toBe("ws://localhost:8000/ws/interview-demo?lang=zh");
    expect(url).not.toContain("style_id");
  });

  it("passes lang=en correctly", () => {
    const url = buildWsUrl("ws://localhost:8000/ws/interview-demo", "tcl-id", "en");
    expect(url).toContain("lang=en");
    expect(url).toContain("style_id=tcl-id");
  });

  it("null style_id with existing token in base URL", () => {
    const url = buildWsUrl("wss://example.com/ws?token=tok", null, "en");
    expect(url).toBe("wss://example.com/ws?token=tok&lang=en");
    expect(url).not.toContain("style_id");
  });
});
