#!/usr/bin/env python3
"""Simple multi-printer helper for Bambu printers (LAN mode)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List

try:
    from bpm.bambuconfig import BambuConfig
    from bpm.bambuprinter import BambuPrinter
except Exception as exc:  # pragma: no cover
    print("ERROR: Missing dependency 'bpm' (bambu-printer-manager).")
    print("Install with: pip install bambu-printer-manager")
    print(f"Details: {exc}")
    sys.exit(2)


BIT_BED_LEVELING = 1 << 1  # 2
BIT_VIBRATION = 1 << 2     # 4
BIT_MOTOR_NOISE = 1 << 3   # 8


@dataclass
class PrinterEntry:
    id: int
    name: str
    host: str
    serial: str
    access_code: str
    port: int = 8883


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bambusy.py",
        description="One small script to control many Bambu printers over LAN.",
    )
    parser.add_argument(
        "--config",
        default="printers.json",
        help="Path to printers config JSON file (default: printers.json)",
    )
    parser.add_argument(
        "--connect-wait",
        type=float,
        default=2.0,
        help="Seconds to wait after MQTT session start (default: 2.0)",
    )
    parser.add_argument(
        "--post-wait",
        type=float,
        default=1.0,
        help="Seconds to wait after sending commands (default: 1.0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be sent, but do not connect/send.",
    )

    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparsers.add_parser("list", help="List printers from config")

    home = subparsers.add_parser("home", help="Send HOME command")
    home.add_argument(
        "--printers",
        required=True,
        help="Printer IDs, e.g. 1,2,3,4,5",
    )

    cal = subparsers.add_parser(
        "calibrate",
        help="Send HOME and optional CALIBRATION command",
    )
    cal.add_argument(
        "--printers",
        required=True,
        help="Printer IDs, e.g. 1,2,3,4,5",
    )
    cal.add_argument("--bed-leveling", action="store_true", help="Enable bed leveling")
    cal.add_argument("--vibration", action="store_true", help="Enable vibration calibration")
    cal.add_argument("--motor-noise", action="store_true", help="Enable motor noise calibration")
    cal.add_argument(
        "--home-only",
        action="store_true",
        help="Only send HOME, skip calibration command",
    )
    cal.add_argument(
        "--calibration-delay",
        type=float,
        default=3.0,
        help="Delay between HOME and CALIBRATION command (default: 3.0)",
    )

    return parser.parse_args()


def load_config(path: Path) -> List[PrinterEntry]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    printers = []
    for item in data.get("printers", []):
        printers.append(
            PrinterEntry(
                id=int(item["id"]),
                name=str(item.get("name", f"printer-{item['id']}")),
                host=str(item["host"]),
                serial=str(item["serial"]),
                access_code=str(item["access_code"]),
                port=int(item.get("port", 8883)),
            )
        )
    return printers


def parse_printer_ids(raw: str) -> List[int]:
    return [int(chunk.strip()) for chunk in raw.split(",") if chunk.strip()]


def build_calibration_option(bed_leveling: bool, vibration: bool, motor_noise: bool) -> int:
    option = 0
    if bed_leveling:
        option |= BIT_BED_LEVELING
    if vibration:
        option |= BIT_VIBRATION
    if motor_noise:
        option |= BIT_MOTOR_NOISE
    return option


def send_payload(printer: BambuPrinter, serial: str, payload: dict) -> None:
    topic = f"device/{serial}/request"
    printer.client.publish(topic, json.dumps(payload))


def with_session(entry: PrinterEntry, connect_wait: float) -> BambuPrinter:
    cfg = BambuConfig(
        hostname=entry.host,
        access_code=entry.access_code,
        serial_number=entry.serial,
        mqtt_port=entry.port,
    )
    bp = BambuPrinter(config=cfg)
    bp.start_session()
    time.sleep(connect_wait)
    return bp


def cmd_list(printers: List[PrinterEntry]) -> int:
    if not printers:
        print("No printers in config.")
        return 1

    print("Configured printers:")
    for p in printers:
        print(f"  {p.id}: {p.name} ({p.host}, serial: {p.serial})")
    return 0


def select_printers(printers: List[PrinterEntry], requested_ids: List[int]) -> List[PrinterEntry]:
    by_id = {p.id: p for p in printers}
    missing = [pid for pid in requested_ids if pid not in by_id]
    if missing:
        raise ValueError(f"Unknown printer ID(s): {missing}")
    return [by_id[pid] for pid in requested_ids]


def cmd_home(args: argparse.Namespace, printers: List[PrinterEntry]) -> int:
    requested = parse_printer_ids(args.printers)
    targets = select_printers(printers, requested)

    home_payload = {"print": {"command": "home", "sequence_id": "1"}}

    for entry in targets:
        print(f"[{entry.id}] {entry.name}: HOME")
        if args.dry_run:
            print(json.dumps(home_payload))
            continue

        bp = None
        try:
            bp = with_session(entry, args.connect_wait)
            send_payload(bp, entry.serial, home_payload)
            time.sleep(args.post_wait)
            print(f"[{entry.id}] OK")
        except Exception as exc:
            print(f"[{entry.id}] FAILED: {exc}")
        finally:
            if bp is not None:
                try:
                    bp.quit()
                except Exception:
                    pass

    return 0


def cmd_calibrate(args: argparse.Namespace, printers: List[PrinterEntry]) -> int:
    requested = parse_printer_ids(args.printers)
    targets = select_printers(printers, requested)

    option = build_calibration_option(args.bed_leveling, args.vibration, args.motor_noise)

    if not args.home_only and option <= 0:
        print("Nothing to calibrate: choose at least one option or use --home-only.")
        return 1

    home_payload = {"print": {"command": "home", "sequence_id": "1"}}
    cal_payload = {"print": {"command": "calibration", "sequence_id": "2", "option": option}}

    for entry in targets:
        print(f"[{entry.id}] {entry.name}: HOME")
        if args.dry_run:
            print(json.dumps(home_payload))
            if not args.home_only:
                print(f"wait {args.calibration_delay}s")
                print(json.dumps(cal_payload))
            continue

        bp = None
        try:
            bp = with_session(entry, args.connect_wait)
            send_payload(bp, entry.serial, home_payload)

            if not args.home_only:
                time.sleep(args.calibration_delay)
                print(f"[{entry.id}] {entry.name}: CALIBRATION option={option}")
                send_payload(bp, entry.serial, cal_payload)

            time.sleep(args.post_wait)
            print(f"[{entry.id}] OK")
        except Exception as exc:
            print(f"[{entry.id}] FAILED: {exc}")
        finally:
            if bp is not None:
                try:
                    bp.quit()
                except Exception:
                    pass

    return 0


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)

    try:
        printers = load_config(config_path)
    except Exception as exc:
        print(f"Config error: {exc}")
        return 1

    try:
        if args.cmd == "list":
            return cmd_list(printers)
        if args.cmd == "home":
            return cmd_home(args, printers)
        if args.cmd == "calibrate":
            return cmd_calibrate(args, printers)
        print(f"Unknown command: {args.cmd}")
        return 1
    except Exception as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
