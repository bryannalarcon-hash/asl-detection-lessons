"""RunPod provisioning helper (GraphQL) for the v3 training rounds.

Reads RUNPOD_API from .env.local. Subcommands:

  python3 scripts/runpod_provision.py offers          # list 5090 availability + price
  python3 scripts/runpod_provision.py balance         # account balance
  python3 scripts/runpod_provision.py deploy [--gpu "NVIDIA GeForce RTX 5090"] \
        [--disk 220] [--image pytorch/pytorch:2.7.0-cuda12.8-cudnn9-devel] \
        [--pubkey ~/.ssh/vast_v3.pub] [--name asl-train]
  python3 scripts/runpod_provision.py ssh <podId>     # print "host port" once SSH is up
  python3 scripts/runpod_provision.py status <podId>
  python3 scripts/runpod_provision.py destroy <podId>

`deploy` prints the podId on stdout (last line) so a launcher can capture it.
SSH key is injected via the PUBLIC_KEY env var, which the runpod/pytorch image
writes into /root/.ssh/authorized_keys on boot. SSH in with:
  ssh -i ~/.ssh/vast_v3 -o IdentitiesOnly=yes -p <port> root@<host>

Community 5090 is ~$0.69/hr. Always destroy when done — the launcher traps EXIT.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

API_BASE = "https://api.runpod.io/graphql"


def _load_api_key() -> str:
    key = os.environ.get("RUNPOD_API", "")
    if not key:
        env = Path(__file__).resolve().parents[1] / ".env.local"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("RUNPOD_API="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        sys.exit("RUNPOD_API not set (env or .env.local)")
    return key


def _gql(query: str, api_key: str, timeout: int = 40) -> dict:
    body = json.dumps({"query": query}).encode()
    req = urllib.request.Request(
        f"{API_BASE}?api_key={api_key}",
        data=body,
        headers={"Content-Type": "application/json",
                 "User-Agent": "curl/8.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read().decode())
    if "errors" in out:
        raise RuntimeError(json.dumps(out["errors"], indent=2))
    return out["data"]


def cmd_balance(api_key: str) -> None:
    d = _gql("query { myself { clientBalance } }", api_key)
    print(f"balance: ${d['myself']['clientBalance']:.2f}")


def cmd_offers(api_key: str, gpu: str) -> None:
    # gpuTypes(input) returns the catalog; lowestPrice needs an availability input.
    q = (
        'query { gpuTypes { id displayName memoryInGb '
        'secureCloud communityCloud '
        'lowestPrice(input: {gpuCount: 1}) { '
        'minimumBidPrice uninterruptablePrice } } }'
    )
    d = _gql(q, api_key)
    rows = [g for g in d["gpuTypes"]
            if gpu.lower() in (g["displayName"] or "").lower()
            or gpu.lower() in (g["id"] or "").lower()]
    if not rows:
        rows = d["gpuTypes"]
    for g in sorted(rows, key=lambda x: (x["lowestPrice"] or {}).get(
            "uninterruptablePrice") or 9.99):
        lp = g.get("lowestPrice") or {}
        print(f"  id={g['id']!r}  {g['displayName']}  {g['memoryInGb']}GB  "
              f"community={g['communityCloud']}  "
              f"onDemand=${lp.get('uninterruptablePrice')}  "
              f"spot=${lp.get('minimumBidPrice')}")


def cmd_deploy(api_key: str, gpu: str, disk: int, image: str,
               pubkey_path: str, name: str, community: bool) -> None:
    pub = Path(os.path.expanduser(pubkey_path)).read_text().strip()
    cloud = "COMMUNITY" if community else "SECURE"
    # GraphQL string-escape the key (it has spaces + slashes but no quotes).
    env_block = f'[{{key: "PUBLIC_KEY", value: "{pub}"}}]'
    q = (
        'mutation { podFindAndDeployOnDemand(input: {'
        f'cloudType: {cloud}, gpuCount: 1, '
        f'gpuTypeId: "{gpu}", '
        f'name: "{name}", '
        f'imageName: "{image}", '
        f'containerDiskInGb: {disk}, volumeInGb: 0, '
        'ports: "22/tcp", '
        'dockerArgs: "", '
        f'env: {env_block}'
        '}) { id machineId desiredStatus } }'
    )
    d = _gql(q, api_key)
    pod = d["podFindAndDeployOnDemand"]
    if not pod:
        sys.exit("deploy returned null — no capacity for that GPU/cloud combo")
    print(f"[deploy] pod {pod['id']} status={pod['desiredStatus']}",
          file=sys.stderr)
    print(pod["id"])


def _pod_ssh(api_key: str, pod_id: str) -> tuple[str, str] | None:
    q = ('query { pod(input: {podId: "' + pod_id + '"}) { '
         'desiredStatus runtime { ports { ip isIpPublic privatePort '
         'publicPort type } } } }')
    d = _gql(q, api_key)
    pod = d.get("pod") or {}
    rt = pod.get("runtime") or {}
    for p in (rt.get("ports") or []):
        if p.get("privatePort") == 22 and p.get("type") == "tcp" and p.get("isIpPublic"):
            return str(p["ip"]), str(p["publicPort"])
    return None


def cmd_ssh(api_key: str, pod_id: str, wait_s: int = 600) -> None:
    deadline = time.time() + wait_s
    while time.time() < deadline:
        hp = _pod_ssh(api_key, pod_id)
        if hp:
            print(f"{hp[0]} {hp[1]}")
            return
        time.sleep(10)
    sys.exit("ssh endpoint never came up")


def cmd_status(api_key: str, pod_id: str) -> None:
    q = ('query { pod(input: {podId: "' + pod_id + '"}) { '
         'id name desiredStatus lastStatusChange '
         'runtime { uptimeInSeconds } } }')
    print(json.dumps(_gql(q, api_key), indent=2))


def cmd_destroy(api_key: str, pod_id: str) -> None:
    q = 'mutation { podTerminate(input: {podId: "' + pod_id + '"}) }'
    _gql(q, api_key)
    print(f"[destroy] terminated {pod_id}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("balance")
    po = sub.add_parser("offers")
    po.add_argument("--gpu", default="RTX 5090")
    pd = sub.add_parser("deploy")
    pd.add_argument("--gpu", default="NVIDIA GeForce RTX 5090")
    pd.add_argument("--disk", type=int, default=220)
    pd.add_argument("--image",
                    default="runpod/pytorch:2.8.0-py3.11-cuda12.8.1-cudnn-devel-ubuntu22.04")
    pd.add_argument("--pubkey", default="~/.ssh/vast_v3.pub")
    pd.add_argument("--name", default="asl-train")
    pd.add_argument("--secure", action="store_true", help="use SECURE cloud (pricier)")
    for c in ("ssh", "status", "destroy"):
        sp = sub.add_parser(c)
        sp.add_argument("pod_id")
    args = ap.parse_args()
    api_key = _load_api_key()

    if args.cmd == "balance":
        cmd_balance(api_key)
    elif args.cmd == "offers":
        cmd_offers(api_key, args.gpu)
    elif args.cmd == "deploy":
        cmd_deploy(api_key, args.gpu, args.disk, args.image, args.pubkey,
                   args.name, community=not args.secure)
    elif args.cmd == "ssh":
        cmd_ssh(api_key, args.pod_id)
    elif args.cmd == "status":
        cmd_status(api_key, args.pod_id)
    elif args.cmd == "destroy":
        cmd_destroy(api_key, args.pod_id)


if __name__ == "__main__":
    main()
