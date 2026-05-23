"""Plot per-epoch timing + target metric for Net 1 and Net 2.

Outputs:
  results/v3/training_curves.png  (4-panel: net1 time, net1 PCK, net2 time, net2 loss)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


REPO = Path(__file__).resolve().parents[1]


def load_jsonl(p: Path) -> list[dict]:
    with p.open() as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def main() -> None:
    n1_metrics = load_jsonl(REPO / "results/v3/net1/stage1_v2_facebody/metrics.jsonl")
    n2_metrics = load_jsonl(REPO / "results/v3/net2/metrics.jsonl")

    n1_epochs = [m["epoch"] for m in n1_metrics]
    n1_time = [m["epoch_secs"] for m in n1_metrics]
    n1_pck = [m.get("coco_val/pck_overall", 0.0) for m in n1_metrics]

    n2_epochs = [m["epoch"] for m in n2_metrics]
    n2_time = [m["epoch_secs"] for m in n2_metrics]
    n2_train = [m["train_loss"] for m in n2_metrics]
    n2_cls = [m["cls_loss"] for m in n2_metrics]
    n2_box = [m["box_loss"] for m in n2_metrics]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle("v3 training curves — time + target metrics", fontsize=14, fontweight="bold")

    # Net 1 — time per epoch
    ax = axes[0, 0]
    ax.plot(n1_epochs, n1_time, color="#2a6fdb", lw=1.5)
    ax.axhline(n1_time[0], color="#888", lw=0.8, ls="--", label=f"first epoch {n1_time[0]:.1f}s")
    ax.set_title(f"Net 1 — time per epoch  (mean {sum(n1_time)/len(n1_time):.1f}s, total {sum(n1_time)/60:.0f} min)")
    ax.set_xlabel("epoch")
    ax.set_ylabel("seconds")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Net 1 — PCK
    ax = axes[0, 1]
    ax.plot(n1_epochs, n1_pck, color="#16a34a", lw=1.5, label="coco_val pck_overall (sliced K=7)")
    ax.axhline(0.314, color="#888", lw=0.8, ls="--", label="v2 e79 baseline 0.314")
    best = max(n1_pck); best_e = n1_pck.index(best)
    ax.scatter([best_e], [best], color="#16a34a", zorder=5, s=50)
    ax.annotate(f"best {best:.3f} @ e{best_e}", xy=(best_e, best),
                xytext=(best_e - 25, best - 0.02),
                arrowprops=dict(arrowstyle="->", color="#16a34a"),
                fontsize=9)
    ax.set_title(f"Net 1 — coco_val PCK@0.05 (target ≥ 0.90 face/body)")
    ax.set_xlabel("epoch")
    ax.set_ylabel("PCK")
    ax.set_ylim(0, 1.0)
    ax.legend(loc="lower right", fontsize=9)
    ax.grid(True, alpha=0.3)

    # Net 2 — time per epoch
    ax = axes[1, 0]
    ax.plot(n2_epochs, n2_time, color="#2a6fdb", lw=1.5)
    ax.set_title(f"Net 2 — time per epoch  (mean {sum(n2_time)/len(n2_time):.1f}s, total {sum(n2_time)/60:.0f} min)")
    ax.set_xlabel("epoch")
    ax.set_ylabel("seconds")
    ax.grid(True, alpha=0.3)

    # Net 2 — loss breakdown
    ax = axes[1, 1]
    ax.plot(n2_epochs, n2_train, color="#16a34a", lw=1.5, label="train_loss (cls + box)")
    ax.plot(n2_epochs, n2_cls, color="#dc2626", lw=1.0, ls="--", label="cls_loss (focal)")
    ax.plot(n2_epochs, n2_box, color="#f59e0b", lw=1.0, ls="--", label="box_loss (smoothL1)")
    ax.set_title("Net 2 — training loss (target: palm AP@IoU=0.5 ≥ 0.85)")
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.set_yscale("log")
    ax.legend(loc="upper right", fontsize=9)
    ax.grid(True, alpha=0.3, which="both")

    plt.tight_layout()
    out_p = REPO / "results/v3/training_curves.png"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_p, dpi=120, bbox_inches="tight")
    print(f"saved → {out_p}")
    print(f"\nNet 1 summary:")
    print(f"  epochs:    {len(n1_metrics)}")
    print(f"  mean time: {sum(n1_time)/len(n1_time):.1f}s/epoch")
    print(f"  total:     {sum(n1_time)/60:.1f} min")
    print(f"  best pck:  {best:.4f} @ epoch {best_e}")
    print(f"  last pck:  {n1_pck[-1]:.4f}")
    print(f"\nNet 2 summary:")
    print(f"  epochs:    {len(n2_metrics)}")
    print(f"  mean time: {sum(n2_time)/len(n2_time):.1f}s/epoch")
    print(f"  total:     {sum(n2_time)/60:.1f} min")
    print(f"  final train_loss: {n2_train[-1]:.4f}")
    print(f"  final cls_loss:   {n2_cls[-1]:.4f}")
    print(f"  final box_loss:   {n2_box[-1]:.4f}")


if __name__ == "__main__":
    main()
