# 1st Place Solution — Google Isolated Sign Language Recognition (Kaggle, May 2023)

**Author:** hoyso48
**Approach:** 1D CNN combined with Transformer, trained from scratch on competition data only, 4-seed ensemble for submission.
**Stack:** Started with PyTorch + GPU, switched to TensorFlow + Colab TPU (TPUv2-8) for TFLite compatibility.

---

## TL;DR

A 1D CNN handles local inter-frame structure; a Transformer is stacked on top to handle longer-range context (the 1D CNN acts as a "trainable tokenizer"). Trained from scratch, regularized heavily, ensembled across 4 seeds.

---

## 1D CNN vs. Transformer — the hypothesis

> If there is a strong inter-frame correlation, 1D CNNs would be more efficient than Transformers.

A pure 1D CNN already reached **0.80 public LB**. The Transformer wasn't the headliner — it was used on top of the CNN to extend the receptive field. Combining the two is the same idea as CoAtNet, Conformer, MaxViT, NextViT, etc.

Starting point: 192-dim 8-layer 1D CNN.
Final: 192-dim **(3 conv + 1 transformer) × 2** structure → +0.01 CV and LB over the pure CNN.

- 1D CNN blocks use **depthwise convolution** with **causal padding**.
- Transformer blocks use **BatchNorm + Swish** instead of LayerNorm + GELU — slightly lighter inference, same accuracy.
- Single model: **~1.85M parameters**.

---

## Model code

```python
def get_model(max_len=64, dropout_step=0, dim=192):
    inp = tf.keras.Input((max_len, CHANNELS))
    x = tf.keras.layers.Masking(mask_value=PAD, input_shape=(max_len, CHANNELS))(inp)
    ksize = 17
    x = tf.keras.layers.Dense(dim, use_bias=False, name='stem_conv')(x)
    x = tf.keras.layers.BatchNormalization(momentum=0.95, name='stem_bn')(x)

    x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
    x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
    x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
    x = TransformerBlock(dim, expand=2)(x)

    x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
    x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
    x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
    x = TransformerBlock(dim, expand=2)(x)

    if dim == 384:  # for the 4x sized model
        x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
        x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
        x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
        x = TransformerBlock(dim, expand=2)(x)

        x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
        x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
        x = Conv1DBlock(dim, ksize, drop_rate=0.2)(x)
        x = TransformerBlock(dim, expand=2)(x)

    x = tf.keras.layers.Dense(dim * 2, activation=None, name='top_conv')(x)
    x = tf.keras.layers.GlobalAveragePooling1D()(x)
    x = LateDropout(0.8, start_step=dropout_step)(x)
    x = tf.keras.layers.Dense(NUM_CLASSES, name='classifier')(x)
    return tf.keras.Model(inp, x)
```

---

## Masking (variable-length inputs)

Handling variable-length input correctly was crucial for train/test consistency and inference speed — short videos shouldn't need to be padded at inference.

- **Training:** `max_len=384` with padding and truncation.
- **Inference:** truncation only, no padding.
- **`tf.keras.layers.Masking`** at the start propagates the mask through the model.
- **Causal padding** is used in the Conv1D so the mask index stays aligned.
- Operations sensitive to masking (BatchNorm, GlobalAveragePooling) must be mask-aware.

### Why causal padding for the conv blocks (hoyso48, from comments)

`Masking(PAD)` marks pad tokens; Transformer blocks already accept `attention_mask`, so they handle PAD natively.

For Conv1D, kernel size > 1 means pad tokens would intrude into real frames if you used `padding='same'`. **Causal padding** prevents kernels from looking at "future" frames and preserves time-frame alignment at `strides=1`, so the original mask from the `Masking` layer stays valid without extra bookkeeping.

If you try `PAD=0` with no masking during training and no padding at inference, accuracy drops significantly due to train/test inconsistency. Masking is the right answer.

---

## Regularization

All three of the following were essential — removing any one caused noticeable drops on both CV and LB. Training ran >300 epochs, so without heavy regularization the model overfit hard.

- **DropPath** (stochastic depth, p=0.2) — applied after each block.
- **High Dropout** (p=0.8) — applied after Global Average Pooling.
- **AWP** (Adversarial Weight Perturbation, λ=0.2).

AWP and the high dropout were both turned on starting at **epoch 15** (LateDropout).

---

## Preprocessing

```python
class Preprocess(tf.keras.layers.Layer):
    def __init__(self, max_len=MAX_LEN, point_landmarks=POINT_LANDMARKS, **kwargs):
        super().__init__(**kwargs)
        self.max_len = max_len
        self.point_landmarks = point_landmarks

    def call(self, inputs):
        if tf.rank(inputs) == 3:
            x = inputs[None, ...]
        else:
            x = inputs

        # Center around landmark 17 (nose-ish), which sits near (0.5, 0.5)
        mean = tf_nan_mean(tf.gather(x, [17], axis=2), axis=[1, 2], keepdims=True)
        mean = tf.where(tf.math.is_nan(mean), tf.constant(0.5, x.dtype), mean)
        x = tf.gather(x, self.point_landmarks, axis=2)  # N, T, P, C
        std = tf_nan_std(x, center=mean, axis=[1, 2], keepdims=True)
        x = (x - mean) / std

        if self.max_len is not None:
            x = x[:, :self.max_len]
        length = tf.shape(x)[1]
        x = x[..., :2]  # drop z, keep (x, y)

        # Lag-1 and lag-2 motion features
        dx = tf.cond(
            tf.shape(x)[1] > 1,
            lambda: tf.pad(x[:, 1:] - x[:, :-1], [[0, 0], [0, 1], [0, 0], [0, 0]]),
            lambda: tf.zeros_like(x),
        )
        dx2 = tf.cond(
            tf.shape(x)[1] > 2,
            lambda: tf.pad(x[:, 2:] - x[:, :-2], [[0, 0], [0, 2], [0, 0], [0, 0]]),
            lambda: tf.zeros_like(x),
        )

        x = tf.concat([
            tf.reshape(x,   (-1, length, 2 * len(self.point_landmarks))),
            tf.reshape(dx,  (-1, length, 2 * len(self.point_landmarks))),
            tf.reshape(dx2, (-1, length, 2 * len(self.point_landmarks))),
        ], axis=-1)

        x = tf.where(tf.math.is_nan(x), tf.constant(0., x.dtype), x)
        return x
```

**Landmarks used:** left + right hand, eye, nose, lips.
**Normalization reference:** landmark 17 (nose), chosen because it's typically near image center (0.5, 0.5).
**Motion features:** lag-1 (`x[t] - x[t-1]`) and lag-2 (`x[t] - x[t-2]`). Lag > 2 didn't help.

---

## Augmentation

**Temporal**
- Random resample (0.5× ~ 1.5× original length)
- Random masking

**Spatial**
- Horizontal flip
- Random affine (scale, shift, rotate, shear)
- Random cutout

---

## Training

| Setting    | Value                                                  |
| ---------- | ------------------------------------------------------ |
| Epochs     | 400                                                    |
| LR         | 5e-4 × num_replicas = 4e-3                             |
| Schedule   | CosineDecay, no warmup                                 |
| Optimizer  | RAdam + Lookahead (beat AdamW at optimal params)       |
| Loss       | CCE with label smoothing 0.1 (or plain CCE)            |
| Hardware   | Colab TPUv2-8, ~4 hours per model                      |

---

## Results

| Metric                          | Score |
| ------------------------------- | ----- |
| CV (participant split, 5-fold)  | 0.80  |
| Public LB                       | 0.80  |
| Private LB                      | 0.88  |
| 4-seed ensemble (public LB)     | 0.81  |

A 4× sized model (384d, 16 layers) with the same settings actually scored slightly worse — hoyso believes it could match or beat the 192d model with better configurations, but didn't pursue it.

---

## Tried but didn't work

- **GCNs**
- More complex augmentations (angle/distance-based, grid distortion across temporal/spatial axes)
- **CutMix / MixUp** — main blocker was defining the new label when the two inputs had different lengths.
- **Knowledge Distillation** (single 4× model distilled from the 4-seed 4× ensemble) — didn't manage to make it work in the time available.

---

## Released code

Inference notebook: <https://www.kaggle.com/competitions/asl-signs/discussion/406978>
