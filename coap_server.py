#!/usr/bin/env python3

import asyncio
import json
import math
from datetime import datetime

import aiocoap
import aiocoap.resource as resource
from aiocoap.numbers.contentformat import ContentFormat


# CoAP application/json has content-format number 50.
JSON_FORMAT = ContentFormat(50)

# Shared storage for the most recently accepted EV sample.
state = {
    "payload": None,
    "received_at": None,
}


def validate_ev_data(data):
    """Validate the expected EV telemetry fields."""

    if not isinstance(data, dict):
        raise ValueError("JSON payload must be an object")

    required = ("v", "i", "p", "e", "s")

    for key in required:
        if key not in data:
            raise ValueError(f"Missing field: {key}")

    # Voltage, current, power and energy must be finite,
    # non-negative numbers (boolean values are not accepted).
    for key in ("v", "i", "p", "e"):
        value = data[key]

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"Invalid numeric field: {key}")

    status = data["s"]

    if (
        isinstance(status, bool)
        or not isinstance(status, int)
        or status not in (0, 1, 2, 3)
    ):
        raise ValueError("Status must be an integer from 0 to 3")

    # Return only the agreed fields.
    return {
        "v": data["v"],
        "i": data["i"],
        "p": data["p"],
        "e": data["e"],
        "s": status,
    }


class EVTelemetryResource(resource.Resource):
    """POST new readings and GET the latest reading."""

    async def render_post(self, request):
        try:
            data = json.loads(request.payload.decode("utf-8"))
            data = validate_ev_data(data)

            payload = json.dumps(
                data,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")

        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            print(f"Rejected POST: {exc}", flush=True)

            return aiocoap.Message(
                code=aiocoap.BAD_REQUEST,
                payload=str(exc).encode("utf-8"),
                content_format=ContentFormat.TEXT,
            )

        state["payload"] = payload
        state["received_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )

        print(
            f"[{state['received_at']}] EV telemetry accepted: "
            f"{payload.decode('utf-8')}",
            flush=True,
        )

        return aiocoap.Message(
            code=aiocoap.CHANGED,
            payload=b"EV telemetry accepted",
            content_format=ContentFormat.TEXT,
        )

    async def render_get(self, request):
        if state["payload"] is None:
            return aiocoap.Message(
                code=aiocoap.SERVICE_UNAVAILABLE,
                payload=b"No EV telemetry received yet",
                content_format=ContentFormat.TEXT,
            )

        return aiocoap.Message(
            code=aiocoap.CONTENT,
            payload=state["payload"],
            content_format=JSON_FORMAT,
        )


class LatestEVResource(resource.Resource):
    """Read-only endpoint for retrieving the latest sample."""

    async def render_get(self, request):
        if state["payload"] is None:
            return aiocoap.Message(
                code=aiocoap.SERVICE_UNAVAILABLE,
                payload=b"No EV telemetry received yet",
                content_format=ContentFormat.TEXT,
            )

        result = {
            "data": json.loads(state["payload"].decode("utf-8")),
            "received_at": state["received_at"],
        }

        return aiocoap.Message(
            code=aiocoap.CONTENT,
            payload=json.dumps(result, separators=(",", ":")).encode("utf-8"),
            content_format=JSON_FORMAT,
        )


async def main():
    site = resource.Site()

    site.add_resource(
        [".well-known", "core"],
        resource.WKCResource(site.get_resources_as_linkheader),
    )

    site.add_resource(
        ["telemetry", "ev"],
        EVTelemetryResource(),
    )

    site.add_resource(
        ["telemetry", "ev", "latest"],
        LatestEVResource(),
    )

    # Listen for CoAP requests on IPv6 port 5683.
    await aiocoap.Context.create_server_context(
        site,
        bind=("::", 5683),
    )

    print("EV CoAP receiver started", flush=True)
    print("Listening on IPv6 UDP port 5683", flush=True)
    print("POST /telemetry/ev", flush=True)
    print("GET  /telemetry/ev/latest", flush=True)

    await asyncio.get_running_loop().create_future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nEV CoAP receiver stopped", flush=True)