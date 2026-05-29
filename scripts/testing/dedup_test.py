import asyncio
import httpx
import time
import os

API_KEY = os.getenv("CAPI_LOAD_TEST_API_KEY", "")
URL = os.getenv("CAPI_LOAD_TEST_URL", "http://localhost:8000/api/v1/events")

async def send_duplicate(client, event_id):
    payload = {
        "data": [{
            "event_name": "Purchase",
            "event_time": int(time.time()),
            "event_id": event_id,
            "event_source_url": "http://example.com/dedup-test",
            "user_data": {
                "client_ip_address": "127.0.0.1",
                "client_user_agent": "Dedup-Tester"
            }
        }]
    }
    headers = {"X-API-Key": API_KEY}
    return await client.post(URL, json=payload, headers=headers)

async def main():
    if not API_KEY:
        raise SystemExit("Set CAPI_LOAD_TEST_API_KEY before running the dedup test.")

    event_id = f"unique_test_{int(time.time())}"
    print(f"Sending 10 concurrent requests for event_id: {event_id}")

    async with httpx.AsyncClient() as client:
        tasks = [send_duplicate(client, event_id) for _ in range(10)]
        responses = await asyncio.gather(*tasks)

    status_codes = [r.status_code for r in responses]
    print(f"Status codes: {status_codes}")

    # In theory, only the first one should actually trigger a Facebook send (mocked)
    # The others should return success because they are deduplicated.
    # We should check logs to see how many "MOCK API" entries appear.

if __name__ == "__main__":
    asyncio.run(main())
