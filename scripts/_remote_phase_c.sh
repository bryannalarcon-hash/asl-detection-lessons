#!/usr/bin/env bash
# Phase C (remote): PopSign keypoint extraction -> Net 4 training -> e2e.
# Run inside the rented pod by scripts/launch_phase_c.sh. Assumes the trained
# checkpoints have been pushed to:
#   results/v3/net1_v3_1/best_export.pt  (Net 1, face+body)
#   results/v3/net2/best.pt              (Net 2, palm + wrist/MCP kpts)
#   results/v3/net3/best.pt              (Net 3, regression landmarks)
#
# Per sign: download tar -> extract -> clip manifest (cap clips) -> run the
# Net1/2/3 keypoint extractor -> rm raw video (peak disk ~5GB/sign). Then build
# the Net 4 manifest from the .npz cache and train the classifier.
set -uo pipefail
cd /workspace/asl
[ -f .remote_env ] && { set -a; . ./.remote_env; set +a; }
export PYTHONUNBUFFERED=1
mkdir -p logs work data/signs/popsign_kpt_cache

MAX_PER_SIGN="${MAX_PER_SIGN:-300}"
NET1=results/v3/net1_v3_1/best_export.pt
NET2=results/v3/net2/best.pt
NET3=results/v3/net3/best.pt
KPT_OUT=data/signs/popsign_kpt_cache
BASE="https://signdata.cc.gatech.edu/data/popsign_v1_0/game/train"

echo "[phasec] $(date -u) installing tools/deps"
apt-get update -qq >/dev/null 2>&1 || true
apt-get install -y -qq unzip wget curl >/dev/null 2>&1 || true
pip install -q -r requirements.txt
for f in "$NET1" "$NET2" "$NET3"; do
    [ -s "$f" ] || { echo "[phasec] FATAL missing checkpoint: $f"; exit 2; }
done

# Flatten the vocab to PopSign tar names (apply aliases).
mapfile -t SIGNS < <(python3 - <<'PY'
import json
d = json.load(open("configs/popsign_vocab.json"))
aliases = d.get("popsign_tar_aliases", {})
seen, out = set(), []
for signs in d["categories"].values():
    for s in signs:
        tar = aliases.get(s, s)
        if tar not in seen:
            seen.add(tar); out.append(tar)
print("\n".join(out))
PY
)
echo "[phasec] ${#SIGNS[@]} signs to extract (cap ${MAX_PER_SIGN}/sign)"

ok=0; miss=0
for sign in "${SIGNS[@]}"; do
    url="${BASE}/${sign}.tar"
    if ! curl -sfI --max-time 30 "$url" >/dev/null 2>&1; then
        echo "[phasec] MISS $sign (no tar at $url)"; miss=$((miss+1)); continue
    fi
    echo "[phasec] $(date -u) $sign : download"
    rm -rf "work/${sign}"
    tarf="work/${sign}.tar"
    # Download to a file with resume (-C -) + retries: PopSign tars are multi-GB
    # and a streamed "curl | tar" loses the whole sign on any mid-stream drop.
    if ! curl -sf -C - --retry 6 --retry-delay 5 --retry-all-errors \
            --max-time 3600 -o "$tarf" "$url" 2>>logs/phasec.log; then
        echo "[phasec] WARN $sign download failed after retries; skipping"; rm -f "$tarf"; continue
    fi
    if ! tar -xf "$tarf" -C work/ 2>>logs/phasec.log; then
        echo "[phasec] WARN $sign extract failed; skipping"; rm -rf "$tarf" "work/${sign}"; continue
    fi
    rm -f "$tarf"
    python3 scripts/build_clip_manifest.py --work-dir work --signs "$sign" \
        --out "work/${sign}.jsonl" --max-per-sign "$MAX_PER_SIGN" 2>&1 | tee -a logs/phasec.log
    python3 -m src.stage2.data.extract_keypoints \
        --manifest "work/${sign}.jsonl" --net1 "$NET1" --net2 "$NET2" --net3 "$NET3" \
        --out "$KPT_OUT" --max-frames 64 --delete-after 2>&1 | tee -a logs/extract.log
    rm -rf "work/${sign}" "work/${sign}.jsonl"
    ok=$((ok+1))
    echo "[phasec] $sign done ($ok ok / $miss miss); npz=$(ls "$KPT_OUT" | wc -l); df: $(df -h /workspace | awk 'NR==2{print $4" free"}')"
done

echo "[phasec] extraction complete: $ok signs, $(ls "$KPT_OUT" | wc -l) npz files"
echo "[phasec] building Net 4 manifest"
python3 -m src.stage2.data.build_manifest_popsign \
    --vocab configs/popsign_vocab.json --kpt-dir "$KPT_OUT" \
    --sign-list-out data/signs/popsign_sign_list.json \
    --manifest-out data/signs/popsign_manifest.jsonl \
    --val-frac 0.1 --test-frac 0.1 --seed 42 2>&1 | tee -a logs/phasec.log
touch .extract_done

echo "[phasec] $(date -u) training Net 4"
python3 -m src.stage2.train_v4_classifier \
    --config configs/stage2_v4_classifier_popsign.yaml 2>&1 | tee -a logs/train_net4.log
touch .net4_done
echo "[phasec] DONE $(date -u) — e2e pipeline trained"
