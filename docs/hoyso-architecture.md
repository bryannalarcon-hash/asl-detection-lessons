# Hoyso48 ISLR Architecture — Reference Notes

Reference for the model architecture we're adapting. Original source: 1st place solution to the Google Isolated Sign Language Recognition (ISLR) Kaggle competition, 2023, by hoyso48.

## Why this is our reference

- **Closest task match**: isolated sign classification (not fingerspelling).
- **From-scratch friendly**: trained without pretrained weights → compatible with Req 7.
- **Small**: ~1.85M params per model → realistic for browser inference.
- **Hybrid temporal stack**: Conv1D captures local motion, Transformer captures long-range timing.
- **Result**: CV 0.80, public LB 0.80, private LB 0.88 on ~250 classes.

## Architecture at a glance

```
Input (T=64 frames, C=CHANNELS per frame)
  │
  ├─ Masking(PAD)                                 # variable-length support
  ├─ Dense(192, no bias)  ─ "stem_conv"
  ├─ BatchNorm(momentum=0.95) ─ "stem_bn"
  │
  ├─ 3× Conv1DBlock(dim=192, kernel=17, dr=0.2)   # local temporal
  ├─ 1× TransformerBlock(dim=192, expand=2)       # global temporal
  ├─ 3× Conv1DBlock(dim=192, kernel=17, dr=0.2)
  ├─ 1× TransformerBlock(dim=192, expand=2)
  │
  ├─ Dense(384) ─ "top_conv"
  ├─ GlobalAveragePooling1D
  ├─ LateDropout(p=0.8, start_step=...)
  └─ Dense(NUM_CLASSES) ─ "classifier"
```

Total: ~1.85M params. Ensembled across 4 seeds at inference (prob average).

## Block details

**Conv1DBlock**
- Depthwise-separable Conv1D, **causal padding** (keeps lag features aligned in time)
- GELU activation
- Residual connection
- DropPath regularization

**TransformerBlock**
- Pre-norm
- Multi-head self-attention (4 heads)
- MLP with 2× expansion (Dense → GELU → Dense)
- Residual, DropPath

**LateDropout**
- Dropout that activates only after a configured `start_step`.
- Lets the model fit aggressively early, then heavily regularizes (p=0.8) once it starts to memorize.

## Per-frame feature vector (their version)

For each of T=64 frames, concatenate:
- Selected landmark coordinates (x, y, z) — subset of hand + pose + lips
- **Lag-1 motion**: `frame[t] − frame[t-1]`
- **Lag-2 motion**: `frame[t] − frame[t-2]`

Resulting vector has CHANNELS dims. PAD value is used for masked positions.

## Training recipe

| Component       | Setting                                          |
| --------------- | ------------------------------------------------ |
| Optimizer       | RAdam + Lookahead                                |
| LR schedule     | Cosine decay                                     |
| Precision       | fp16 mixed                                       |
| Regularization  | DropPath, LateDropout (p=0.8, late start)        |
| Robustness      | AWP (Adversarial Weight Perturbation, λ=0.2)     |
| Sequence length | Variable, max_len=64, masked                     |
| Validation      | Signer-stratified k-fold (no signer leakage)     |
| Ensemble        | 4 seeds, probability average                     |
| Hardware/time   | TPUv2-8, ~4 hours                                |

## How we adapt it for the pilot

| Their setup                          | Ours                                                                          |
| ------------------------------------ | ----------------------------------------------------------------------------- |
| MediaPipe landmarks per frame        | Small from-scratch CNN frame encoder on cropped RGB hand ROI (Req 7)          |
| ~250 classes                         | 75–100 classes                                                                |
| Public Kaggle ISLR dataset           | 10–15k self-collected labeled clips, controlled framing (Req 8)               |
| TPUv2-8                              | Rented 4090 / A100 on vast.ai                                                 |
| —                                    | Optional Tier 2: SSL pretraining (masked frame / temporal contrastive)        |

**The temporal stack stays.** Conv1D × 6 + Transformer × 2 + LateDropout + AWP is doing the work, and it's independent of where per-frame features come from. We swap **only the front end**:

```
Webcam frame
  → classical ROI finder (skin YCbCr + frame diff + bg subtract)
  → crop 112×112
  → CNN frame encoder (~500K params, 5 conv blocks)
  → 192-dim per-frame embedding
  → append lag-1 & lag-2 deltas
  → feed into hoyso temporal stack
```

## Reference code skeleton

```python
def get_model(max_len=64, dropout_step=0, dim=192):
    inp = tf.keras.Input((max_len, CHANNELS))
    x = tf.keras.layers.Masking(mask_value=PAD)(inp)
    x = tf.keras.layers.Dense(dim, use_bias=False, name='stem_conv')(x)
    x = tf.keras.layers.BatchNormalization(momentum=0.95, name='stem_bn')(x)

    # 6× Conv1DBlock(dim, ksize=17, drop_rate=0.2)
    # interleaved with 2× TransformerBlock(dim, expand=2)
    # pattern: [C, C, C, T, C, C, C, T]

    x = tf.keras.layers.Dense(dim * 2, name='top_conv')(x)
    x = tf.keras.layers.GlobalAveragePooling1D()(x)
    x = LateDropout(0.8, start_step=dropout_step)(x)
    x = tf.keras.layers.Dense(NUM_CLASSES, name='classifier')(x)
    return tf.keras.Model(inp, x)
```

## Open questions / things to tune for us

1. **Frame encoder size** — start ~500K params (5 conv blocks), 192-dim output. Resize if browser latency suffers.
2. **T=64** — at 30 fps that's ~2.1s per clip. Should cover our beginner signs comfortably; revisit if any sign overruns.
3. **AWP** — costs ~2× training time. Worth keeping off until baseline lands, then enable to squeeze the last few points.
4. **LateDropout `start_step`** — needs retuning on our (smaller) dataset; their schedule assumed Kaggle-scale data.
5. **Ensemble size** — 4 seeds is great for offline accuracy but multiplies browser bundle size. Consider distilling the ensemble into a single student before shipping.
