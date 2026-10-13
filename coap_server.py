#!/usr/bin/env python3

import asyncio
import json
import os
from datetime import datetime, timezone

import aiocoap
import aiocoap.resource as resource
import requests

# ctOP API configuration
CTOP_API_URL = "https://dev-ctop.iiit.ac.in/api/nodes/create-cin/63"
CTOP_API_TOKEN = os.environ.get("CTOP_API_TOKEN", "").strip()
CTOP_TIMEOUT_SECONDS = 10

# Store the latest telemetry in memory
latest_telemetry = None

# JSON content format
JSON_CONTENT_FORMAT = 50


def timestamp_now():
    return datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )


def validate_telemetry(data):
    required = ("v", "i", "p", "e", "s")

    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(
            "Missing required fields: " + ", ".join(missing)
        )

    try:
        voltage = float(data["v"])
        current = float(data["i"])
        power = float(data["p"])
        energy_kwh = float(data["e"])
        status = int(data["s"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid telemetry values") from exc

    if status not in (0, 1, 2, 3):
        raise ValueError("Status must be between 0 and 3")

    return {
        "v": voltage,
        "i": current,
        "p": power,
        "e": energy_kwh,
        "s": status,
    }


def forward_to_ctop(telemetry):
    """Forward telemetry to the ctOP HTTPS API."""

    if not CTOP_API_TOKEN:
        print(
            "ctOP forwarding skipped: "
            "CTOP_API_TOKEN is not configured."
        )
        return False

    # Map the received fields to ctOP API fields.
    api_data = {
        "voltage": telemetry["v"],
        "current": telemetry["i"],
        "power": telemetry["p"],
        "units": telemetry["e"],
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CTOP_API_TOKEN}",
    }

    try:
        response = requests.post(
            CTOP_API_URL,
            json=api_data,
            headers=headers,
            timeout=CTOP_TIMEOUT_SECONDS,
        )

        if 200 <= response.status_code < 300:
            print(
                f"ctOP API SUCCESS: HTTP {response.status_code}"
            )
            print("Response:", response.text)
            return True

        print(f"ctOP API ERROR: HTTP {response.status_code}")
        print("Response:", response.text)
        return False

    except requests.RequestException as exc:
        print("ctOP API request failed:", exc)
        return False


class EVTelemetryResource(resource.Resource):

    async def render_post(self, request):
        global latest_telemetry

        try:
            incoming = json.loads(
                request.payload.decode("utf-8")
            )
            telemetry = validate_telemetry(incoming)

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ) as exc:
            return aiocoap.Message(
                code=aiocoap.BAD_REQUEST,
                payload=json.dumps({
                    "error": str(exc)
                }).encode("utf-8"),
                content_format=JSON_CONTENT_FORMAT,
            )

        received_at = timestamp_now()

        latest_telemetry = {
            "data": telemetry,
            "received_at": received_at,
        }

        print(
            f"[{received_at}] EV telemetry received: "
            f"{json.dumps(telemetry)}"
        )

        # Forward the received data to ctOP.
        api_ok = await asyncio.to_thread(
            forward_to_ctop, telemetry
        )

        if api_ok:
            result = {
                "message":
                    "EV telemetry accepted and forwarded to ctOP"
            }
        else:
            result = {
                "message":
                    "Telemetry stored locally, but ctOP forwarding failed or was skipped"
            }

        return aiocoap.Message(
            code=aiocoap.CHANGED,
            payload=json.dumps(result).encode("utf-8"),
            content_format=JSON_CONTENT_FORMAT,
        )


class LatestTelemetryResource(resource.Resource):

    async def render_get(self, request):
        if latest_telemetry is None:
            payload = {
                "message": "No EV telemetry received yet"
            }
        else:
            payload = latest_telemetry

        return aiocoap.Message(
            code=aiocoap.CONTENT,
            payload=json.dumps(payload).encode("utf-8"),
            content_format=JSON_CONTENT_FORMAT,
        )


async def main():
    site = resource.Site()

    site.add_resource(
        ["telemetry", "ev"],
        EVTelemetryResource(),
    )

    site.add_resource(
        ["telemetry", "ev", "latest"],
        LatestTelemetryResource(),
    )

    protocol = await aiocoap.Context.create_server_context(
        site,
        bind=("::", 5683),
    )

    print("EV CoAP server listening on UDP port 5683")
    print("POST endpoint: /telemetry/ev")
    print("GET endpoint: /telemetry/ev/latest")

    if CTOP_API_TOKEN:
        print("ctOP forwarding is enabled")
    else:
        print(
            "WARNING: CTOP_API_TOKEN is not set; "
            "ctOP forwarding is disabled"
        )

    try:
        await asyncio.get_running_loop().create_future()
    finally:
        await protocol.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
