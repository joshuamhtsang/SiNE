Short answer: **PER alone is not enough to *predict* jitter**, but it *does* let you **bound and estimate it** once you add a little MAC context.

Let’s make that precise and practical.

---

## Why PER matters for jitter (but isn’t sufficient)

PER tells you:

> “What fraction of packets fail *per transmission attempt* at this SNR/MCS.”

Jitter comes from:

* **random backoff**
* **retransmissions**
* **aggregation delays**

PER directly drives **retransmissions**, which are the *largest* source of *long-tail* jitter.

But PER does **not** encode:

* contention level
* backoff window
* retry limits
* aggregation size

So:

* ❌ PER → exact jitter ❌
* ✅ PER → retry statistics → delay distribution ✅

---

## The minimal model: PER → retries → delay

Assume:

* independent packet errors
* PER = *p*
* max retries = *R*
* each attempt takes time *Ttx*
* average backoff time *Tb*

### Probability of *k* retries

```
P(k retries) = p^k · (1 − p),   for k < R
```

### Expected number of transmissions

```
E[N] = 1 / (1 − p)
```

### Expected packet delay

```
E[delay] ≈ E[N] · (Ttx + Tb)
```

### Jitter (standard deviation, rough)

```
σ_delay ≈ sqrt(p / (1 − p)^2) · (Ttx + Tb)
```

So jitter grows **nonlinearly** as PER rises.

---

## Intuition check (important)

| PER   | Avg retries | Jitter behavior |
| ----- | ----------- | --------------- |
| 0.01  | ~1.01       | negligible      |
| 0.05  | ~1.05       | small           |
| 0.10  | ~1.11       | noticeable      |
| 0.30  | ~1.43       | large           |
| 0.50  | 2.0         | brutal          |
| >0.70 | unstable    | unusable        |

This is why **10% PER** is often used as an MCS threshold — above that, latency and jitter explode.

---

## What PER *can* give you reliably

With just PER + a few constants, you can estimate:

✔ mean latency
✔ jitter trend (low / medium / high)
✔ tail latency risk
✔ retry-induced burstiness

That’s already useful for:

* voice
* control loops
* IoT telemetry

---

## What you still need for accurate jitter

Add **three MAC knobs** and you’re golden:

```yaml
mac:
  timing:
    slot_time_us: 52
    contention_window:
      min: 16
      max: 1024

  retransmission:
    max_retries: 7

  aggregation:
    max_ppdu_us: 4000
```

Now:

* PER → retry count distribution
* backoff → delay variance
* aggregation → jitter smoothing *or* bursts

---

## Key insight (this is the money line)

> **PER determines how often delay *spikes***
> **MAC determines how large those spikes are**

That’s the correct mental model.

---

## Practical recommendation for your YAML

Do this:

1. Store **PER vs SNR per MCS** (you already like this ✔)
2. Store **retry limits & timing**
3. Compute jitter statistically, not deterministically

If you want a clean output metric:

```yaml
derived_metrics:
  jitter_ms:
    p50: 3
    p95: 15
    p99: 40
```

…but compute it, don’t store it.

---

If you want, I can:

* walk through a **numerical jitter example**
* derive **closed-form bounds** for 802.11ah
* show how **rate adaptation reduces jitter vs fixed MCS**

You’re asking exactly the right questions for realistic radio modeling — keep going.
