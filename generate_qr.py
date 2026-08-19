"""Generate QR codes for mall app locations, encoding a URL per location.

Usage:
    python locations/generate_qr.py --ip 192.168.1.50 [--port 5000]
"""

import argparse
from pathlib import Path

import qrcode

from locations import LOCATIONS

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "static" / "qrcodes"


def generate_qr_codes(ip: str, port: int) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for name in LOCATIONS:
        url = f"http://{ip}:{port}/location/{name}"
        img = qrcode.make(url)

        out_path = OUTPUT_DIR / f"{name}.png"
        img.save(out_path)
        print(f"Saved {out_path} -> {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True, help="Host/IP the app is served on")
    parser.add_argument("--port", type=int, default=5000, help="Port the app is served on")
    args = parser.parse_args()

    generate_qr_codes(args.ip, args.port)


if __name__ == "__main__":
    main()
