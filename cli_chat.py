#!/usr/bin/env python3
"""Interactive Real-Time CLI Client for MyNaksh FastAPI Service."""
import asyncio
import os
import sys

import httpx

SERVER_URL = os.getenv("API_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")


async def check_server_health(client: httpx.AsyncClient) -> bool:
    try:
        res = await client.get("/health")
        return res.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


async def fetch_brain_info(client: httpx.AsyncClient, user_id: str):
    print("\n\033[1;33m--- [SHARED BRAIN FACTS via FastAPI] ---\033[0m")

    # 1. Fetch User Profile
    try:
        u_res = await client.get(f"/users/{user_id}")
        if u_res.status_code == 200:
            user = u_res.json()
            print(f"Profile : Name={user.get('name')}, DOB={user.get('date_of_birth')}, "
                  f"Zodiac={user.get('zodiac')}, Lang={user.get('preferred_language')}")
        elif u_res.status_code == 404:
            print("Profile : (No profile registered yet)")
        else:
            print(f"Profile : Error {u_res.status_code}")
    except Exception as exc:
        print(f"Profile : Failed to query ({exc})")

    # 2. Fetch Stored Facts
    try:
        b_res = await client.get(f"/users/{user_id}/brain")
        if b_res.status_code == 200:
            facts = b_res.json().get("facts", [])
            if facts:
                for f in facts:
                    meta = f" (meta: {f['metadata']})" if f.get("metadata") else ""
                    print(f" • [{f.get('type')}] {f.get('key')}: {f.get('value')}{meta} (rel: {f.get('relation')})")
            else:
                print(" • (Brain has 0 stored facts)")
        else:
            print(f" • Error querying brain: {b_res.status_code}")
    except Exception as exc:
        print(f" • Failed to query brain ({exc})")

    print("\033[1;33m----------------------------------------\033[0m\n")


async def main():
    user_id = os.getenv("CHAT_USER_ID", "test_user_1")
    session_id = os.getenv("CHAT_SESSION_ID", "session_live_1")

    print("=" * 65)
    print("✨ MyNaksh Personalized Astrology Chat — Live FastAPI Client ✨")
    print(f"Target Server : {SERVER_URL}")
    print(f"User ID       : {user_id}")
    print(f"Session ID    : {session_id}")
    print("Commands      :")
    print("  /brain  - Query stored facts from GET /users/{id}/brain")
    print("  /exit   - Quit chat client")
    print("=" * 65)

    async with httpx.AsyncClient(base_url=SERVER_URL, timeout=90.0) as client:
        # Pre-flight check: ensure FastAPI server is running
        is_healthy = await check_server_health(client)
        if not is_healthy:
            print(f"\n\033[1;31m⚠️  Cannot connect to FastAPI server at {SERVER_URL}.\033[0m")
            print("Please make sure your server is running in another terminal tab:")
            print("  \033[1;36muvicorn app.main:app --reload\033[0m\n")
            sys.exit(1)

        print(f"\033[1;32m Connected to FastAPI server at {SERVER_URL}/health (Status: OK)\033[0m\n")
        print("Type your message below and press Enter:\n")

        while True:
            try:
                msg = input("\033[1;34mYou\033[0m: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting...")
                break

            if not msg:
                continue

            if msg.lower() in ("/exit", "exit", "quit"):
                print("Goodbye!")
                break

            if msg.lower() == "/brain":
                await fetch_brain_info(client, user_id)
                continue

            # Send HTTP POST /chat to FastAPI
            try:
                response = await client.post(
                    "/chat",
                    json={
                        "user_id": user_id,
                        "session_id": session_id,
                        "message": msg,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    response_text = data.get("response", "")
                    context_used = data.get("context_used", [])

                    print(f"\n\033[1;32mAI\033[0m : {response_text}")
                    print(f"\033[2m[Context Tags Used: {', '.join(context_used) if context_used else 'none'}]\033[0m\n")
                elif response.status_code == 422:
                    print(f"\n\033[1;31m[Validation Error 422]:\033[0m {response.text}\n")
                else:
                    print(f"\n\033[1;31m[HTTP {response.status_code} Error]:\033[0m {response.text}\n")

            except httpx.ConnectError:
                print(f"\n\033[1;31m[Connection Error]: Lost connection to {SERVER_URL}.\033[0m")
                print("Is Uvicorn still running?\n")
            except httpx.TimeoutException:
                print("\n\033[1;31m[Timeout]: The request to the LLM timed out. Please try again.\033[0m\n")
            except Exception as exc:
                print(f"\n\033[1;31m[Error]:\033[0m {exc}\n")


if __name__ == "__main__":
    asyncio.run(main())
