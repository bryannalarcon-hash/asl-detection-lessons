"""Build offline synthetic hand-in-scene composites for Net 2 training.

Net 2 fails on COCO body-scene hands because the training mix is HaGRID-dominated
(71%), with hands at 60-80 px. Real COCO hands are 10-30 px embedded in full-body
context. This script synthesizes a closing of that gap: FreiHAND hand crops
masked, scaled small, and feathered onto COCO non-person backgrounds.

Blending method: alpha-feather with multi-kernel gaussian (a 1-px erosion then
a 3-5 px gaussian on the binary mask). Picked over cv2.seamlessClone because
seamlessClone is brittle on tiny patches (<30 px) and requires a non-zero
gradient at the seam — for a 12-px hand on a flat sky background it produces
visible color shifts or fails outright. Soft-alpha feathering with sub-pixel
mask blur reliably blends the boundary without color-bleeding the small patch.

Output:
  data/synthetic_composites/img/{:08d}.png   256x256 RGB composites
  data/synthetic_composites/anno.jsonl       one JSON object per line
  data/synthetic_composites/preview/         first 20 composites for eyeballing

Annotation schema (per line):
  {
    "image_id": int,
    "image_path": "img/00000001.png",
    "bbox_xyxy": [x1, y1, x2, y2],   # pixel coords on the 256x256 canvas
    "side": "right",                  # FreiHAND is right-hand only by convention
    "frei_id": int,                   # source FreiHAND image index
    "coco_id": int,                   # source COCO image id
    "hand_bbox_px": float             # final scaled hand bbox edge length on canvas
  }

Usage:
  python -m scripts.build_synthetic_composites \\
      --frei-root data/FreiHAND_pub_v2 \\
      --coco-ann data/coco/annotations/coco_wholebody_train_v1.0.json \\
      --coco-img data/coco/images/train2017 \\
      --out data/synthetic_composites \\
      --n 50000
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import cv2
import numpy as np

cv2.setNumThreads(1)
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")


CANVAS_SIZE = 256
HAND_PX_MIN = 10
HAND_PX_MAX = 30
HAND_PX_MODE = 15
EDGE_MARGIN = 5
PREVIEW_COUNT = 20


# ---------- COCO non-person filter ----------------------------------------

def collect_no_person_coco_ids(coco_ann_path: Path) -> list[int]:
    """Return COCO image ids that contain ZERO person-category annotations.

    Person is category_id == 1 in the COCO instances schema. The wholebody
    annotation file extends the same image set; non-person images are those
    whose annotation list has no entry with category_id == 1.
    """
    with coco_ann_path.open() as f:
        data = json.load(f)
    images_by_id = {img["id"]: img for img in data["images"]}
    has_person: set[int] = set()
    for ann in data["annotations"]:
        if ann.get("category_id", 1) == 1:
            has_person.add(ann["image_id"])
    no_person = sorted(set(images_by_id.keys()) - has_person)
    return no_person


def collect_no_person_from_instances(instances_path: Path) -> list[int]:
    """Same as above but for the standard COCO instances_train2017.json file.

    Use this if the wholebody file only contains person annotations (which is
    typical — wholebody is a person-only extension). The instances file has
    the full 80-category annotation set we need for the negative filter.
    """
    with instances_path.open() as f:
        data = json.load(f)
    images_by_id = {img["id"]: img for img in data["images"]}
    has_person: set[int] = set()
    for ann in data["annotations"]:
        if ann.get("category_id", 1) == 1:
            has_person.add(ann["image_id"])
    return sorted(set(images_by_id.keys()) - has_person), images_by_id


# ---------- FreiHAND mask + image loading ---------------------------------

def load_frei_image_and_mask(frei_root: Path, frei_id: int) -> tuple[np.ndarray, np.ndarray] | None:
    """Load a FreiHAND rgb image and its binary mask.

    FreiHAND v2 stores 4 background variants per scene (variants 1-3 are
    composited; variant 0 is original green-screen). The mask is only valid
    for the green-screen pose (variant 0), but applies to all 4 variants
    because the hand pose is identical across variants — only the background
    differs. So mask path uses `frei_id mod num_scenes`.
    """
    img_path = frei_root / "training" / "rgb" / f"{frei_id:08d}.jpg"
    if not img_path.exists():
        return None
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # FreiHAND v2 has 32560 unique scenes, 4 variants each.
    scene_id = frei_id % 32560
    mask_path = frei_root / "training" / "mask" / f"{scene_id:08d}.jpg"
    if not mask_path.exists():
        return None
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return None
    if mask.shape[:2] != img.shape[:2]:
        mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
    return img, mask


def crop_to_hand(img: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Tight-crop the image+mask to the hand mask bounding box, with 2-px margin."""
    ys, xs = np.where(mask > 64)
    if ys.size == 0 or xs.size == 0:
        return None
    y0, y1 = int(ys.min()), int(ys.max())
    x0, x1 = int(xs.min()), int(xs.max())
    pad = 2
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(img.shape[0] - 1, y1 + pad)
    x1 = min(img.shape[1] - 1, x1 + pad)
    if (y1 - y0) < 4 or (x1 - x0) < 4:
        return None
    return img[y0:y1 + 1, x0:x1 + 1].copy(), mask[y0:y1 + 1, x0:x1 + 1].copy()


# ---------- Compositing ---------------------------------------------------

def sample_hand_target_px(rng: random.Random) -> int:
    """Triangular distribution peaked at HAND_PX_MODE within [HAND_PX_MIN, HAND_PX_MAX].

    Matches the observed COCO val hand-size mode (15 px) better than a flat
    uniform; tails still cover the full 10-30 range.
    """
    return int(round(rng.triangular(HAND_PX_MIN, HAND_PX_MAX, HAND_PX_MODE)))


def scale_hand_to_target(hand_rgb: np.ndarray, hand_mask: np.ndarray,
                         target_px: int) -> tuple[np.ndarray, np.ndarray]:
    """Scale the hand crop so its longer side equals target_px."""
    h, w = hand_rgb.shape[:2]
    longer = max(h, w)
    scale = target_px / float(longer)
    new_h = max(1, int(round(h * scale)))
    new_w = max(1, int(round(w * scale)))
    rgb_s = cv2.resize(hand_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
    mask_s = cv2.resize(hand_mask, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return rgb_s, mask_s


def feather_mask(mask: np.ndarray, rng: random.Random) -> np.ndarray:
    """Produce a soft alpha map in [0, 1] from a binary mask.

    Two-step: 1-px erosion to retreat slightly inside the true boundary,
    then a 3-5 px gaussian blur to feather. Result is a continuous alpha in
    [0, 1] that smoothly transitions from full hand to full background at
    the boundary — eliminates the high-frequency edge that detectors would
    otherwise lock onto as a shortcut.
    """
    binary = (mask > 64).astype(np.uint8) * 255
    erosion_kernel = np.ones((3, 3), np.uint8)
    eroded = cv2.erode(binary, erosion_kernel, iterations=1)
    blur_k = rng.choice([3, 5])
    blurred = cv2.GaussianBlur(eroded, (blur_k, blur_k), 0)
    alpha = blurred.astype(np.float32) / 255.0
    return alpha


def letterbox_bg(bg_rgb: np.ndarray, size: int) -> np.ndarray:
    """Resize a background image to fit `size x size` with center-letterbox padding."""
    h, w = bg_rgb.shape[:2]
    scale = size / max(h, w)
    new_h = max(1, int(round(h * scale)))
    new_w = max(1, int(round(w * scale)))
    resized = cv2.resize(bg_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    dy = (size - new_h) // 2
    dx = (size - new_w) // 2
    canvas[dy:dy + new_h, dx:dx + new_w] = resized
    return canvas


def paste_with_alpha(canvas: np.ndarray, patch_rgb: np.ndarray, alpha: np.ndarray,
                     x: int, y: int) -> tuple[int, int, int, int]:
    """Alpha-blend `patch_rgb` onto `canvas` at top-left (x, y). Returns bbox xyxy.

    Assumes patch fits fully inside canvas (caller responsible for clamping).
    """
    h, w = patch_rgb.shape[:2]
    region = canvas[y:y + h, x:x + w].astype(np.float32)
    patch_f = patch_rgb.astype(np.float32)
    alpha3 = alpha[..., None]
    blended = region * (1.0 - alpha3) + patch_f * alpha3
    canvas[y:y + h, x:x + w] = np.clip(blended, 0, 255).astype(np.uint8)
    # Tight bbox = the alpha>0.1 region inside the placement.
    ys, xs = np.where(alpha > 0.1)
    if ys.size == 0:
        return x, y, x + w, y + h
    bb_x0 = x + int(xs.min())
    bb_y0 = y + int(ys.min())
    bb_x1 = x + int(xs.max()) + 1
    bb_y1 = y + int(ys.max()) + 1
    return bb_x0, bb_y0, bb_x1, bb_y1


def synthesize_one(frei_root: Path, frei_id: int,
                   bg_img_path: Path, coco_id: int,
                   rng: random.Random) -> tuple[np.ndarray, dict] | None:
    """Build a single composite. Returns (rgb_uint8_HxWx3, anno_dict) or None on failure."""
    pair = load_frei_image_and_mask(frei_root, frei_id)
    if pair is None:
        return None
    hand_rgb, hand_mask = pair
    cropped = crop_to_hand(hand_rgb, hand_mask)
    if cropped is None:
        return None
    hand_c_rgb, hand_c_mask = cropped

    target_px = sample_hand_target_px(rng)
    hand_s_rgb, hand_s_mask = scale_hand_to_target(hand_c_rgb, hand_c_mask, target_px)
    alpha = feather_mask(hand_s_mask, rng)

    bg = cv2.imread(str(bg_img_path))
    if bg is None:
        return None
    bg = cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)
    canvas = letterbox_bg(bg, CANVAS_SIZE)

    ph, pw = hand_s_rgb.shape[:2]
    if ph >= CANVAS_SIZE - 2 * EDGE_MARGIN or pw >= CANVAS_SIZE - 2 * EDGE_MARGIN:
        return None
    x = rng.randint(EDGE_MARGIN, CANVAS_SIZE - EDGE_MARGIN - pw)
    y = rng.randint(EDGE_MARGIN, CANVAS_SIZE - EDGE_MARGIN - ph)

    bbox = paste_with_alpha(canvas, hand_s_rgb, alpha, x, y)
    x1, y1, x2, y2 = bbox
    if (x2 - x1) < 4 or (y2 - y1) < 4:
        return None

    anno = {
        "bbox_xyxy": [int(x1), int(y1), int(x2), int(y2)],
        "side": "right",
        "frei_id": int(frei_id),
        "coco_id": int(coco_id),
        "hand_bbox_px": float(max(x2 - x1, y2 - y1)),
        "target_px": int(target_px),
    }
    return canvas, anno


# ---------- Worker entry point --------------------------------------------

_WORKER_CTX: dict = {}


def _worker_init(frei_root_str: str, coco_img_root_str: str, seed_base: int):
    _WORKER_CTX["frei_root"] = Path(frei_root_str)
    _WORKER_CTX["coco_img_root"] = Path(coco_img_root_str)
    _WORKER_CTX["rng"] = random.Random(seed_base + os.getpid())


def _worker_synthesize(task: dict) -> dict | None:
    rng: random.Random = _WORKER_CTX["rng"]
    frei_root: Path = _WORKER_CTX["frei_root"]
    coco_img_root: Path = _WORKER_CTX["coco_img_root"]

    bg_path = coco_img_root / task["coco_file"]
    result = synthesize_one(frei_root, task["frei_id"], bg_path, task["coco_id"], rng)
    if result is None:
        return None
    canvas, anno = result

    out_img = Path(task["out_img"])
    out_img.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_img), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))

    anno["image_id"] = task["image_id"]
    anno["image_path"] = task["image_rel"]
    return anno


# ---------- Driver --------------------------------------------------------

def build_tasks(n: int, frei_max: int, no_person_ids: list[int],
                images_by_id: dict, out_dir: Path, seed: int) -> list[dict]:
    rng = random.Random(seed)
    tasks: list[dict] = []
    for i in range(n):
        frei_id = rng.randint(0, frei_max - 1)
        coco_id = rng.choice(no_person_ids)
        coco_file = images_by_id[coco_id]["file_name"]
        image_rel = f"img/{i:08d}.png"
        tasks.append({
            "image_id": i,
            "frei_id": frei_id,
            "coco_id": coco_id,
            "coco_file": coco_file,
            "out_img": str(out_dir / image_rel),
            "image_rel": image_rel,
        })
    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frei-root", required=True, type=Path,
                        help="FreiHAND v2 root (contains training/rgb/, training/mask/)")
    parser.add_argument("--coco-ann", required=True, type=Path,
                        help="COCO instances_train2017.json (for non-person filter)")
    parser.add_argument("--coco-img", required=True, type=Path,
                        help="COCO images dir (e.g. train2017/)")
    parser.add_argument("--out", required=True, type=Path,
                        help="Output dir (creates img/, preview/, anno.jsonl)")
    parser.add_argument("--n", type=int, default=50000, help="Number of composites")
    parser.add_argument("--frei-max", type=int, default=130240,
                        help="Max FreiHAND image index (130240 = full v2 with 4 variants)")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = args.out
    (out / "img").mkdir(parents=True, exist_ok=True)
    (out / "preview").mkdir(parents=True, exist_ok=True)

    print(f"[{time.strftime('%H:%M:%S')}] loading COCO instances annotation...")
    no_person_ids, images_by_id = collect_no_person_from_instances(args.coco_ann)
    print(f"  found {len(no_person_ids):,} non-person COCO images")
    if not no_person_ids:
        raise SystemExit("no non-person COCO images found — check --coco-ann path")

    print(f"[{time.strftime('%H:%M:%S')}] building {args.n:,} tasks...")
    tasks = build_tasks(args.n, args.frei_max, no_person_ids, images_by_id, out, args.seed)

    anno_path = out / "anno.jsonl"
    successes = 0
    failures = 0
    preview_saved = 0
    t0 = time.time()

    with anno_path.open("w") as anno_f, ProcessPoolExecutor(
        max_workers=args.workers,
        initializer=_worker_init,
        initargs=(str(args.frei_root), str(args.coco_img), args.seed),
    ) as pool:
        for i, anno in enumerate(pool.map(_worker_synthesize, tasks, chunksize=16)):
            if anno is None:
                failures += 1
                continue
            successes += 1
            anno_f.write(json.dumps(anno) + "\n")
            if preview_saved < PREVIEW_COUNT:
                src = out / anno["image_path"]
                dst = out / "preview" / f"{preview_saved:02d}_{src.name}"
                if src.exists():
                    img = cv2.imread(str(src))
                    if img is not None:
                        x1, y1, x2, y2 = anno["bbox_xyxy"]
                        annotated = img.copy()
                        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 1)
                        cv2.imwrite(str(dst), annotated)
                        preview_saved += 1
            if (i + 1) % 1000 == 0:
                dt = time.time() - t0
                rate = (i + 1) / dt
                eta = (len(tasks) - (i + 1)) / max(rate, 1e-6)
                print(f"  {i+1:,}/{len(tasks):,}  ok={successes}  fail={failures}  "
                      f"rate={rate:.1f}/s  eta={eta/60:.1f}m")

    dt = time.time() - t0
    print(f"\n[{time.strftime('%H:%M:%S')}] DONE  ok={successes:,}  fail={failures:,}  "
          f"elapsed={dt/60:.2f}m  rate={successes/dt:.1f}/s")
    print(f"  composites:  {out/'img'}")
    print(f"  annotations: {anno_path}")
    print(f"  previews:    {out/'preview'}  ({preview_saved} files)")


if __name__ == "__main__":
    main()
