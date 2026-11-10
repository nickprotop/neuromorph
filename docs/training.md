# Training & Testing the Avoidance Example

This guide explains how a driver program trains [`examples/brain.json`](../examples/brain.json) and checks whether it really learned. Use [`examples/brain_training.json`](../examples/brain_training.json) as the root: it includes `brain.json` unchanged and adds the learning switches and recording needed below.

Method names in code (`SetInput`, `Step`, `GetOutput`, `SetControl`) are placeholders for the engine's host API. Their behaviour follows [the spec](brain-json-spec.md) §4.10–4.12.

---

## 1. The goal

The brain should learn: **"when I feel touch pattern k, move muscle m(k)"**, *before* pain arrives. You choose the patterns and the mapping `m`; the brain doesn't know either until it is taught.

## 2. The driver's job

The driver is the world and the teacher. Every 10 ms (20 steps of 0.5 ms) it:

1. **Reads** the 8 muscle values (0–1) from `upper_limb_muscle_synergies`.
2. **Decides** what happened: muscle j has *moved* if its value is above **0.5**.
3. **Sends** the next inputs: the touch pattern, pain, and reward.

| Input | Size | Meaning |
| :--- | :--- | :--- |
| `somatosensory_mechanoreceptors` | 64 × [0,1] | Touch sensors. 1 = touched (120 Hz), 0 = silent. |
| `nociceptive_error_input` | 8 × [0,1] | Pain on channel j. Triggers the built-in reflex on muscle j and a dopamine dip. |
| `appetitive_reward_input` | 1 × [0,1] | Reward. Causes a dopamine burst. **Always a short pulse.** |
| `proprioceptive_muscle_spindles` | 8 × [-1,1] | Limb position. Not needed for this task; keep it at 0. |

Inputs stay set until you change them, so always set pain and reward back to 0 yourself.

## 3. Design the patterns

A pattern is just 64 numbers. Good patterns are **clearly different** from each other. Recommended starting set:

- **Pattern k** = sensors `8k … 8k+7` set to 1, all others 0 (k = 0…7). The patterns don't overlap at all.

Choose the mapping. To prove the brain learned something rather than relying on wiring, use a **shuffled** mapping, for example:

| Pattern k | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
| :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Muscle m(k) | 3 | 6 | 0 | 5 | 1 | 7 | 2 | 4 |

Pain for pattern k is given on channel **m(k)**, because the reflex is what first moves the correct muscle.

Harder variants, once the basic task works:
- **Noisy patterns:** flip about 10% of the sensors each trial.
- **Overlapping patterns:** neighbouring patterns share some sensors.
- **More patterns than muscles:** several patterns map to the same muscle.

## 4. One trial

```
cue      = pattern[k]          target = m(k)
show cue for up to 500 ms:
    if muscle[target] > 0.5:   -> AVOIDED: reward pulse (1.0 for 200 ms), end trial
if not avoided:
    pain on channel target (value 1.0), keep cue on
    when muscle[target] > 0.5: -> ESCAPED: pain off, reward pulse (1.0 for 200 ms), end trial
    give up after 1000 ms of pain: pain off, no reward
clear cue, wait 3 s (nothing on)
```

Why it works: early on, only the pain reflex moves the muscle. The cortex cells activated by the cue were active just before. Their connections to muscle m(k) are **marked** for about 1 second, and the reward pulse makes marked connections stronger. After enough trials, the cue alone moves the muscle.

Rules of thumb:
- Give the reward **within 1 s** of the movement, or the marks fade.
- Keep rewards **short**. A constant reward stops counting as a reward.
- The **3 s gap** keeps one trial's marks from leaking into the next.

## 5. Session plan

| Phase | Duration | What the driver does | `learning` |
| :--- | :--- | :--- | :--- |
| Settle | 15 s | Random touch patterns, no pain or reward. Learning is automatically off here (`plasticity_warmup_ms`). | 1 |
| Baseline test | 8 patterns × 5 | Cue only, no pain or reward. Record the confusion matrix (§6). | **0** |
| Training | blocks of 8 trials (all patterns, shuffled order) | Trials as in §4. | 1 |
| Test after each 5 blocks | 8 patterns × 5 | Cue only, no pain or reward. | **0** |

Switch learning with `SetControl("learning", 0 or 1)`. For a strict test, also set `SetControl("sprouting", 0)` so no new connections grow during testing.

## 6. Did it learn? How to check

Test trials show the cue for 500 ms with **no pain and no reward**, and learning off. Record which muscles went above 0.5 and how quickly.

1. **Confusion matrix (the main proof).** Make an 8 × 8 table, with rows = pattern shown and columns = muscle that moved first.
   - **Learned:** most counts on the target entries (k, m(k)).
   - **Not learned:** an empty table (nothing moves), or counts spread everywhere.
   - Because the mapping is shuffled, a strong match can only come from learning.
2. **Avoidance rate.** The share of training trials that ended as AVOIDED, plotted per block. It should rise from about 0 towards 1.
3. **Response time.** The time from cue onset to the target muscle passing 0.5. It should fall during training and stay under 500 ms.
4. **Specificity.** In test trials, other muscles should stay low. If every cue moves every muscle, the brain learned "move when touched", not the mapping.
5. **Inside the brain** (from `brain_training.json` probes):
   - `corticospinal_weights`: the weight distribution should spread, with a few connections growing strong while most stay or shrink.
   - `motor_dopamine`: short peaks after each reward, small dips during pain.
   - `cortex_rate`: should stay near a few Hz. Steady growth means runaway excitation (lower the learning gains).
6. **Generalisation (optional).** Test with noisy patterns that were never shown exactly. Good learning still gives mostly diagonal answers.

A simple pass criterion: **≥ 80% of test trials move the correct muscle first, within 500 ms, with no other muscle above 0.5.**

## 7. If it doesn't learn

| Symptom | Likely cause | Try |
| :--- | :--- | :--- |
| Nothing ever moves in test | Learning too slow | Raise `transfer_gain` on DA in `Corticospinal_ThreeFactor_STDP`, or train longer. |
| Every cue moves every muscle | Cue drives cortex too broadly, or reward given too often | Use more distinct patterns; check rewards are only given for the target muscle. |
| The reflex doesn't move the muscle | Reflex too weak | Raise the `innate_withdrawal_reflex_arc` weight. |
| Avoidance learned, then lost | Rewards too long or too frequent, so the running average absorbs them | Shorter reward pulses; longer gaps. |
| Cortex rate keeps rising | Too much excitation | Lower `a_plus` or `w_max` of the cortical rules. |

These values have not been run in a simulation yet. Expect a few rounds of tuning when the engine first runs.
