"""Tear down the vast.ai instance once Stage 1 is complete.

  python scripts/destroy_instance.py --instance-id 37252447 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--instance-id", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    api = os.environ.get("VAST_API")
    if not api:
        raise SystemExit("VAST_API env var not set. Source .env.local first.")

    # Confirm current state before destroying.
    req = urllib.request.Request(
        f"https://console.vast.ai/api/v0/instances/{args.instance_id}/",
        headers={"Authorization": f"Bearer {api}"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    state = data.get("actual_status") or data.get("cur_state")
    spend = data.get("client_run_time", 0) * data.get("dph_total", 0)
    print(f"[destroy] instance {args.instance_id} state={state} "
          f"approx-spend=${spend:.2f}")

    if args.dry_run:
        print("[destroy] --dry-run, not destroying")
        return

    req = urllib.request.Request(
        f"https://console.vast.ai/api/v0/instances/{args.instance_id}/",
        headers={"Authorization": f"Bearer {api}"},
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req) as r:
            print(r.read().decode())
        print(f"[destroy] instance {args.instance_id} destroyed")
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode())


if __name__ == "__main__":
    main()
