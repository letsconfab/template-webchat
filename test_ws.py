"""
WebSocket chat test: login, connect, ask "What is INTEGRATE?", print response.
"""
import asyncio
import httpx
import json
import uuid

WS_URL = "ws://localhost:8000/ws/chat"
API_URL = "http://localhost:8000"


async def main():
    # 1. Login
    async with httpx.AsyncClient(base_url=API_URL) as c:
        r = await c.post("/api/auth/login", json={
            "email": "gsingh@embetter.in",
            "password": "admin123",
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        token = r.json()["access_token"]
        print(f"[OK] Logged in, token={token[:40]}...")

    import websockets
    async with websockets.connect(
        WS_URL,
        origin="http://localhost:3030",
        ping_interval=None,
    ) as ws:
        print("[OK] WebSocket connected")

        # 2. Send session init
        await ws.send(json.dumps({
            "session_id": str(uuid.uuid4()),
            "provider": "sarvam",
            "model": "sarvam-30b",
            "api_key": "",
        }))

        # 3. Read initial status/history messages
        initial = await asyncio.wait_for(ws.recv(), timeout=15)
        data = json.loads(initial)
        print(f"[INIT] type={data.get('type')} {str(data)[:300]}")
        if data.get("type") == "history":
            initial2 = await asyncio.wait_for(ws.recv(), timeout=15)
            data = json.loads(initial2)
            print(f"[INIT] type={data.get('type')} {str(data)[:300]}")

        # 4. Send question
        await ws.send(json.dumps({"message": "What is INTEGRATE ?"}))
        print("[SENT] What is INTEGRATE ?")

        # 5. Read response
        full_response = ""
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=180)
                data = json.loads(msg)
                print(f"[RECV] type={data.get('type')} {str(data)[:200]}")
                if data.get("type") == "start":
                    continue
                elif data.get("type") == "think":
                    print(f"[THINK] {data.get('content', '')[:150]}")
                elif data.get("type") == "chunk":
                    full_response += data.get("content", "")
                elif data.get("type") == "end":
                    break
                elif data.get("type") == "error":
                    print(f"[ERROR] {data}")
                    break
            except asyncio.TimeoutError:
                print("[TIMEOUT] No response within 3 min")
                break

        print("\n" + "=" * 60)
        print("FULL RESPONSE:")
        print(full_response)
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
