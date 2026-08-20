"""Generate QR codes for mall app locations, encoding a URL per location.

Usage:
    python locations/generate_qr.py --ip 192.168.1.50 [--port 5000]
    python locations/generate_qr.py --base-url https://your-tunnel.ngrok-free.dev
"""

import argparse
from pathlib import Path

import qrcode

from locations import LOCATIONS

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "static" / "qrcodes"


def generate_qr_codes(base_url: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base_url = base_url.rstrip("/")

    for name in LOCATIONS:
        url = f"{base_url}/location/{name}"
        img = qrcode.make(url)

        out_path = OUTPUT_DIR / f"{name}.png"
        img.save(out_path)
        print(f"Saved {out_path} -> {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", help="Host/IP the app is served on")
    parser.add_argument("--port", type=int, default=5000, help="Port the app is served on")
    parser.add_argument("--base-url", help="Full base URL (e.g. an ngrok tunnel), overrides --ip/--port")
    args = parser.parse_args()

    if args.base_url:
        base_url = args.base_url
    elif args.ip:
        base_url = f"http://{args.ip}:{args.port}"
    else:
        parser.error("either --base-url or --ip is required")

    generate_qr_codes(base_url)


if __name__ == "__main__":
    main()
