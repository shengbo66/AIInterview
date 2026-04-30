"""Pre-POC: minimal Strands BidiAgent server for Nova Sonic.

Goal: verify Strands BidiAgent works locally with us-east-1 Nova Sonic.
No tools, no image, no product knowledge — just plain conversation.
"""
import os
import json
import asyncio
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel
from strands.experimental.bidi.tools import stop_conversation
from dotenv import load_dotenv

load_dotenv(override=True)

MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-2-sonic-v1:0")
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")

app = FastAPI()


@app.get("/ping")
async def ping():
    return {"status": "Healthy", "time": int(datetime.now().timestamp())}


sonic_model = BidiNovaSonicModel(
    model_id=MODEL_ID,
    provider_config={
        "audio": {"voice": "tiffany", "input_rate": 16000, "output_rate": 16000,
                  "channels": 1, "format": "pcm"},
        "inference": {}
    },
    client_config={"region": BEDROCK_REGION},
)


@app.websocket("/ws")
async def ws_handler(websocket: WebSocket):
    agent = BidiAgent(
        model=sonic_model,
        tools=[stop_conversation],
        system_prompt="You are a friendly assistant. Keep replies short (one sentence).",
    )
    await websocket.accept()
    print(f"[{datetime.now().isoformat()}] WS connected")

    async def recv():
        data = await websocket.receive_json()
        msg_type = data.get("type", "?")
        if msg_type != "bidi_audio_input":
            print(f"[RECV] type={msg_type}")
        return data

    async def send(data):
        msg_type = data.get("type", "?") if isinstance(data, dict) else "?"
        if msg_type != "bidi_audio_stream":
            print(f"[SEND] type={msg_type}  preview={json.dumps(data)[:150]}")
        await websocket.send_json(data)

    try:
        await agent.run(inputs=[recv], outputs=[send], invocation_state={"websocket": websocket})
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error: {e}")
        import traceback; traceback.print_exc()
    finally:
        try:
            await websocket.close()
            await agent.stop()
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn
    print(f"Model: {MODEL_ID}  Region: {BEDROCK_REGION}")
    uvicorn.run(app, host="127.0.0.1", port=8080)
