# EV Charger CoAP Implementation — Detailed Project Documentation

**Document status:** Working implementation notes, based on project progress and terminal results recorded in this conversation.  
**Last documented date:** 2026-10-13  
**Scope:** Pi-EV PZEM telemetry → FG25/WSTK serial CLI → Wi-SUN CoAP POST → Pi-BR CoAP receiver.

---

## 1. Overview

This project sends EV charger electrical telemetry from a Raspberry Pi that reads a PZEM-004T meter to a second Raspberry Pi over a Wi-SUN network. The EFR32FG25/WSTK acts as the Wi-SUN node and sends readings to the Border Router Raspberry Pi using CoAP.

### Intended data path

```text
PZEM-004T
    │
    ▼
Pi-EV: Charger_script.py
    │  USB serial / VCOM command: ev_update <v> <i> <p> <e> <s>
    ▼
EFR32FG25 / WSTK
    │  Wi-SUN CoAP POST, JSON, every ~5 seconds
    ▼
Pi-BR: coap_server.py
    │
    ▼
GET /telemetry/ev/latest
```

The existing local UDP telemetry from `Charger_script.py` to `127.0.0.1:5000` is a separate path for the local backend and is intended to remain unchanged. It is not the Wi-SUN CoAP transport.

## 2. Hardware and software components

| Component | Role | Notes |
|---|---|---|
| Pi-EV (Raspberry Pi) | Reads PZEM data and runs charger display/relay script | `/home/evcharger/EVCS-4/Charger_script.py` |
| PZEM-004T | Measures voltage, current, power, and energy | Python `minimalmodbus` |
| EFR32FG25/WSTK | Wi-SUN node and CoAP sender | Connected to Pi-EV by USB/VCOM |
| Pi-BR (Raspberry Pi) | Wi-SUN Border Router and CoAP receiver | Python `aiocoap` server |
| Wi-SUN network | IPv6 connectivity between FG25 and Pi-BR | Stack 2.11.1; FAN 1.1; EU533 recorded |
| Simplicity Studio / SDK | FG25 firmware development | Simplicity Studio 6; SDK Suite 2025.12.3 |

### Serial and network identifiers recorded

| Item | Recorded value |
|---|---|
| Pi-EV FG25 VCOM serial device | `/dev/ttyACM0` |
| FG25 serial baud rate | `115200` |
| PZEM serial device | `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0` |
| PZEM baud rate | `9600` |
| Pi-BR Wi-SUN IPv6 on `tun0` | `fd12:3456::92fd:9fff:feee:9d54/64` |
| CoAP receiver port | UDP `5683` |
| CoAP POST resource | `/telemetry/ev` |
| Latest-data GET resource | `/telemetry/ev/latest` |
| FG25 CoAP POST interval | `5000 ms` |
| Local backend UDP destination | `127.0.0.1:5000` |

**Address caution:** The FG25 IPv6 address has varied in earlier sessions. Verify its current address after reboot or network rejoin. The address above is the Pi-BR receiver address recorded for these tests.

## 3. Telemetry payload

The FG25 posts JSON with these keys:

| Key | Meaning | Representation |
|---|---|---|
| `v` | Voltage in volts | Number |
| `i` | Current in amperes | Number |
| `p` | Power in watts | Number |
| `e` | Energy in kWh | Number |
| `s` | Status | Integer |

The Python sender converts the PZEM's `energy_Wh` field to kWh by dividing by 1000. Its temporary status mapping is:
- `0` = idle when current is at or below `0.1 A`
- `1` = charging when current is above `0.1 A`

The receiver validates numeric `v`, `i`, `p`, and `e`, and an integer `s` from 0 through 3.

Example payload:

```json
{"v":233.4,"i":0.00,"p":0.0,"e":0.000,"s":0}
```

This is an example only; actual values depend on the meter and charger state.

## 4. Pi-BR: CoAP receiver

### 4.1 File and virtual environment

Receiver file:

```text
/home/wisun/ev_charger/coap_server.py
```

Virtual environment:

```text
/home/wisun/coap-venv/
```

`aiocoap` was installed in that environment. Start the receiver with:

```bash
/home/wisun/coap-venv/bin/python /home/wisun/ev_charger/coap_server.py
```

The server binds to IPv6 wildcard address `("::", 5683)` and exposes two resources.

### 4.2 Resources

| Method | URI | Function |
|---|---|---|
| POST | `/telemetry/ev` | Accepts and validates telemetry JSON, stores the latest payload in RAM, logs receipt with timestamp, and returns an acceptance response |
| GET | `/telemetry/ev/latest` | Returns the latest stored payload and `received_at` timestamp |

Example POST:

```json
{"v":229.2,"i":0.44,"p":100.8,"e":0.125,"s":1}
```

Successful response recorded:

```text
EV telemetry accepted
```

Example GET command on Pi-BR:

```bash
coap-client-notls -m get \
  "coap://[fd12:3456::92fd:9fff:feee:9d54]:5683/telemetry/ev/latest"
```

Expected response shape:

```json
{"data":{"v":229.2,"i":0.44,"p":100.8,"e":0.125,"s":1},"received_at":"2026-10-13T10:58:55+05:30"}
```

The values and timestamp above illustrate a recorded response; they are not guaranteed to be current. The latest-value storage is in RAM, so assume it clears when the server restarts unless persistence is added.

### 4.3 Receiver verification performed

The following checks passed earlier:
1. `aiocoap` server started in the virtual environment.
2. Port 5683 was confirmed listening using `ss`.
3. A local CoAP test to `[::1]:5683` succeeded.
4. A POST to the Pi-BR Wi-SUN IPv6 address succeeded.
5. A GET to `/telemetry/ev/latest` returned the stored payload and timestamp.

Commands used:

```bash
sudo ss -lunp | grep ':5683'
```

```bash
coap-client-notls -m post -t application/json \
  -e '{"v":229.2,"i":0.44,"p":100.8,"e":0.125,"s":1}' \
  "coap://[fd12:3456::92fd:9fff:feee:9d54]:5683/telemetry/ev"
```

```bash
coap-client-notls -m get \
  "coap://[fd12:3456::92fd:9fff:feee:9d54]:5683/telemetry/ev/latest"
```

### 4.4 Connection-refused warning

A warning was observed:

```text
coap_network_read: ICMP: Connection refused
```

The logged local and remote IPv6 addresses were both `fd12:3456::92fd:9fff:feee:9d54`. This suggests the client may have been trying to reach the Pi-BR address from Pi-BR itself, but the exact origin was not established from the log alone.

Check whether the server is listening:

```bash
sudo ss -lunp | grep ':5683'
```

If no listener is shown, start the server with the command above. If a process is already listening, do not start a duplicate; inspect the existing process and its terminal output.

## 5. FG25/WSTK firmware: CoAP sender

### 5.1 Existing project behavior

The Simplicity Studio project is named `Wi-SUN - SoC Socket`. It joins the Wi-SUN network and prints `Operational`. It also provides:
- A CoAP GET resource `/ev`
- A VCOM CLI command `ev_update`

The VCOM stream selection was changed in:

```text
config/sl_cli_config_vcom.h
```

from:

```c
sl_iostream_recommended_console_stream
```

to:

```c
sl_iostream_get_handle("vcom")
```

This change was necessary for the custom serial CLI to work in the recorded setup. Do not revert it without a specific reason.

### 5.2 Dynamic response buffer

In `app_coap.c`, the `/ev` GET response is held in a mutable buffer. The recorded initial dummy payload was:

```c
#define EV_RESPONSE_SIZE 128

static char ev_response[EV_RESPONSE_SIZE] =
    "{\"v\":229.2,\"i\":0.44,\"p\":100.8,\"e\":0.125,\"s\":1}";
```

The initial value is a dummy/test payload. If no successful `ev_update` command changes the buffer, periodic POSTs will continue to carry these values.

The CLI handler `ev_update_command(sl_cli_command_arg_t *arguments)` parses five string arguments, validates the values and status, then formats the JSON into `ev_response` using `snprintf`, conceptually:

```c
snprintf(ev_response, sizeof(ev_response),
         "{\"v\":%.1f,\"i\":%.2f,\"p\":%.1f,\"e\":%.3f,\"s\":%lu}",
         voltage, current, power, energy_kwh, status);
printf("EV data updated: %s\r\n", ev_response);
```

Manual command tested on the FG25 VCOM CLI:

```text
ev_update 229.2 0.44 100.8 0.125 1
```

The command was reported to update the JSON response, and a subsequent GET to `/ev` returned the updated values. Dynamic manual updates were tested with more than one set of values.

### 5.3 CoAP notification POST

The firmware uses the Wi-SUN CoAP notification API:
- Header: `sl_wisun_coap_notify.h`
- Initialization: `sl_wisun_coap_notify_init()`
- Registration: `sl_wisun_coap_notify_add(&ev_post_notify)`

Recorded configuration:

```c
#define EV_POST_URI_PATH "telemetry/ev"
#define EV_POST_INTERVAL_MS 5000U
#define EV_POST_BR_IPV6 "fd12:3456::92fd:9fff:feee:9d54"
#define EV_POST_BR_PORT 5683U
#define EV_JSON_CONTENT_FORMAT 50U
```

The notification structure uses ID `"ev-telemetry-post"`, parses the remote IPv6 address using `inet_pton(AF_INET6, ...)`, sets the port with `htons(EV_POST_BR_PORT)`, and uses a condition callback that returns `true`.

The packet callback creates a CoAP POST with:
- Request code `COAP_MSG_CODE_REQUEST_POST`
- Non-confirmable type `COAP_MSG_TYPE_NON_CONFIRMABLE`
- Content format `50` (`application/json`)
- URI path `telemetry/ev`
- Payload pointer to `ev_response`
- Payload length `strlen(ev_response)`
- Incrementing message ID

Critical dynamic payload lines:

```c
packet.payload_ptr = (uint8_t *)ev_response;
packet.payload_len = (uint16_t)strlen(ev_response);
```

These lines make each callback use the current mutable response buffer, so periodic POSTs are intended to carry the latest CLI-updated values. Periodic POSTs were observed at Pi-BR, but Python-driven live updates still need an end-to-end confirmation.

### 5.4 Receiver log observed

Pi-BR logged repeated accepted POSTs with the same dummy payload:

```text
[2026-10-13T10:58:55+05:30] EV telemetry accepted: {"v":229.2,"i":0.44,"p":100.8,"e":0.125,"s":1}
[2026-10-13T10:58:58+05:30] EV telemetry accepted: {"v":229.2,"i":0.44,"p":100.8,"e":0.125,"s":1}
[2026-10-13T10:59:00+05:30] EV telemetry accepted: {"v":229.2,"i":0.44,"p":100.8,"e":0.125,"s":1}
```

This confirms periodic POSTs reached the server. At that time, the payload was still the firmware's dummy JSON, so the receiver transport was working while the live Python → CLI → buffer update remained unresolved.

## 6. Pi-EV: Python telemetry sender

### 6.1 Script and configuration

Script:

```text
/home/evcharger/EVCS-4/Charger_script.py
```

Recorded relevant configuration:

```python
PZEM_PORT = "/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A50285BI-if00-port0"
PZEM_BAUD = 9600

FG25_PORT = "/dev/ttyACM0"
FG25_BAUD = 115200

WISUN_SEND_INTERVAL = 5.0

LOCAL_UDP_IP = "127.0.0.1"
LOCAL_UDP_PORT = 5000
```

The PZEM is read using `minimalmodbus`. The script also runs a Tkinter dashboard and maintains the local UDP backend feed.

### 6.2 Sender function

The function shared most recently is:

```python
def send_ev_data_to_fg25(fg25_serial, readings):
    """Send current PZEM readings to the FG25 CLI."""

    voltage = float(readings["voltage_V"])
    current = float(readings["current_A"])
    power = float(readings["power_W"])
    energy_kwh = float(readings["energy_Wh"]) / 1000.0

    # Temporary status mapping:
    # 0 = IDLE, 1 = CHARGING
    status = 1 if current > 0.1 else 0

    command = (
        f"ev_update {voltage:.1f} "
        f"{current:.2f} "
        f"{power:.1f} "
        f"{energy_kwh:.3f} "
        f"{status}\r\n"
    )

    fg25_serial.write(command.encode("ascii"))
    fg25_serial.flush()

    print(
        "FG25 CLI TX:",
        command.strip()
    )
```

A receive-debugging snippet was also discussed to read `fg25_serial.in_waiting`, print `FG25 CLI RX`, or print `<no response received>`. Check the actual live file if the response output is needed; the latest pasted function version did not include that snippet.

### 6.3 Monitoring loop

The user's latest `monitor_pzem(app)` version:
1. Creates the PZEM object.
2. Creates the existing local UDP socket to `127.0.0.1:5000`.
3. Opens FG25 serial at `/dev/ttyACM0`, 115200 baud.
4. Waits for PZEM readiness.
5. Reads PZEM data continuously.
6. Every five seconds, if FG25 serial exists and is open, calls `send_ev_data_to_fg25(fg25_serial, readings)`.
7. Continues local UDP telemetry, target-unit file reading, and GUI updates.

The corrected send condition is:

```python
now = time.monotonic()

if (
    fg25_serial is not None
    and fg25_serial.is_open
    and (now - last_wisun_send >= WISUN_SEND_INTERVAL)
):
    try:
        send_ev_data_to_fg25(
            fg25_serial,
            readings
        )
        last_wisun_send = now
    except Exception as e:
        print("FG25 send error:", e)
```

This removes the obsolete `fg25_socket_id` dependency. The old `create_wisun_socket()` helper and the old `FG25_SOCKET_ID` / `BORDER_ROUTER_UDP_PORT` constants can remain unused, but should not be called in the CoAP design.

### 6.4 Old error and correction

The script previously contained the old condition:

```python
if fg25_serial and fg25_socket_id is not None and (
    now - last_wisun_send >= WISUN_SEND_INTERVAL
):
```

It produced:

```text
PZEM read error: name 'fg25_socket_id' is not defined
```

The user later shared a revised monitoring loop that checks only `fg25_serial`, `fg25_serial.is_open`, and the five-second interval. This correction is structurally appropriate for the new architecture.

### 6.5 Latest observed Pi-EV output

After updating serial initialization, the user reported:

```text
=== EV Charger Display & Relay Controller Started ===
Starting PZEM continuous monitoring...
Ready to send telemetry to 127.0.0.1:5000
FG25 connected: /dev/ttyACM0
PZEM CONNECTED. Monitoring...
PZEM: V=233.4V  I=0.00A  P=0.0W  Units=0.0
PZEM read error: name 'fg25_socket_id' is not defined
...
```

That output was from before the old condition was corrected. The user subsequently shared the revised `monitor_pzem()` code with the corrected condition and asked whether it was correct. The revised code was assessed as structurally correct, but there is not yet a post-fix terminal log confirming that `FG25 CLI TX` appears.

Therefore, the end-to-end update from PZEM through Python CLI to the CoAP POST payload remains to be re-tested after the latest edit.

## 7. Old UDP code versus current CoAP implementation

The script still has an old helper:

```python
def create_wisun_socket(fg25_serial, retries=10):
    ...
    fg25_serial.write(b"wisun udp_client\r")
    ...
```

It waits for output such as `[Socket created: 13]` and belongs to the previous raw-UDP Wi-SUN socket approach.

For the current design:
- Do not call `create_wisun_socket()`.
- Do not use `wisun socket_write` to send telemetry.
- Do not require `fg25_socket_id` in the send condition.
- Send `ev_update ...` through the FG25 VCOM CLI.
- Let the FG25 CoAP notification sender post the updated JSON to Pi-BR.

The old helper can be removed later for cleanup, but it does not need to be deleted for the new path to work if it is unused.

## 8. End-to-end testing checklist

### A. Confirm the Pi-BR receiver is listening

On Pi-BR:

```bash
sudo ss -lunp | grep ':5683'
```

If the server is not running:

```bash
/home/wisun/coap-venv/bin/python /home/wisun/ev_charger/coap_server.py
```

### B. Confirm periodic CoAP POSTs arrive

Watch the terminal running `coap_server.py`. Expected log shape:

```text
EV telemetry accepted: {"v":...,"i":...,"p":...,"e":...,"s":...}
```

Values should change when the input data changes and the serial update succeeds.

### C. Confirm Pi-EV opens FG25 serial

On Pi-EV:

```bash
python3 /home/evcharger/EVCS-4/Charger_script.py
```

Expected:

```text
FG25 connected: /dev/ttyACM0
```

### D. Confirm Python sends `ev_update`

The same terminal should show:

```text
FG25 CLI TX: ev_update ...
```

approximately every five seconds. If it does not, check the corrected condition, `fg25_serial.is_open`, `last_wisun_send`, and any earlier exceptions.

### E. Confirm FG25 accepts the command

If receive-debugging code is enabled, look for output similar to:

```text
FG25 CLI RX: EV data updated: {"v":...,"i":...,"p":...,"e":...,"s":...}
```

This exact response has not yet been confirmed for the automated Python sender. A `<no response received>` result does not prove the command was rejected; CLI output and serial buffering can affect what is read.

The firmware's manual CLI command was previously tested:

```text
ev_update 229.2 0.44 100.8 0.125 1
```

Manual dynamic updates were reported to work.

### F. Confirm the latest endpoint changes

On Pi-BR:

```bash
coap-client-notls -m get \
  "coap://[fd12:3456::92fd:9fff:feee:9d54]:5683/telemetry/ev/latest"
```

Compare `v`, `i`, `p`, `e`, and `s` with the Python `FG25 CLI TX` values. Remember that the Python script divides `energy_Wh` by 1000 to get kWh.

## 9. Troubleshooting notes

### `name 'fg25_socket_id' is not defined`

An old UDP condition remained in the monitoring loop. Remove that dependency and use the corrected serial-only condition.

### CoAP `ICMP: Connection refused`

Check that the receiver is running and port 5683 is listening. The warning does not by itself prove the receiver code is wrong; it may mean there was no UDP listener at the destination at that moment.

### Receiver accepts repeated dummy payloads

If Pi-BR logs the same dummy JSON every five seconds, the CoAP sender and receiver are communicating, but the FG25 `ev_response` buffer is not being updated by the serial command (or the Python command is not being processed). Check in this order:
1. Does Pi-EV print `FG25 CLI TX`?
2. Is Pi-EV connected to the correct FG25 VCOM stream?
3. Does the FG25 CLI respond to `ev_update`?
4. Does a manual `ev_update` change the FG25 `/ev` GET response?
5. Does the next CoAP POST contain the changed values?

Do not rewrite the Pi-BR receiver or CoAP notification implementation before confirming these steps; those components passed separate tests.

### No `FG25 CLI TX` output

Check that:
- The corrected condition is in the running script.
- `fg25_serial` is not `None` and `fg25_serial.is_open` is true.
- `last_wisun_send` is initialized before the loop.
- The loop reaches the send condition without raising an earlier exception.
- The call is `send_ev_data_to_fg25(fg25_serial, readings)`.

### GUI / headless operation

The script uses Tkinter (`app.mainloop()`) and schedules GUI updates through `app.after(...)`. A previous `$DISPLAY` issue was discussed, but the latest user output showed startup, PZEM connection, and monitoring output, so the GUI/monitoring path was running in that test.

## 10. Current status summary

| Area | Status based on recorded tests |
|---|---|
| PZEM reading on Pi-EV | Confirmed working; live voltage readings displayed |
| Pi-EV opens FG25 VCOM | Confirmed in latest output: `FG25 connected: /dev/ttyACM0` |
| FG25 joins Wi-SUN | Previously confirmed; firmware prints `Operational` |
| FG25 `/ev` CoAP GET resource | Previously confirmed working |
| FG25 manual `ev_update` command | Previously confirmed working; dynamic updates manually tested |
| FG25 periodic CoAP POST | Confirmed; Pi-BR logged repeated accepted posts |
| Pi-BR CoAP receiver and GET latest | Previously confirmed working |
| Old UDP socket helper | Not needed for current design; should remain unused |
| Corrected Python monitoring condition | Shared by user; appears structurally correct |
| Python `FG25 CLI TX` after latest correction | Not yet confirmed after the fix |
| Python-driven dynamic update reaching Pi-BR | **Not yet confirmed end-to-end** |

## 11. Recommended next action

1. Save the latest `monitor_pzem()` version that no longer references `fg25_socket_id`.
2. Stop any old running instance of `Charger_script.py` and restart it.
3. Confirm `FG25 CLI TX` appears every five seconds.
4. Compare those values with Pi-BR's `EV telemetry accepted` log and `GET /telemetry/ev/latest` result.
5. If the receiver still shows dummy values, collect one matching `FG25 CLI TX` line, one `FG25 CLI RX` line (if available), and one Pi-BR accepted-POST line.

Keep the existing CoAP receiver and FG25 notification code unchanged until these results show where the live update stops.
