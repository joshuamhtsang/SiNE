“Typical” spectral efficiency depends very strongly on **what layer you mean** (PHY vs system), **how adaptive the link is**, and **how conservative the design is**. But there *are* well-established ranges that engineers use as sanity checks.

Below is a practical, cross-technology view.

---

## 1. Theoretical upper bound (for context)

Shannon capacity:

[
\eta_{\max} = \log_2(1 + \text{SINR}) \quad \text{bits/s/Hz}
]

Examples:

| SINR (dB) | SINR (lin) | Shannon limit (b/s/Hz) |
| --------- | ---------- | ---------------------- |
| 0 dB      | 1          | 1.0                    |
| 5 dB      | 3.2        | 2.0                    |
| 10 dB     | 10         | 3.46                   |
| 20 dB     | 100        | 6.66                   |
| 30 dB     | 1000       | 9.97                   |

**Real systems operate well below this**, typically at **50–80%** of Shannon at the PHY, and much less at system level.

---

## 2. Spectral efficiency by modulation & coding (PHY-level)

These are *raw PHY efficiencies*, ignoring overhead:

| Modulation | Code rate | Spectral efficiency (b/s/Hz) |
| ---------- | --------- | ---------------------------- |
| BPSK       | 1/2       | 0.5                          |
| QPSK       | 1/2       | 1.0                          |
| QPSK       | 3/4       | 1.5                          |
| 16-QAM     | 1/2       | 2.0                          |
| 16-QAM     | 3/4       | 3.0                          |
| 64-QAM     | 2/3       | 4.0                          |
| 64-QAM     | 3/4       | 4.5                          |
| 256-QAM    | 3/4       | 6.0                          |
| 256-QAM    | 5/6       | ~6.7                         |

**Rule of thumb:**

> Each extra ~3 dB of SINR buys you roughly **+1 b/s/Hz** in practical systems.

---

## 3. Typical *system-level* spectral efficiency

Once you include:

* MAC overhead
* Pilots / reference signals
* Control channels
* Retransmissions
* Guard intervals
* Half-duplex constraints

…the numbers drop.

### Wi-Fi (802.11n/ac/ax)

* Poor channel: **0.5–1 b/s/Hz**
* Typical good link: **2–4 b/s/Hz**
* Excellent, short-range: **5–6 b/s/Hz**

### LTE / 5G (single user)

* Cell edge: **0.2–0.5 b/s/Hz**
* Typical user: **1–3 b/s/Hz**
* Very good conditions: **4–5 b/s/Hz**

### Tactical / military radios (conservative by design)

* Robust modes: **0.1–0.5 b/s/Hz**
* Normal operation: **0.5–1.5 b/s/Hz**
* Aggressive modes: **2–3 b/s/Hz**

These lower numbers are *intentional* — robustness and coexistence matter more than peak rate.

---

## 4. Mapping spectral efficiency to SINR (practical rule)

A very common engineering mapping looks like this:

| SINR (dB) | Practical spectral efficiency (b/s/Hz) |
| --------- | -------------------------------------- |
| −5        | ~0.1–0.2                               |
| 0         | ~0.5–1                                 |
| 5         | ~1–2                                   |
| 10        | ~2–3                                   |
| 15        | ~3–4                                   |
| 20        | ~4–5                                   |
| 25+       | ~5–6                                   |

If your model violates this badly, something is off.

---

## 5. Why this matters for EMANE / link models

If your EMANE link shows:

* SINR = 20 dB
* Throughput = 0.5 b/s/Hz

That means:

* You are **MCS-limited**, not channel-limited
* PCR will look perfect
* You are wasting ~80% of channel capacity

Conversely:

* High spectral efficiency at low SINR usually implies:

  * Unrealistic PCR curves
  * Overly optimistic link modeling

---

## 6. A compact mental checklist

When sanity-checking a link:

1. What SINR does the channel provide?
2. What spectral efficiency does the MCS imply?
3. Is efficiency ≤ ~70% of Shannon?
4. Is PCR high in the region where MCS is stable?
5. Does throughput fall *before* PCR collapses?

If yes → your model is realistic.

---

If you want, I can:

* Give **SINR→MCS→spectral efficiency tables** suitable for EMANE
* Help you design **PCR curves that stay flat across MCS regimes**
* Show how to infer spectral efficiency from measured throughput traces

