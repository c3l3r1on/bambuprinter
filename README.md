# bambuprinter

A small Python script to manage multiple Bambu printers from one place.

It is made for people who want a simple LAN workflow without heavy setup.

## What it does

- reads your printers from one JSON file
- sends `home` command to one or many printers
- sends calibration command with easy switches:
  - bed leveling
  - vibration calibration
  - motor noise calibration
- supports one-shot command for printers `1,2,3,4,5`

## Tested setup

- author test profile: **01.05**, LAN mode, Developer options enabled
- MQTT over local network (`bblp` + access code)

## Requirements

- Python 3.10+
- `bambu-printer-manager` package (module `bpm`)

Install dependency:

```bash
pip install bambu-printer-manager
```

## Quick start

1. Copy config template:

```bash
cp printers.example.json printers.json
```

2. Fill your printer data in `printers.json`.

3. List printers:

```bash
python3 bambuprinter.py --config printers.json list
```

## Config format

```json
{
  "printers": [
    {
      "id": 1,
      "name": "P1S-Left",
      "host": "192.168.9.201",
      "serial": "03XXXXXXXXXXXXXX",
      "access_code": "12345678",
      "port": 8883
    }
  ]
}
```

## Example commands

Home only for printers 1..5:

```bash
python3 bambuprinter.py --config printers.json home --printers 1,2,3,4,5
```

Calibration for printers 1..5 (bed + vibration + motor noise):

```bash
python3 bambuprinter.py --config printers.json calibrate --printers 1,2,3,4,5 --bed-leveling --vibration --motor-noise
```

Bed leveling only for printers 1..5:

```bash
python3 bambuprinter.py --config printers.json calibrate --printers 1,2,3,4,5 --bed-leveling
```

Home + calibration with custom delay:

```bash
python3 bambuprinter.py --config printers.json calibrate --printers 1,2,3,4,5 --bed-leveling --calibration-delay 4
```

Dry run (show payloads, do not send):

```bash
python3 bambuprinter.py --config printers.json --dry-run calibrate --printers 1,2,3,4,5 --bed-leveling --vibration --motor-noise
```

## Notes

- Keep `printers.json` private.
- Do not commit access codes.
- Use this only on your own printers/network.
