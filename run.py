"""Run the Order-image flow against the open Fakturama application.

Examples:
    python run.py samples/order_northstar.png
    python run.py samples/order_northstar.png --from-step 2.10
    python run.py samples/order_northstar.png --dry-run
    python run.py --probe
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fakturama_auto import ax, screen  # noqa: E402
from fakturama_auto.flow import run  # noqa: E402


def probe() -> None:
    app = ax.activate()
    print("tabs:", ax.tab_titles(app), flush=True)
    print("windows:", [ax.title(window) for window in ax.windows(app)], flush=True)
    path = screen.capture("probe", "Current Fakturama state")
    text = screen.visible_text()
    print(text[:2500], flush=True)
    print(f"full screenshot: {path}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fakturama image-to-cash automation")
    parser.add_argument("image", nargs="?", help="Order image to extract and post")
    parser.add_argument("--from-step", default="1.3", help="PDF step to resume at (1.3, 2.1, 2.5, 2.10, 2.11, 3.1, 4.1, 4.5, 5.1)")
    parser.add_argument("--dry-run", action="store_true", help="Fill records but do not save them")
    parser.add_argument("--probe", action="store_true", help="Screenshot Fakturama and print what is open")
    args = parser.parse_args()
    if args.probe:
        probe()
        return
    if not args.image:
        parser.error("an order image is required unless --probe is used")
    run(Path(args.image), from_step=args.from_step, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
