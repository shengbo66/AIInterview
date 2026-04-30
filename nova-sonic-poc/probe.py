"""Probe WS endpoint: connect, receive up to N events, or timeout."""
import asyncio
import json
import sys
import websockets


async def probe(timeout_sec: float = 15.0, max_events: int = 10):
    url = "ws://127.0.0.1:8080/ws"
    print(f"Connecting to {url}...")
    async with websockets.connect(url) as ws:
        print("✓ WS connected")
        start = asyncio.get_event_loop().time()
        events_received = 0
        while events_received < max_events:
            remaining = timeout_sec - (asyncio.get_event_loop().time() - start)
            if remaining <= 0:
                print(f"[TIMEOUT after {timeout_sec}s, got {events_received} events]")
                break
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                data = json.loads(raw)
                events_received += 1
                t = data.get("type", "?")
                preview = json.dumps(data)[:200]
                print(f"[EVENT {events_received}] type={t}  {preview}")
            except asyncio.TimeoutError:
                print(f"[no message for {remaining:.1f}s, stopping]")
                break
        print(f"\nTotal events: {events_received}")
        return events_received


if __name__ == "__main__":
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    result = asyncio.run(probe(timeout))
    sys.exit(0 if result > 0 else 1)
