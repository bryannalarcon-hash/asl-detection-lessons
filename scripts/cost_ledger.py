"""Cost ledger updater for AWS, Vast, Modal.

Schema: ts, provider, balance_usd, spent_since_prev_usd, mtd_usd, source, note

- balance_usd:           remaining credit (estimated for AWS/Modal)
- spent_since_prev_usd:  delta of balance vs previous row for this provider
- mtd_usd:               month-to-date spend reported by source (for delta math)
- source:                live / stale / manual

Providers:
  vast   -> vastai CLI (vastai show user --raw); reports credit directly.
  modal  -> modal billing report --for "this month"; sums Cost column.
  aws    -> boto3 Cost Explorer (requires ce:GetCostAndUsage IAM perm).

Each call writes ONE row per provider. Falls back gracefully when a source
isn't reachable, copying the previous balance + marking source=stale.

Usage:
    python3 -m scripts.cost_ledger                  # all providers
    python3 -m scripts.cost_ledger --provider aws   # one provider
    python3 -m scripts.cost_ledger --note "post Net 2 v3.1"
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

LEDGER = Path(__file__).resolve().parent.parent / "costs" / "ledger.csv"
FIELDS = ["ts", "provider", "balance_usd", "spent_since_prev_usd", "mtd_usd", "source", "note"]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_rows() -> list[dict]:
    if not LEDGER.exists():
        return []
    with LEDGER.open() as f:
        return list(csv.DictReader(f))


def last_row(provider: str, rows: list[dict] | None = None) -> dict | None:
    rows = rows if rows is not None else read_rows()
    last = None
    for r in rows:
        if r["provider"] == provider:
            last = r
    return last


def fetch_vast() -> tuple[float | None, float | None, str]:
    """Returns (balance, mtd, source). mtd is None for Vast (computed from delta)."""
    try:
        out = subprocess.run(
            ["vastai", "show", "user", "--raw"],
            capture_output=True, text=True, timeout=15, check=True,
        ).stdout
        data = json.loads(out)
        return float(data["credit"]), None, "vast-cli"
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
        return None, None, "stale"


def _parse_modal_total(stdout: str) -> float:
    total = 0.0
    for line in stdout.splitlines():
        m = re.search(r"│\s+([0-9]+\.[0-9]+)\s+│\s*$", line)
        if m:
            total += float(m.group(1))
    return total


def fetch_modal(prev: dict | None) -> tuple[float | None, float | None, str]:
    """Modal billing report sums month-to-date spend.

    balance_now = prev.balance - (mtd_now - prev.mtd)
    """
    try:
        out = subprocess.run(
            ["modal", "billing", "report", "--for", "this month"],
            capture_output=True, text=True, timeout=20, check=True,
        ).stdout
        mtd = _parse_modal_total(out)
        if prev is None:
            return None, mtd, "modal-cli(no-prior-balance)"
        prev_balance = float(prev["balance_usd"])
        prev_mtd = float(prev.get("mtd_usd") or 0.0)
        delta = mtd - prev_mtd
        return prev_balance - delta, mtd, "modal-cli"
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None, "stale"


def fetch_aws(prev: dict | None) -> tuple[float | None, float | None, str]:
    """AWS Cost Explorer for MTD spend (needs ce:GetCostAndUsage)."""
    try:
        import boto3  # type: ignore
        ce = boto3.client("ce", region_name="us-east-1")
        today = dt.date.today()
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": today.replace(day=1).isoformat(),
                        "End": (today + dt.timedelta(days=1)).isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        mtd = float(resp["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"])
        if prev is None:
            return None, mtd, "aws-ce(no-prior-balance)"
        prev_balance = float(prev["balance_usd"])
        prev_mtd = float(prev.get("mtd_usd") or 0.0)
        delta = mtd - prev_mtd
        return prev_balance - delta, mtd, "aws-ce"
    except Exception as e:
        msg = str(e).split("\n", 1)[0][:60]
        return None, None, f"stale({msg})"


def update_one(provider: str, note: str, rows: list[dict]) -> None:
    prev = last_row(provider, rows)
    if provider == "vast":
        balance, mtd, source = fetch_vast()
    elif provider == "modal":
        balance, mtd, source = fetch_modal(prev)
    elif provider == "aws":
        balance, mtd, source = fetch_aws(prev)
    else:
        raise ValueError(provider)

    if balance is None:
        if prev is None:
            print(f"[{provider}] no prior balance and fetch failed; skipping.")
            return
        balance = float(prev["balance_usd"])
        mtd = float(prev.get("mtd_usd") or 0.0) if mtd is None else mtd
        source = source if "stale" in source else f"stale({source})"
    if mtd is None:
        mtd = float(prev["mtd_usd"]) if prev and prev.get("mtd_usd") else 0.0

    prev_balance = float(prev["balance_usd"]) if prev else balance
    delta = balance - prev_balance
    row = {
        "ts": now_iso(),
        "provider": provider,
        "balance_usd": f"{balance:.2f}",
        "spent_since_prev_usd": f"{-delta:.2f}",  # positive = spent
        "mtd_usd": f"{mtd:.2f}",
        "source": source,
        "note": note,
    }
    write_header = not LEDGER.exists()
    with LEDGER.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)
    print(f"[{provider:5s}] balance ${balance:7.2f}  spent ${-delta:+.2f}  mtd ${mtd:6.2f}  src={source}")


def total_remaining(rows: list[dict]) -> None:
    by_provider = {}
    for p in ("vast", "modal", "aws"):
        r = last_row(p, rows)
        if r:
            by_provider[p] = float(r["balance_usd"])
    print("---")
    for p, b in by_provider.items():
        print(f"  {p:5s}: ${b:8.2f}")
    print(f"  TOTAL: ${sum(by_provider.values()):8.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("vast", "modal", "aws"))
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    targets = [args.provider] if args.provider else ["vast", "modal", "aws"]
    for p in targets:
        update_one(p, args.note, read_rows())
    total_remaining(read_rows())


if __name__ == "__main__":
    main()
