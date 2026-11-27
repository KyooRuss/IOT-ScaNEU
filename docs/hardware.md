# Connecting the hardware

The Arduinos, RFID readers, IR sensors, barriers and camera are not connected yet. Until they are, the simulator page (`/dev/simulator`) stands in for them, and the terminal running `python run.py` prints a line for every message the hardware will send or receive. This page lists each of those lines, the hardware it stands for, and the code that changes when that hardware is connected.

Line numbers are as of the commit that added this page. If the code has moved since, search for the function name.

## Reading the log

Start `python run.py`, open `/dev/simulator`, send a vehicle and flip the IR switch. The terminal shows:

```
10:25:28  entrance  Arduino -> Pi  UID:04A1B2C3   card tapped                          dev/routes.py:50
10:25:28  entrance  Camera -> Pi   ABC1234        plate read                           dev/routes.py:51
10:25:28  entrance  Pi -> Arduino  OPEN           lift barrier, green LED, short beep  gate/controller.py:48
10:25:28  entrance  Arduino -> Pi  IR:1           vehicle under barrier                dev/routes.py:64
10:25:28  entrance  Arduino -> Pi  IR:0           barrier clear                        dev/routes.py:66
10:25:28  entrance  Pi -> Arduino  CLOSE          lower barrier                        gate/controller.py:93
```

Each line is: the time, the lane (entrance or exit), which way the message goes, the message itself, what it means, and the file and line that printed it. Set `SCANEU_ARDUINO_LOG=0` in `.env` to turn the log off.

## Every log line

| Log line | Hardware | Meaning | Printed by, for now |
|---|---|---|---|
| `Arduino -> Pi  UID:04A1B2C3` | RFID reader (RC522) on the Arduino | A card was tapped. The UID is the card's number in hex. | `vehicle()` in [dev/routes.py:50](../scaneu/dev/routes.py#L50) |
| `Camera -> Pi  ABC1234` | Camera on the Pi, with plate recognition (YOLO11n + OCR) | The plate the camera read, or `(none)` if it could not read one. Not an Arduino message; it is there to show the order. | `vehicle()` in [dev/routes.py:51](../scaneu/dev/routes.py#L51) |
| `Arduino -> Pi  IR:1` | IR sensor under the barrier | A vehicle is under the barrier. | `ir()` in [dev/routes.py:64](../scaneu/dev/routes.py#L64) |
| `Arduino -> Pi  IR:0` | IR sensor under the barrier | The vehicle has passed. | `ir()` in [dev/routes.py:66](../scaneu/dev/routes.py#L66) |
| `Arduino -> Pi  BTN` | Manual override button | Someone pressed the button at the lane. | `button()` in [dev/routes.py:78](../scaneu/dev/routes.py#L78) |
| `Pi -> Arduino  OPEN` | Barrier, green LED, buzzer | Lift the barrier, green LED on, short beep. | `MockGateController.open()` in [gate/controller.py:48](../scaneu/gate/controller.py#L48) |
| `Pi -> Arduino  DENY` | Barrier, red LED, buzzer | Keep the barrier closed, red LED on, long beep. Sent when the vehicle is refused or has to wait for the guard. | `MockGateController.hold()` in [gate/controller.py:54](../scaneu/gate/controller.py#L54) |
| `Pi -> Arduino  CLOSE` | Barrier | Lower the barrier. Sent 3 s after the IR sensor clears, or 15 s after `OPEN` if no vehicle crossed (`SCANEU_BARRIER_CLOSE_DELAY` and `SCANEU_BARRIER_OPEN_TIMEOUT`). | `MockGateController._close()` in [gate/controller.py:93](../scaneu/gate/controller.py#L93) |

## What changes when the hardware arrives

Three pieces of new code. The gate rules, the database and the dashboard stay as they are.

### 1. Serial reader: Arduino → Pi

This replaces the simulator routes in [scaneu/dev/routes.py](../scaneu/dev/routes.py).

It opens each Arduino's USB serial port (9600 baud; on the Pi usually `/dev/ttyACM0` and `/dev/ttyACM1`), reads one line at a time, and calls the same function the simulator calls today:

| Line from the Arduino | What the reader calls | Simulator route doing it now |
|---|---|---|
| `UID:<uid>` | `service.handle_vehicle(lane, rfid_uid=uid, plate_text=..., image_path=...)`, with the camera's result from part 3 | `vehicle()` |
| `IR:1` / `IR:0` | `service.controller().set_vehicle_present(lane, True)` / `(lane, False)` | `ir()` |
| `BTN` | `service.controller().open(lane)` | `button()` |

It runs in a background thread inside `with app.app_context():`, because these functions use the database. It needs the `pyserial` package and a setting for which port is the entrance and which is the exit.

### 2. Barrier controller: Pi → Arduino

A `SerialGateController` in [scaneu/gate/controller.py](../scaneu/gate/controller.py), with the same methods as `MockGateController`. It replaces the mock where the app creates it, in [scaneu/\_\_init\_\_.py:33](../scaneu/__init__.py#L33).

The three `serial_log.to_arduino(...)` lines in `MockGateController` (lines 48, 54 and 93) are exactly where the Pi has to write `OPEN`, `DENY` and `CLOSE` to the lane's port. The simplest way to build it is to start from `MockGateController`, which already runs the close timers and updates the dashboard, and add a serial write at those three lines.

### 3. Camera and plate recognition

This runs on the Pi, not the Arduino. When a card is tapped, the Pi takes a photo and reads the plate, then passes both to `handle_vehicle`:

- `plate_text`: the plate it read, or `None` if it could not read one. The dashboard then flags the visit as "Plate unreadable".
- `image_path`: where the photo was saved, relative to `data/images/`, in one folder per day (for example `2026-11-27/entrance-102528.jpg`). The dashboard shows photos from there.

Today the simulator's plate field does this job: the `Camera -> Pi` line, [dev/routes.py:51](../scaneu/dev/routes.py#L51).

## Checklist for the Arduino code

The full protocol is in the README under "Arduino serial protocol": one text line per message at 9600 baud (`Serial.println` is fine).

- When a card is tapped, send `UID:` and the card's UID in hex, e.g. `UID:04A1B2C3`.
- Send `IR:1` when the sensor sees a vehicle and `IR:0` when it clears.
- Send `BTN` when the manual button is pressed.
- On `OPEN`: lift the barrier, green LED, short beep.
- On `DENY`: keep the barrier closed, red LED, long beep.
- On `CLOSE`: lower the barrier and turn the LEDs off, but never while the IR sensor sees a vehicle.

## Open questions

- **Visitors without a card.** The Arduino only sends a message when a card is tapped, so for a visitor nothing tells the Pi that a car has arrived. In the simulator you just press Send. Options: the camera watches the lane and detects cars on its own, a second sensor before the barrier, or a capture button for the guard on the dashboard (the documentation lists a `force_capture` guard action, not built yet).
- **Manual button.** On `BTN`, the Pi currently answers with `OPEN`. Should the Arduino wait for that, or lift the barrier on its own?
- **Which Arduino is which lane.** Either decide which USB port is the entrance and which is the exit, or have each Arduino send its lane when it starts.
