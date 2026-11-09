# `brain.json` Architecture & Configuration Specification (v4.3)

This document defines the declarative schema for the **Pure Core Neural Simulation Engine**. The engine is purely mathematical and has no built-in biological names. Anatomy, chemical kinetics, eligibility-trace pipelines, ligand-gated plasticity, network topology and sensory/motor transducers all come from this configuration file.

The keywords **MUST**, **MUST NOT**, **SHOULD** and **MAY** are used as in RFC 2119. A conforming engine produces bit-identical results for the same `brain.json`, seed and input stream, whatever its thread count (see [§5.4](#54-determinism)).

---

## Table of Contents
1. [Root Schema Overview](#1-root-schema-overview)
2. [Units & Conventions](#2-units--conventions)
3. [Enum Reference Index](#3-enum-reference-index)
4. [Detailed Section Specifications](#4-detailed-section-specifications)
   - [4.1 Meta & Simulation](#41-meta--simulation)
   - [4.2 Neurotransmitters (Ligand Pools)](#42-neurotransmitters-ligand-pools)
   - [4.3 Receptors](#43-receptors)
   - [4.4 Plasticity Rules](#44-plasticity-rules)
   - [4.5 Short-Term Dynamics](#45-short-term-dynamics)
   - [4.6 Cell Types](#46-cell-types)
   - [4.7 Nuclei, Placement & Projections](#47-nuclei-placement--projections)
   - [4.8 Structural Plasticity](#48-structural-plasticity)
   - [4.9 External I/O Interfaces](#49-external-io-interfaces)
5. [Execution Semantics](#5-execution-semantics)
6. [Validation Rules](#6-validation-rules)
7. [Complete Reference Example](#7-complete-reference-example)

---

## 1. Root Schema Overview

The root JSON object has nine required top-level properties:

```json
{
  "meta": { ... },               // Versioning, naming, deterministic RNG seed
  "simulation": { ... },         // Clock rates and global constants
  "neurotransmitters": { ... },  // Abstract ligands and clearance kinetics
  "receptors": { ... },          // Conductance channels and cellular modulation
  "plasticity_rules": { ... },   // Coincidence -> Trace -> Ligand-gated weight transfer
  "short_term_dynamics": { ... },// Presynaptic depression / facilitation
  "cell_types": { ... },         // Neuron and compartment dynamics
  "nuclei": [ ... ],             // Populations, placement, gap junctions, projections
  "io_interfaces": { ... }       // Sensory encoders and motor decoders
}
```

JSON object members are unordered (RFC 8259). The engine **MUST NOT** depend on member order. Cross-references are resolved after the whole document is parsed. Unknown properties, and properties that don't apply to the selected model or enum value, are validation **errors**, so typos are never silently ignored.

`"None"` is a reserved identifier. It means "no rule" in `stp_rule` and `ltp_rule`, and **MUST NOT** be used as a key in any dictionary.

---

## 2. Units & Conventions

All dynamics use one normalised-capacitance unit system ($C_m = 1$):

| Quantity | Unit | Notes |
| :--- | :--- | :--- |
| Time | ms | All `*_ms` fields. |
| Membrane potential | mV | All `*_mv` fields. |
| Current ("current units", cu) | mV/ms | Adds directly to $dV/dt$. Izhikevich's $I$ is in these units. |
| Conductance | ms⁻¹ | $I = g\,(E_{\text{rev}} - V)$ gives mV/ms. |
| Concentration | dimensionless (c.u.) | Abstract ligand units. |
| Rate | Hz | Converted to ms⁻¹ ($r/1000$) wherever it enters a ms-based equation. |
| Distance | mm | Stereotaxic coordinates. |
| Conduction velocity | m/s | Since 1 mm ÷ 1 m/s = 1 ms, delay in ms = distance in mm ÷ velocity in m/s. |
| Synaptic weight $w$ | dimensionless, ≥ 0 | Scales transmitter release. Excitation vs. inhibition comes **only** from the receptor's $E_{\text{rev}}$. |

**Sign convention:** every current term is written as *depolarising positive*. Synaptic current is $I_{\text{syn}} = \sum_r g_r\,B_r(V)\,(E_r - V)$.

---

## 3. Enum Reference Index

String literals bind to C# enums (byte-backed in data-oriented arrays). Byte IDs are stable across schema versions.

### 3.1 `LigandClearanceModel`
Defines how the deviation $\Delta = C - C_{\text{base}}$ of a pool relaxes to zero.

| Value | Byte | Formulation | Required fields |
| :--- | :---: | :--- | :--- |
| `ExponentialDecay` | `0` | $\dfrac{d\Delta}{dt} = -\dfrac{\Delta}{\tau_{\text{clear}}}$ | `clearance_tau_ms` |
| `MichaelisMenten` | `1` | $\dfrac{d\Delta}{dt} = -\dfrac{V_{\max}\,\Delta}{K_m + \lvert\Delta\rvert}$ (sign-safe: also restores concentration from below baseline) | `v_max` (c.u./ms), `k_m` (c.u.) |

### 3.2 `CellularModulationTarget`
Each modulating receptor produces a multiplicative factor $F$ ([§4.3.3](#433-cellular-modulation)). Factors from several receptors acting on the same target multiply together.

| Value | Byte | Effect of factor $F$ |
| :--- | :---: | :--- |
| `None` | `0` | No effect. |
| `MembraneExcitability` | `1` | Input gain: synaptic, sensory and gap-junction current summed per compartment is multiplied by $F$. Intrinsic and homeostatic currents are not scaled. |
| `SpikeAdaptation` | `2` | Multiplies the post-spike adaptation increment ($d$ for Izhikevich, $b$ for AdEx). No effect on `LIF` (validation warning). |
| `DendriticCoupling` | `3` | Multiplies $g_c$ in `Izhikevich_2C`. No effect on single-compartment models (validation warning). |
| `HomeostaticSetPoint` | `4` | Multiplies the cell's homeostatic $r_{\text{target}}$. |

### 3.3 `ReceptorKineticsModel`

| Value | Byte | Description |
| :--- | :---: | :--- |
| `DualExponentialConductance` | `0` | Ionotropic: $I = g_{\max}\,s(t)\,(E_{\text{rev}} - V)$. |
| `VoltageGatedConductance` | `1` | As above, multiplied by the Mg²⁺ block $B(V)$. |
| `MetabotropicLinearGain` | `2` | Non-conducting. Its activation $s(t)$ drives a `cellular_modulation`. |

$s(t)$ is the receptor activation defined in [§4.3.1](#431-activation-cascade).

### 3.4 `CoincidenceDetectionModel`

| Value | Byte | Summary (full definition in [§4.4.2](#442-stage-1--coincidence-models)) |
| :--- | :---: | :--- |
| `None` | `0` | Static synapse. Not allowed inside a plasticity rule; use `"ltp_rule": "None"` instead. |
| `AsymmetricSTDP` | `1` | Pair-based causal STDP, all-to-all pairing via traces. |
| `SymmetricSTDP` | `2` | Vogels–Sprekeler inhibitory plasticity. |
| `TripletSTDP` | `3` | Pfister–Gerstner all-to-all triplet rule. |
| `BCM_Rate` | `4` | Rate-based BCM with a sliding threshold. |

### 3.5 `ShortTermPlasticityModel`

| Value | Byte | Description |
| :--- | :---: | :--- |
| `None` | `0` | Reserved; selected with `"stp_rule": "None"`. Gives $r_{\text{STP}} = 1$. |
| `TsodyksMarkram` | `1` | Resources $x$ and utilisation $u$ ([§4.5](#45-short-term-dynamics)). |

### 3.6 `NeuronDynamicsModel`

| Value | Byte | Allowed `compartments` |
| :--- | :---: | :--- |
| `Izhikevich_1C` | `0` | `["Soma"]` |
| `Izhikevich_2C` | `1` | `["Soma", "ApicalDendrite"]` or `["Soma", "BasalDendrite"]` |
| `AdEx` | `2` | `["Soma"]` |
| `LIF` | `3` | `["Soma"]` |

### 3.7 `CompartmentType`

| Value | Byte | Role |
| :--- | :---: | :--- |
| `Soma` | `0` | Spike generation; target of perisomatic inhibition. |
| `ApicalDendrite` | `1` | Distal tree; top-down/modulatory input; plateau potentials. |
| `BasalDendrite` | `2` | Proximal tree; feedforward input. |

### 3.8 `IntrinsicCurrentType`

| Value | Byte | Fields | Definition |
| :--- | :---: | :--- | :--- |
| `None` | `0` | — | $I_{\text{int}} = 0$ |
| `ConstantDC` | `1` | `value` (cu) | $I_{\text{int}} = \text{value}$ |
| `PoissonShotNoise` | `2` | `rate_hz`, `kick_mv` | Each step, with probability $1 - e^{-\lambda\,dt}$, $V_{\text{soma}}$ += `kick_mv`. |
| `OrnsteinUhlenbeck` | `3` | `mean_current`, `sigma_current`, `tau_ms` | Exact update: $I \leftarrow \mu + (I-\mu)e^{-dt/\tau} + \sigma\sqrt{1-e^{-2dt/\tau}}\;\xi$, $\xi\sim\mathcal N(0,1)$. Stationary std = $\sigma$. |

### 3.9 `TopologyType`

| Value | Byte | Fields | Rule |
| :--- | :---: | :--- | :--- |
| `AllToAll` | `0` | — | Every (source, target) pair. |
| `OneToOne` | `1` | — | Source rank $i$ → target rank $i$; equal sizes required. |
| `Random` | `2` | `probability` | Independent Bernoulli per pair. |
| `FixedIndegree` | `3` | `k` | Each target draws exactly $k$ distinct sources uniformly; $k \le N_{\text{src}}$ (after excluding autapses). |
| `SpatialGaussian` | `4` | `sigma_mm`, `max_prob` | $P = P_{\max}\exp(-d_{ij}^2/2\sigma^2)$, $d_{ij}$ = absolute 3-D distance between the two neurons' positions. |
| `Topographic` | `5` | `sigma_rel`, `max_prob`, `axes` (default `[0,1,2]`) | $P = P_{\max}\exp(-\lVert\hat p_i - \hat p_j\rVert^2_{\text{axes}}/2\sigma_{\text{rel}}^2)$ on normalised coordinates ([§4.7.1](#471-placement--normalised-coordinates)), summed over the listed axes only. |

Every topology also accepts `allow_autapses` (default `false`). It only matters when the source and target populations are the same. Multapses (more than one synapse per pair) are never created at build time.

**Expected indegree.** For an interior target neuron, `SpatialGaussian` gives $\mathbb E[K] \approx \rho\,P_{\max}\,(2\pi\sigma^2)^{3/2}$, where $\rho$ is the source density per mm³. Neurons near the sphere's surface get fewer. σ must be chosen for the **model's** density, not biological density. The compiler reports realised indegree statistics ([§6](#6-validation-rules)).

### 3.10 `DistributionType`

| Value | Byte | Fields | Notes |
| :--- | :---: | :--- | :--- |
| `Constant` | `0` | `value` | |
| `Uniform` | `1` | `min`, `max` | |
| `Gaussian` | `2` | `mean`, `std` | |
| `LogNormal` | `3` | `mu`, `sigma` | Parameters of the underlying normal; median $= e^{\mu}$. |

Sampled weights are **clipped** to $[w_{\min}, w_{\max}]$ of the projection's `ltp_rule`, or to $[0, \infty)$ for static synapses.

### 3.11 `SensoryEncodingModel`

The normalised input is $\hat x = \text{clamp}\!\left(\frac{x - x_{\min}}{x_{\max} - x_{\min}}, 0, 1\right)$, with $x_{\min}, x_{\max}$ = `min_input`, `max_input`.

| Value | Byte | Fields | Mechanism (per neuron of the channel's block) |
| :--- | :---: | :--- | :--- |
| `DirectCurrent` | `0` | `min_current`, `max_current` | $I = I_{\min} + \hat x\,(I_{\max} - I_{\min})$, held until the next input frame. |
| `PoissonRate` | `1` | `min_rate_hz`, `max_rate_hz`, `injection_weight_mv` | Independent Poisson process at $\lambda = r_{\min} + \hat x(r_{\max} - r_{\min})$. Each event adds `injection_weight_mv` to the target compartment's $V$. |
| `TimeToFirstSpike` | `2` | `window_ms`, `min_activation`, `injection_weight_mv` | At the start of each window, if $\hat x \ge$ `min_activation`, one kick is scheduled at latency $(1-\hat x)\cdot$`window_ms`, rounded to a whole step. |
| `PopulationGaussianReceptiveField` | `3` | `receptive_field_sigma`, `gain_current` | The $n$ neurons of the block get preferred values $\mu_k = x_{\min} + \frac{k + 0.5}{n}(x_{\max} - x_{\min})$ and current $I_k = \text{gain}\cdot\exp(-(x - \mu_k)^2 / 2\sigma^2)$, where σ is in raw input units and $x$ is clamped to $[x_{\min}, x_{\max}]$. |

### 3.12 `MotorDecodingModel`

Each source neuron $i$ keeps a rate trace $y_i$ in Hz. It decays with `tau_trace_ms` and jumps by $1000/\tau_{\text{trace}}$ on each spike, so it estimates the firing rate. A channel's activity is $\bar y_c = \frac{1}{n_c}\sum_{i \in c} y_i$.

| Value | Byte | Fields | Output |
| :--- | :---: | :--- | :--- |
| `ExponentialRateTrace` | `0` | `tau_trace_ms`, `rate_normalization_hz` | $o_c = \text{gain}\cdot\bar y_c / r_{\text{norm}}$ |
| `PopulationVector` | `1` | `tau_trace_ms`, `rate_normalization_hz`, `preferred_directions` (`"UniformCircle"`, `"UniformSphere"` or an explicit `[[...],...]` list, one per neuron) | $\mathbf o = \text{gain}\cdot\frac{1}{N}\sum_i (y_i / r_{\text{norm}})\,\mathbf p_i$; `dimensions` must be 2 or 3. For the uniform options, $\mathbf p_i$ are spread evenly by rank (Fibonacci lattice for the sphere). |
| `SlidingWindowRate` | `2` | `window_ms`, `rate_normalization_hz` | $o_c = \text{gain}\cdot\frac{\text{spikes in window}}{n_c \cdot W/1000} / r_{\text{norm}}$ |
| `WinnerTakeAll` | `3` | `tau_trace_ms`, `min_activity_hz` | $o_c = 1$ for $c = \arg\max \bar y_c$ (lowest index on ties) if $\max \bar y_c \ge$ `min_activity_hz`; otherwise all 0. |

The output is clamped to `clamp_bounds` when given. `output_gain` (default 1.0) is the "gain" above. It does not apply to `WinnerTakeAll`.

### 3.13 `ReferenceMode`

Used by plasticity `modulator_couplings[].reference` and by `cellular_modulation.reference`.

| Value | Byte | Fields | Definition |
| :--- | :---: | :--- | :--- |
| `Fixed` | `0` | `value` | $C_{\text{ref}} = \text{value}$ |
| `RunningAverage` | `1` | `tau_ms` | $C_{\text{ref}}$ is a per-pool exponential average of the signal, initialised to the ligand's `baseline_ambient`. Plasticity couplings update it once per batch with the batch-mean concentration $\bar C$, *after* the transfer: $C_{\text{ref}} \leftarrow C_{\text{ref}} + (\bar C - C_{\text{ref}})(1 - e^{-\Delta_p/\tau})$. Modulation updates it every step with $s(t)$. |

`RunningAverage` is the recommended mode for any tonically released ligand. Tonic release then sets the zero point, a phasic burst gives a positive deviation, and a pause gives a negative one.

---

## 4. Detailed Section Specifications

### 4.1 `meta` & `simulation`

`meta`: `schema_version` (must be `"4.3"`), `name`, `seed` (unsigned 64-bit integer).

| `simulation` field | Default | Meaning |
| :--- | :--- | :--- |
| `dt_ms` | required | Base integration step. |
| `neuron_substeps` | `2` | Number of Euler sub-steps per `dt` for the nonlinear membrane equations ([§5.2](#52-per-step-update-order)). |
| `plasticity_update_interval_ms` | required | Batch interval $\Delta_p$ for trace→weight transfer. Must be an integer multiple of `dt_ms`. |
| `structural_update_interval_ms` | required | Interval $\Delta_s$ for pruning and sprouting. Must be an integer multiple of $\Delta_p$. |
| `plasticity_warmup_ms` | `0` | For $t <$ warmup, weight transfer (Stage 2) and structural updates are disabled. Traces, running references and homeostasis still run, so `RunningAverage` references settle before learning starts. |
| `default_resting_potential_mv` | `-65.0` | Initial $V$ of every compartment. Izhikevich $u_0 = b\,V_0$; AdEx $w_0 = 0$. |
| `validation_max_rate_hz` | `100.0` | Worst-case sustained presynaptic rate used by the divergence checks in [§6](#6-validation-rules). |

### 4.2 `neurotransmitters` (Ligand Pools)

This is a dictionary keyed by an arbitrary ligand ID. For every compartment of every neuron, the engine keeps one concentration $C_{i,c,k}$ per ligand $k$, initialised to `baseline_ambient`. Only (population, compartment, ligand) combinations that receive release, express a receptor for the ligand, or are read by a modulator coupling are allocated. All other combinations stay constant at `baseline_ambient`.

| Field | Meaning |
| :--- | :--- |
| `clearance_model` | `LigandClearanceModel`. |
| `baseline_ambient` | $C_{\text{base}} \ge 0$. The clearance target. |
| `clearance_tau_ms` | For `ExponentialDecay` only. |
| `v_max`, `k_m` | For `MichaelisMenten` only. |
| `quantal_release` | $q$: concentration added per unit of release. |

**Release.** When a presynaptic spike reaches synapse $j \to (i, c)$ after its delay, the target pool is incremented:
$$C_{i,c,k} \mathrel{+}= w_{ij}\; q_k\; r^{\text{STP}}_{j}$$
Here $r^{\text{STP}}$ is the release fraction computed at spike emission ([§4.5](#45-short-term-dynamics)). This is the **only** way synaptic weight affects postsynaptic dynamics. Concentration is clamped to $C \ge 0$.

**Clearance (per step, exact or exponential-Euler):**
- `ExponentialDecay`: $\Delta \leftarrow \Delta\, e^{-dt/\tau}$.
- `MichaelisMenten`: $\Delta \leftarrow \Delta\, \exp\!\left(-\frac{V_{\max}\,dt}{K_m + |\Delta|}\right)$. This is unconditionally stable and keeps the sign. For small $\Delta$ the time constant is $K_m / V_{\max}$.

### 4.3 `receptors`

| Field | Applies to | Meaning |
| :--- | :--- | :--- |
| `ligand` | all | Key in `neurotransmitters`. |
| `kinetics` | all | `ReceptorKineticsModel`. |
| `tau_rise_ms`, `tau_decay_ms` | all | Activation cascade time constants; rise < decay. |
| `g_max` | conductance kinetics | Conductance (ms⁻¹) per unit of activation. |
| `reversal_potential_mv` | conductance kinetics | $E_{\text{rev}}$. |
| `mg_block_conc_mm` | `VoltageGatedConductance` | $[\text{Mg}^{2+}]_o$. |
| `cellular_modulation` | `MetabotropicLinearGain` (required); not allowed on conductance kinetics | See [§4.3.3](#433-cellular-modulation). |

#### 4.3.1 Activation cascade
Each receptor $r$ expressed in compartment $(i, c)$ filters its ligand pool through two first-order stages. The steady-state gain is 1, so a constant concentration $C$ gives $s = C$:
$$\tau_{\text{rise}}\frac{da}{dt} = -a + C_{i,c,\text{ligand}(r)}, \qquad \tau_{\text{decay}}\frac{ds}{dt} = -s + a$$
Both stages are updated with exponential Euler, which is exact for piecewise-constant input, in the order $C \to a \to s$. This is stable for any `dt`, including $\tau_{\text{rise}} < dt$.

The total charge from one release event of size $\Delta C_0$ into an exponentially cleared pool is $g_{\max}\,\Delta C_0\,\tau_{\text{clear}}\,(E_{\text{rev}} - V)$. This is the main quantity for calibrating `g_max`.

#### 4.3.2 Conductance current
$$I_{\text{syn}}(i,c) = \sum_{r} g_{\max,r}\; s_r\; B_r(V_{i,c})\;(E_r - V_{i,c}), \qquad B(V) = \left(1 + \frac{[\text{Mg}^{2+}]_o}{3.57}e^{-0.062V}\right)^{-1}$$
$B \equiv 1$ for `DualExponentialConductance`. Use $V$ from the start of the step.

#### 4.3.3 Cellular modulation
```json
"cellular_modulation": {
  "target": "MembraneExcitability",
  "gain": 1.25,
  "reference": { "mode": "Fixed", "value": 0.2 },
  "min_factor": 0.5,
  "max_factor": 2.0
}
```
$$F_r = \text{clamp}\big(1 + \text{gain}\cdot(\bar s_r - s_{\text{ref}}),\ \text{min\_factor},\ \text{max\_factor}\big)$$
$\bar s_r$ is the receptor's activation averaged over all compartments of the cell that express it. The defaults are `min_factor` = 0.25 and `max_factor` = 4.0. A cell's factor for a target is the product of its receptors' $F_r$ for that target (1 if there are none).

### 4.4 `plasticity_rules`

Every plastic synapse stores a weight $w_{ij}$, an eligibility trace $e_{ij}$, and the per-synapse state required by its coincidence model.

```json
"Rule_Name": {
  "coincidence_model": "AsymmetricSTDP",
  "params": { ... },
  "trace_tau_ms": 1200.0,
  "base_transfer_rate": 0.00005,
  "modulator_couplings": [
    { "ligand": "DA", "reference": { "mode": "RunningAverage", "tau_ms": 5000.0 }, "transfer_gain": 0.1 }
  ],
  "w_min": 0.0,
  "w_max": 6.0
}
```

#### 4.4.1 Timing conventions
- $t_{\text{pre}}$ is the **arrival** time at the synapse (spike time + axonal delay). $t_{\text{post}}$ is the postsynaptic somatic spike time. $\Delta t = t_{\text{post}} - t_{\text{pre}}$.
- Within one step, arrivals are processed before the neuron update and postsynaptic spikes after it ([§5.2](#52-per-step-update-order)). So an arrival and a spike in the same step count as **causal** ($\Delta t = 0^+$).
- All traces decay exponentially between events, computed lazily from the last-update timestamp. A presynaptic trace is per synapse; a postsynaptic trace is per neuron per rule.

#### 4.4.2 Stage 1 — Coincidence models
Each event adds $\delta e$ to $e_{ij}$.

**`AsymmetricSTDP`** — `tau_plus_ms`, `tau_minus_ms`, `a_plus`, `a_minus`. Traces $x_{\text{pre}}$ ($\tau_+$) and $x_{\text{post}}$ ($\tau_-$), each incremented by 1 per spike.
- Pre arrival: $\delta e = -A_-\,x_{\text{post}}$, then $x_{\text{pre}}$ += 1.
- Post spike: $\delta e = +A_+\,x_{\text{pre}}$, then $x_{\text{post}}$ += 1.

This reproduces all-to-all pair STDP: $+A_+e^{-\Delta t/\tau_+}$ for $\Delta t \ge 0$ and $-A_-e^{\Delta t/\tau_-}$ for $\Delta t < 0$.

**`SymmetricSTDP`** (Vogels–Sprekeler) — `tau_ms`, `eta`, `target_rate_hz`. Traces $x_{\text{pre}}$, $x_{\text{post}}$ (τ), each +1 per spike. $\alpha = 2\,(r_{\text{target}}/1000)\,\tau$ (dimensionless).
- Pre arrival: $\delta e = \eta\,(x_{\text{post}} - \alpha)$, then $x_{\text{pre}}$ += 1.
- Post spike: $\delta e = \eta\,x_{\text{pre}}$, then $x_{\text{post}}$ += 1.

**`TripletSTDP`** (Pfister–Gerstner, all-to-all) — `tau_plus_ms`, `tau_minus_ms`, `tau_x_ms`, `tau_y_ms`, `a2_plus`, `a3_plus`, `a2_minus`, `a3_minus`. Presynaptic traces $r_1$ ($\tau_+$) and $r_2$ ($\tau_x$); postsynaptic traces $o_1$ ($\tau_-$) and $o_2$ ($\tau_y$).
- Pre arrival: $\delta e = -o_1\,(A_2^- + A_3^-\,r_2)$, then $r_1$ += 1, $r_2$ += 1.
- Post spike: $\delta e = +r_1\,(A_2^+ + A_3^+\,o_2)$, then $o_1$ += 1, $o_2$ += 1.

$r_2$ and $o_2$ are read *before* their own increment.

**`BCM_Rate`** — `eta`, `tau_rate_ms`, `tau_theta_ms`, `target_rate_hz`. Rate traces $\rho_{\text{pre}}$ and $\rho_{\text{post}}$ in Hz (jump $1000/\tau_{\text{rate}}$ per spike). The sliding threshold is $\theta_M = \langle\rho_{\text{post}}^2\rangle_{\tau_\theta} / r_{\text{target}}$, updated each batch. At every batch boundary, $\delta e = \eta\,\rho_{\text{pre}}\,\rho_{\text{post}}\,(\rho_{\text{post}} - \theta_M)\cdot\Delta_p/1000$.

Between events, $e_{ij}$ decays: $\dot e = -e/\tau_{\text{trace}}$.

#### 4.4.3 Stage 2 — Ligand-gated transfer
The modulation factor of synapse $j \to (i,c)$ over batch $b$ is
$$M_{i,c} = \beta_0 + \sum_{m} g_m\big(\bar C_{i,c,\text{ligand}(m)} - C^{\text{ref}}_{m,i,c}\big)$$
$\bar C$ is the pool concentration averaged over the batch (the engine accumulates a per-pool sum each step). $\beta_0$ and $g_m$ are in ms⁻¹ and ms⁻¹·c.u.⁻¹ respectively. $M$ is held constant over the batch and the continuous rule $\dot w = M\,e$ is integrated **exactly**.

The engine keeps a per-synapse running integral $E_{ij} = \int e\,dt$ over the current batch. On every trace event at time $t$, and at the batch boundary:
```
h      = t - t_last
decay  = exp(-h / τ_trace)
E     += e · τ_trace · (1 - decay)
e      = e · decay  (+ δe if this is an event)
t_last = t
```
At the batch boundary: $w \leftarrow \text{clamp}(w + M\,E,\ w_{\min},\ w_{\max})$, then $E \leftarrow 0$. The trace $e$ carries over.

**Effective gains.** One coincidence $\delta e$ with no modulation eventually transfers $\beta_0\,\tau_{\text{trace}}\,\delta e$. A ligand deviation $\Delta\bar C$ held for $T$ ms transfers about $g\,\Delta\bar C\,T\,e$.

| Recipe | Settings | Behaviour |
| :--- | :--- | :--- |
| Pure STDP | `trace_tau_ms: 1.0`, `base_transfer_rate: 1.0`, `modulator_couplings: []` | $\beta_0\tau = 1$, so each $\delta e$ goes into $w$ unchanged. |
| Three-factor RL | `trace_tau_ms` ≈ 1000, `base_transfer_rate` ≤ $0.05/\tau$, coupling to a reward ligand with a `RunningAverage` reference | Ungated drift ≤ 5% of a coincidence. Bursts potentiate tagged synapses; pauses depress them. |
| Multi-ligand gating | Several couplings | Positive and negative gains combine linearly. |

As in standard R-STDP, a negative modulation combined with a negative trace gives *potentiation*.

### 4.5 `short_term_dynamics`

```json
"Depressing_Glu": { "model": "TsodyksMarkram", "U_release_prob": 0.5, "tau_recovery_ms": 800.0, "tau_facilitation_ms": 20.0 }
```
State $(x, u)$ is kept **per presynaptic neuron per projection**. This is exact because all synapses of a projection share the rule and are updated at spike emission. Between spikes, $x \to 1$ with $\tau_{\text{rec}}$ and $u \to U$ with $\tau_{\text{facil}}$ (exact exponentials). At a spike:
$$u \leftarrow u + U(1 - u), \qquad r^{\text{STP}} = u\,x, \qquad x \leftarrow x - r^{\text{STP}}$$
The value $r^{\text{STP}}$ travels with the spike event to every synapse of the projection. Initial state: $x = 1$, $u = U$.

### 4.6 `cell_types`

| Field | Meaning |
| :--- | :--- |
| `model` | `NeuronDynamicsModel`. |
| `compartments` | See [§3.6](#36-neurondynamicsmodel). |
| `params` | Model parameters (below). |
| `dendrite` | Required for `Izhikevich_2C`; not allowed otherwise. |
| `parameter_jitter` | $j \ge 0$. Per neuron, each `params` entry except `v_peak_mv`, `v_thresh_mv` and `refractory_ms` is set to $p(1 + j\xi)$, with $\xi \sim \mathcal N(0,1)$ truncated to $[-3, 3]$. |
| `intrinsic_current` | `IntrinsicCurrentType` object, injected into the soma. |
| `homeostasis` | `{ "enabled": false }`, or the full object below. |
| `structural_plasticity` | Optional; see [§4.8](#48-structural-plasticity). |

Every model has `refractory_ms`. After a spike, $V_{\text{soma}}$ is held at the reset value for that long; the other state variables keep evolving.

**`Izhikevich_1C`** — `a`, `b`, `c`, `d`, `v_peak_mv`, `refractory_ms`:
$$\dot v = 0.04v^2 + 5v + 140 - u + I_{\text{tot}}, \qquad \dot u = a(bv - u)$$
When $v \ge v_{\text{peak}}$: spike, $v \leftarrow c$, $u \leftarrow u + d\cdot F_{\text{SpikeAdaptation}}$.

**`Izhikevich_2C`** — the same `params` for the soma, plus `dendrite`: `coupling_g` ($g_c$, ms⁻¹), `tau_ms` ($\tau_d$), `e_leak_mv`, `bap_kick_mv` (default 0), and optional `plateau` {`g_max`, `v_half_mv`, `slope_mv`, `reversal_potential_mv`}:
$$\dot v_s = 0.04v_s^2 + 5v_s + 140 - u + I_{\text{tot},s} + g_c F_{\text{DC}}(v_d - v_s)$$
$$\dot v_d = -\frac{v_d - E_L}{\tau_d} + I_{\text{tot},d} + g_c F_{\text{DC}}(v_s - v_d) + g_p\,\sigma\!\left(\frac{v_d - v_{1/2}}{k_p}\right)(E_p - v_d)$$
$\sigma$ is the logistic function and $F_{\text{DC}}$ is the `DendriticCoupling` factor. On a somatic spike, $v_d$ += `bap_kick_mv`.

**`AdEx`** — `tau_m_ms`, `e_leak_mv`, `v_t_mv`, `delta_t_mv`, `a` (dimensionless), `tau_w_ms`, `b` (mV), `v_reset_mv`, `v_peak_mv`, `refractory_ms`:
$$\dot V = \frac{-(V - E_L) + \Delta_T e^{(V - V_T)/\Delta_T} - w}{\tau_m} + I_{\text{tot}}, \qquad \tau_w\dot w = a(V - E_L) - w$$
When $V \ge v_{\text{peak}}$: $V \leftarrow V_{\text{reset}}$, $w \leftarrow w + b\cdot F_{\text{SpikeAdaptation}}$.

**`LIF`** — `tau_m_ms`, `e_leak_mv`, `v_thresh_mv`, `v_reset_mv`, `refractory_ms`:
$$\dot V = -(V - E_L)/\tau_m + I_{\text{tot}}$$
Spike and reset at $v_{\text{thresh}}$.

**Total current per compartment:**
$$I_{\text{tot}} = F_{\text{ME}}\,(I_{\text{syn}} + I_{\text{gap}} + I_{\text{sensory}}) + I_{\text{int}} + I_{\text{h}}$$
$I_{\text{int}}$ and $I_{\text{h}}$ go to the soma only. Voltage kicks (Poisson sensory, shot noise) are added directly to $V$ and are not scaled.

**Homeostasis** — `target_rate_hz`, `rate_estimate_tau_ms` (default 1000), `adaptation_tau_ms`, `bias_gain` (cu per Hz, default 0.5), `max_bias_current` (default 5.0). Rate trace $\hat r$ in Hz (jump $1000/\tau_{\text{est}}$ per spike). A somatic bias current is integrated each step and clamped to $\pm$`max_bias_current`:
$$\dot I_h = \frac{\text{bias\_gain}\,\big(r_{\text{target}}F_{\text{HSP}} - \hat r\big)}{\tau_{\text{adapt}}}$$

### 4.7 `nuclei`, Placement & Projections

| Nucleus field | Meaning |
| :--- | :--- |
| `id` | Unique. |
| `coordinates_mm` | Sphere centre. |
| `radius_mm` | Sphere radius > 0. |
| `size` | Total neuron count. |
| `composition[]` | `cell_type`, `fraction`, `receptors` (map: compartment → list of receptor IDs; may be `{}`). Fractions sum to 1 (±1e-6). A cell type appears at most once per nucleus. |
| `gap_junctions[]` | Optional: `between_type`, `topology` (any `TopologyType`), `conductance` (ms⁻¹). |
| `projections[]` | Efferent projections; may be empty. |

Population sizes are $\lfloor \text{size}\cdot f \rfloor$, with the remainder handed out by the largest-remainder method (ties go to the earlier composition entry).

#### 4.7.1 Placement & normalised coordinates
Each neuron is placed uniformly at random inside its nucleus sphere, from the `Placement` RNG stream. Its normalised coordinate is $\hat p = (p - \text{centre})/\text{radius}$, which lies in the unit ball. `Topographic` projections and I/O channel assignment use $\hat p$; `SpatialGaussian` uses $p$.

#### 4.7.2 Projection fields

| Field | Meaning |
| :--- | :--- |
| `id` | Unique across the file. |
| `from_type` | Source population in this nucleus. |
| `to_nucleus`, `to_type` | Target population. |
| `target_compartment` | Must be one of the target cell type's `compartments`. |
| `topology` | `TopologyType` object. |
| `conduction_velocity_m_s` | > 0. |
| `synaptic_delay_ms` | Optional, default 0. Added to the conduction delay. |
| `transmitter` | Ligand ID released into the target pool. |
| `synapse.weight_distribution` | `DistributionType` object. |
| `synapse.stp_rule` | Key in `short_term_dynamics`, or `"None"`. |
| `synapse.ltp_rule` | Key in `plasticity_rules`, or `"None"`. |
| `synapse.structural_plasticity` | bool. |
| `synapse.sprout_initial_weight` | Required when `structural_plasticity` is true. |

There is no projection-level receptor list. A release activates **every** receptor for that ligand expressed in the target compartment.

**Delay.** $\text{delay} = \lVert p_i - p_j\rVert / v + \text{synaptic\_delay}$, quantised to $\max(1, \text{round}(\text{delay}/dt))$ steps. The spike ring buffer holds at least max steps + 1 slots.

**Gap junctions.** Sampled once per unordered pair, symmetric, soma only:
$$I_{\text{gap},i} = \sum_j g\,(V_j - V_i)$$
Use voltages from the start of the step.

### 4.8 Structural Plasticity

Cell-type object: `max_incoming_synapses` (all incoming synapses from every projection), `prune_weight_threshold`, `sprout_probability_per_sec`, `sprout_grace_period_ms`.

At each structural update (after warmup), in this order:
1. **Prune.** Every synapse of a projection with `structural_plasticity: true`, whose weight is below `prune_weight_threshold` and whose age exceeds the grace period, is removed by swap-and-pop. Per-synapse state (w, e, E, traces, delay) moves with it. The engine **MUST NOT** keep synapse indices across a structural update.
2. **Sprout.** For each target neuron of such a projection, with probability $1 - e^{-p\,\Delta_s/1000}$ and only if the neuron's indegree is below the maximum, one candidate source is drawn uniformly from the source population. It is accepted with the projection's topology probability ($P$ for `Random`/`SpatialGaussian`/`Topographic`; 1 for `AllToAll`/`FixedIndegree`; the matching rank for `OneToOne`). Up to 16 attempts are made. Autapses, multapses and duplicates are rejected. A new synapse gets `sprout_initial_weight`, $e = 0$, fresh traces, its geometric delay, and the projection's rules.

### 4.9 External I/O Interfaces

**Channel assignment** is shared by inputs and outputs:
1. Order the target (or source) population by $\hat p$ along `channel_axis` (default 0), breaking ties by neuron index.
2. Keep the slice of the order given by `target_subrange` (or `source_subrange`) $[a, b) \subseteq [0, 1]$, default `[0, 1]`.
3. Split the slice into `dimensions` contiguous blocks whose sizes differ by at most 1. Block $c$ is channel $c$.

A 1-dimensional input therefore drives the whole slice. Because `Topographic` with `axes: [0]` maps $\hat p_0$ to $\hat p_0$, channel $c$ of a nucleus projects onto channel $c$ of the target. Several inputs **MAY** overlap on the same neurons, and their effects add; the compiler warns about overlaps.

**`sensory_inputs[]`**: `id`, `target_nucleus`, `target_type`, `target_compartment`, `target_subrange`, `channel_axis`, `dimensions`, `encoding`, `min_input`, `max_input`, plus the encoding's fields from [§3.11](#311-sensoryencodingmodel). Input frames are written by the host before a step and stay in effect until overwritten.

**`motor_outputs[]`**: `id`, `source_nucleus`, `source_type`, `source_subrange`, `channel_axis`, `dimensions`, `decoding`, `output_gain`, `clamp_bounds` (optional), plus the decoding's fields from [§3.12](#312-motordecodingmodel). Outputs are readable after every step.

Modulatory nuclei are ordinary nuclei. External valence signals reach them through sensory transducers or projections. There is no special-case reward code in the engine.

---

## 5. Execution Semantics

### 5.1 Compilation order & indexing
1. Parse the whole document, then resolve and validate every reference ([§6](#6-validation-rules)).
2. Assign dense indices to ligands, receptors, rules and cell types by **ordinal (byte-wise) string sort** of their keys.
3. Global neuron indices follow `nuclei` array order, then `composition` order, contiguously. Positions are sampled in index order.
4. Build synapses projection by projection in file order, targets in ascending index order, and sources in ascending index order within each target.

### 5.2 Per-step update order
For step $n$ ($t \to t + dt$):
1. **Spike delivery.** Pop ring-buffer slot $n$. For each arriving event: add release to the pool ([§4.2](#42-neurotransmitters-ligand-pools)), then run the pre-arrival coincidence updates ([§4.4.2](#442-stage-1--coincidence-models)).
2. **Sensory injection.** Poisson and TTFS kicks to $V$; current-based encoders set $I_{\text{sensory}}$.
3. **Clearance** of every pool.
4. **Receptor activations** $a \to s$. Accumulate the batch sums of $C$. Update modulation factors $F$ (and modulation running references).
5. **Currents** $I_{\text{syn}}$, $I_{\text{gap}}$, $I_{\text{int}}$ (advance OU/shot noise), $I_h$, using state from the start of the step.
6. **Membrane integration.** `neuron_substeps` forward-Euler sub-steps of the nonlinear voltage equations with the currents held fixed. Recovery variables ($u$, $w$) use one Euler step. Detect threshold crossings, reset, apply refractoriness.
7. **Post-spike processing.** For each spiking neuron, in ascending index order: STP update and event enqueue for each outgoing projection; post-spike coincidence updates; homeostatic rate traces; motor traces.
8. If $(n+1)\,dt$ is a multiple of $\Delta_p$: **batch transfer** ([§4.4.3](#443-stage-2--ligand-gated-transfer)), then coupling-reference updates, then `BCM_Rate` batch terms.
9. If it is a multiple of $\Delta_s$: **structural update** ([§4.8](#48-structural-plasticity)).

### 5.3 Numerical requirements
- Every linear decay (pools, receptor cascades, traces, STP, OU) **MUST** use exact or exponential-Euler updates. Plain Euler on these is not conforming.
- Single precision (`float`) is sufficient for state. Timestamps **MUST** be integer step counts.

### 5.4 Determinism
- All randomness comes from a counter-based generator (Philox4x32-10), keyed by (`seed`, stream ID, entity index, step). The stream IDs are fixed: `Placement`, `Jitter`, `Topology`, `Weights`, `GapJunctions`, `IntrinsicNoise`, `SensoryEncoding`, `Structural`.
- Floating-point accumulation into shared targets (pools, gap currents) **MUST** run in a fixed order, regardless of thread scheduling. For example, accumulate per target in ascending synapse index.

---

## 6. Validation Rules

The compiler **MUST** reject a configuration with any error and **SHOULD** report every warning.

**Errors**
1. Wrong `schema_version`; a missing required field; an unknown or inapplicable property; a dictionary key equal to `"None"`.
2. A reference to an unknown ligand, receptor, rule, cell type, nucleus or population; duplicate `id`s.
3. `plasticity_update_interval_ms` not a multiple of `dt_ms`, or `structural_update_interval_ms` not a multiple of it.
4. `compartments` not allowed for the model; `dendrite` missing on `Izhikevich_2C` or present elsewhere.
5. `composition` fractions not summing to 1; a cell type repeated in one nucleus; receptor expression on a compartment the cell type does not have.
6. `target_compartment` not on the target cell type.
7. **Dead projection:** the transmitter is neither sensed by a receptor in the target compartment nor read by a modulator coupling of a plastic projection into that same compartment.
8. `cellular_modulation` missing on a `MetabotropicLinearGain` receptor or present on a conductance receptor; `g_max` missing on a conductance receptor.
9. `ExponentialDecay` without `clearance_tau_ms`; `MichaelisMenten` without `v_max`/`k_m`; both kinds of field present.
10. **Michaelis–Menten divergence:** for any pool, the worst-case sustained release $\sum_{\text{proj}} \bar K \cdot (r_{\max}/1000)\cdot w_{\text{upper}}\cdot q \ge V_{\max}$. Here $\bar K$ is the realised mean indegree, $r_{\max}$ is `validation_max_rate_hz`, and $w_{\text{upper}}$ is `w_max` (plastic) or the largest initial weight (static).
11. `FixedIndegree` with $k > N_{\text{src}}$; `OneToOne` with unequal sizes.
12. `structural_plasticity: true` on a projection whose target cell type has no `structural_plasticity` object, or without `sprout_initial_weight`.
13. `Uniform` with min > max; a non-positive `std`, `sigma`, `tau` or radius; `w_min > w_max`; `min_input >= max_input`.

**Warnings**
1. An expressed receptor whose ligand pool never receives release and has `baseline_ambient` = 0 (never activated).
2. A modulator coupling whose ligand is never released into the synapse's target compartment (coupling is inert).
3. A population with no inbound drive (no afferent projection, sensory input or intrinsic current), or with no efferent projection and no motor readout (dead end).
4. More than 1% of initial weight mass clipped by `w_min`/`w_max`.
5. Realised mean indegree < 1 for any projection.
6. A modulation target with no effect on the model (`SpikeAdaptation` on `LIF`, `DendriticCoupling` on a single-compartment cell).
7. Overlapping sensory subranges on one population.
8. A three-factor rule with $\beta_0\,\tau_{\text{trace}} > 0.1$ (large ungated drift).

The compiler **SHOULD** print a per-projection table of realised synapse counts, mean/min/max indegree, and delay range.

---

## 7. Complete Reference Example

The canonical file is [`examples/brain.json`](../examples/brain.json). It is reproduced below and must stay byte-identical.

It implements a **self-organising conditioned avoidance and motor control loop**:
1. **`aras_core`** pacemakers keep a tonic cholinergic (`ACh`) arousal tone on cortical apical dendrites (`M1_Muscarinic` → `MembraneExcitability`). Cortical activity feeds back onto ARAS interneurons, which inhibit the pacemakers. This is a negative-feedback arousal loop.
2. **`sensory_thalamus_vpl`** receives 64 somatosensory channels (subrange 0–0.8) and 8 proprioceptive channels (subrange 0.8–1.0), with local feedforward inhibition. It relays topographically to **`cortex_S1_M1`**.
3. **`cortex_S1_M1`** has recurrent excitation (three-factor STDP, structural plasticity), E→I drive onto basket cells, perisomatic inhibition with iSTDP, mutual inhibition, and electrically coupled basket cells. It projects to the motor pool along axis 0, so channel identity is preserved.
4. **`nociceptive_relay`** receives an 8-channel error signal. It triggers an **innate reflex** (static topographic arc onto the matching motor channels). It also drives **`vta_modulator`** interneurons, which **inhibit the DA pacemakers**: a DA *dip* below the running reference depresses recently tagged synapses.
5. **`appetitive_reward_input`** depolarises the VTA pacemakers: a DA *burst* above the reference consolidates tagged synapses. DA reaches **both** the cortical apical pools (recurrent synapses) and the spinal somatic pools (corticospinal synapses). That is where the eligibility traces of the motor pathway live.
6. **`motor_ventral_horn`** has Renshaw-like recurrent inhibition. Its 8 channels are decoded as rate traces normalised to 50 Hz.

Realised connectivity of this example, from a 200-target Monte Carlo sample of the placement model:

| Projection | Mean indegree (min–max) | Mean delay (ms) |
| :--- | :--- | :--- |
| `aras_cholinergic_tone` | 20 | 31.5 |
| `aras_local_inhibition` | 30 | 4.2 |
| `mesocortical_dopamine_projection` | 20 | 36.9 |
| `mesospinal_dopamine_projection` | 20 | 36.4 |
| `vta_local_inhibition` | 36 | 2.9 |
| `thalamocortical_lemniscal_tract` | 26 (14–40) | 4.0 |
| `thalamic_relay_to_interneuron` | 80 | 3.1 |
| `thalamic_feedforward_inhibition` | 40 | 6.2 |
| `innate_withdrawal_reflex_arc` | 9.8 (1–13) | 2.1 |
| `aversive_vta_suppression` | 40 | 2.9 |
| `cortical_recurrent_association` | 53 (29–81) | 3.4 |
| `cortical_excitation_of_interneurons` | 37 (21–51) | 3.5 |
| `L23_perisomatic_inhibition` | 23 (12–37) | 5.1 |
| `interneuron_mutual_inhibition` | 14 (7–21) | 5.1 |
| `corticospinal_pyramidal_tract` | 59 (9–74) | 4.3 |
| `corticofugal_aras_feedback` | 40 | 12.6 |
| `motor_recurrent_collaterals` | 80 | 1.5 |
| `recurrent_motor_inhibition` | 20 | 1.5 |

The longest delay is about 37 ms (VTA → cortex), so the ring buffer needs at least 75 slots at `dt` = 0.5 ms.

Worst-case DA release per pool is 20 × 0.1 ms⁻¹ × 1.0 × 0.002 = 0.004 c.u./ms, below $V_{\max}$ = 0.005, so the pool is bounded. At tonic 5 Hz the DA pool sits about 0.008 above ambient, and a 20 Hz burst lifts it about 0.04. ACh settles at about 20 × 0.005 × 0.0025 × 400 ≈ 0.1 above ambient at 5 Hz.

The example raises no errors and no warnings under [§6](#6-validation-rules). Absolute `g_max` values and input gains are order-of-magnitude starting points (one AMPA release at $w = 1$ gives about 1 mV of depolarising charge) and are expected to be tuned against simulation.

```json
{
  "meta": {
    "schema_version": "4.3",
    "name": "Closed-Loop-Conditioned-Motor-Brain",
    "seed": 1337
  },
  "simulation": {
    "dt_ms": 0.5,
    "neuron_substeps": 2,
    "plasticity_update_interval_ms": 10.0,
    "structural_update_interval_ms": 1000.0,
    "plasticity_warmup_ms": 15000.0,
    "default_resting_potential_mv": -65.0,
    "validation_max_rate_hz": 100.0
  },
  "neurotransmitters": {
    "Glu": {
      "clearance_model": "ExponentialDecay",
      "baseline_ambient": 0.0,
      "clearance_tau_ms": 1.2,
      "quantal_release": 1.0
    },
    "GABA": {
      "clearance_model": "ExponentialDecay",
      "baseline_ambient": 0.0,
      "clearance_tau_ms": 2.0,
      "quantal_release": 1.0
    },
    "ACh": {
      "clearance_model": "ExponentialDecay",
      "baseline_ambient": 0.2,
      "clearance_tau_ms": 400.0,
      "quantal_release": 0.0025
    },
    "DA": {
      "clearance_model": "MichaelisMenten",
      "baseline_ambient": 0.1,
      "v_max": 0.005,
      "k_m": 0.2,
      "quantal_release": 0.002
    }
  },
  "receptors": {
    "AMPA": {
      "ligand": "Glu",
      "kinetics": "DualExponentialConductance",
      "g_max": 0.015,
      "reversal_potential_mv": 0.0,
      "tau_rise_ms": 0.2,
      "tau_decay_ms": 2.0
    },
    "NMDA": {
      "ligand": "Glu",
      "kinetics": "VoltageGatedConductance",
      "g_max": 0.004,
      "reversal_potential_mv": 0.0,
      "tau_rise_ms": 2.0,
      "tau_decay_ms": 100.0,
      "mg_block_conc_mm": 1.0
    },
    "GABA_A": {
      "ligand": "GABA",
      "kinetics": "DualExponentialConductance",
      "g_max": 0.02,
      "reversal_potential_mv": -70.0,
      "tau_rise_ms": 0.5,
      "tau_decay_ms": 6.0
    },
    "GABA_B": {
      "ligand": "GABA",
      "kinetics": "DualExponentialConductance",
      "g_max": 0.002,
      "reversal_potential_mv": -90.0,
      "tau_rise_ms": 30.0,
      "tau_decay_ms": 200.0
    },
    "M1_Muscarinic": {
      "ligand": "ACh",
      "kinetics": "MetabotropicLinearGain",
      "tau_rise_ms": 20.0,
      "tau_decay_ms": 500.0,
      "cellular_modulation": {
        "target": "MembraneExcitability",
        "gain": 1.25,
        "reference": { "mode": "Fixed", "value": 0.2 },
        "min_factor": 0.5,
        "max_factor": 2.0
      }
    },
    "D1_Dopaminergic": {
      "ligand": "DA",
      "kinetics": "MetabotropicLinearGain",
      "tau_rise_ms": 15.0,
      "tau_decay_ms": 300.0,
      "cellular_modulation": {
        "target": "DendriticCoupling",
        "gain": 5.0,
        "reference": { "mode": "Fixed", "value": 0.1 },
        "min_factor": 0.5,
        "max_factor": 2.0
      }
    }
  },
  "plasticity_rules": {
    "Unmodulated_Sensory_STDP": {
      "coincidence_model": "AsymmetricSTDP",
      "params": {
        "tau_plus_ms": 20.0,
        "tau_minus_ms": 20.0,
        "a_plus": 0.008,
        "a_minus": 0.009
      },
      "trace_tau_ms": 1.0,
      "base_transfer_rate": 1.0,
      "modulator_couplings": [],
      "w_min": 0.0,
      "w_max": 4.0
    },
    "Cortical_ThreeFactor_STDP": {
      "coincidence_model": "AsymmetricSTDP",
      "params": {
        "tau_plus_ms": 20.0,
        "tau_minus_ms": 20.0,
        "a_plus": 0.04,
        "a_minus": 0.035
      },
      "trace_tau_ms": 1200.0,
      "base_transfer_rate": 0.00005,
      "modulator_couplings": [
        {
          "ligand": "DA",
          "reference": { "mode": "RunningAverage", "tau_ms": 5000.0 },
          "transfer_gain": 0.1
        },
        {
          "ligand": "ACh",
          "reference": { "mode": "RunningAverage", "tau_ms": 5000.0 },
          "transfer_gain": 0.005
        }
      ],
      "w_min": 0.0,
      "w_max": 6.0
    },
    "Corticospinal_ThreeFactor_STDP": {
      "coincidence_model": "AsymmetricSTDP",
      "params": {
        "tau_plus_ms": 20.0,
        "tau_minus_ms": 20.0,
        "a_plus": 0.04,
        "a_minus": 0.035
      },
      "trace_tau_ms": 1200.0,
      "base_transfer_rate": 0.00005,
      "modulator_couplings": [
        {
          "ligand": "DA",
          "reference": { "mode": "RunningAverage", "tau_ms": 5000.0 },
          "transfer_gain": 0.1
        }
      ],
      "w_min": 0.0,
      "w_max": 6.0
    },
    "Homeostatic_Inhibitory_iSTDP": {
      "coincidence_model": "SymmetricSTDP",
      "params": {
        "tau_ms": 20.0,
        "eta": 0.005,
        "target_rate_hz": 5.0
      },
      "trace_tau_ms": 1.0,
      "base_transfer_rate": 1.0,
      "modulator_couplings": [],
      "w_min": 0.1,
      "w_max": 10.0
    }
  },
  "short_term_dynamics": {
    "Depressing_Glu": {
      "model": "TsodyksMarkram",
      "U_release_prob": 0.5,
      "tau_recovery_ms": 800.0,
      "tau_facilitation_ms": 20.0
    },
    "Facilitating_Glu": {
      "model": "TsodyksMarkram",
      "U_release_prob": 0.15,
      "tau_recovery_ms": 100.0,
      "tau_facilitation_ms": 600.0
    },
    "Depressing_GABA": {
      "model": "TsodyksMarkram",
      "U_release_prob": 0.4,
      "tau_recovery_ms": 600.0,
      "tau_facilitation_ms": 10.0
    }
  },
  "cell_types": {
    "Thalamic_Relay": {
      "model": "Izhikevich_1C",
      "compartments": ["Soma"],
      "params": {
        "a": 0.02, "b": 0.25, "c": -65.0, "d": 0.05,
        "v_peak_mv": 30.0, "refractory_ms": 1.5
      },
      "parameter_jitter": 0.03,
      "intrinsic_current": { "type": "None" },
      "homeostasis": {
        "enabled": true,
        "target_rate_hz": 8.0,
        "rate_estimate_tau_ms": 1000.0,
        "adaptation_tau_ms": 5000.0,
        "bias_gain": 0.5,
        "max_bias_current": 5.0
      }
    },
    "Pyramidal_RS": {
      "model": "Izhikevich_2C",
      "compartments": ["Soma", "ApicalDendrite"],
      "params": {
        "a": 0.02, "b": 0.2, "c": -65.0, "d": 8.0,
        "v_peak_mv": 30.0, "refractory_ms": 2.0
      },
      "dendrite": {
        "coupling_g": 0.1,
        "tau_ms": 20.0,
        "e_leak_mv": -65.0,
        "bap_kick_mv": 10.0,
        "plateau": {
          "g_max": 0.05,
          "v_half_mv": -35.0,
          "slope_mv": 3.0,
          "reversal_potential_mv": 0.0
        }
      },
      "parameter_jitter": 0.05,
      "intrinsic_current": { "type": "None" },
      "homeostasis": {
        "enabled": true,
        "target_rate_hz": 4.0,
        "rate_estimate_tau_ms": 1000.0,
        "adaptation_tau_ms": 10000.0,
        "bias_gain": 0.5,
        "max_bias_current": 5.0
      },
      "structural_plasticity": {
        "max_incoming_synapses": 1000,
        "prune_weight_threshold": 0.02,
        "sprout_probability_per_sec": 0.05,
        "sprout_grace_period_ms": 5000.0
      }
    },
    "Spinal_Alpha_Motor": {
      "model": "Izhikevich_1C",
      "compartments": ["Soma"],
      "params": {
        "a": 0.02, "b": 0.2, "c": -65.0, "d": 6.0,
        "v_peak_mv": 30.0, "refractory_ms": 2.0
      },
      "parameter_jitter": 0.02,
      "intrinsic_current": { "type": "None" },
      "homeostasis": { "enabled": false },
      "structural_plasticity": {
        "max_incoming_synapses": 500,
        "prune_weight_threshold": 0.02,
        "sprout_probability_per_sec": 0.05,
        "sprout_grace_period_ms": 5000.0
      }
    },
    "Basket_FS": {
      "model": "Izhikevich_1C",
      "compartments": ["Soma"],
      "params": {
        "a": 0.1, "b": 0.2, "c": -65.0, "d": 2.0,
        "v_peak_mv": 30.0, "refractory_ms": 1.0
      },
      "parameter_jitter": 0.02,
      "intrinsic_current": { "type": "None" },
      "homeostasis": { "enabled": false }
    },
    "Tonic_Pacemaker": {
      "model": "Izhikevich_1C",
      "compartments": ["Soma"],
      "params": {
        "a": 0.02, "b": 0.25, "c": -55.0, "d": 0.05,
        "v_peak_mv": 30.0, "refractory_ms": 1.5
      },
      "parameter_jitter": 0.05,
      "intrinsic_current": {
        "type": "OrnsteinUhlenbeck",
        "mean_current": 4.0,
        "sigma_current": 1.5,
        "tau_ms": 5.0
      },
      "homeostasis": { "enabled": false }
    }
  },
  "nuclei": [
    {
      "id": "aras_core",
      "coordinates_mm": [0.0, -25.0, -15.0],
      "radius_mm": 2.0,
      "size": 1000,
      "composition": [
        { "cell_type": "Tonic_Pacemaker", "fraction": 0.85, "receptors": { "Soma": ["GABA_A"] } },
        { "cell_type": "Basket_FS", "fraction": 0.15, "receptors": { "Soma": ["AMPA"] } }
      ],
      "projections": [
        {
          "id": "aras_cholinergic_tone",
          "from_type": "Tonic_Pacemaker",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Pyramidal_RS",
          "target_compartment": "ApicalDendrite",
          "topology": { "type": "FixedIndegree", "k": 20 },
          "conduction_velocity_m_s": 2.0,
          "transmitter": "ACh",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": 0.0, "sigma": 0.2 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "aras_local_inhibition",
          "from_type": "Basket_FS",
          "to_nucleus": "aras_core",
          "to_type": "Tonic_Pacemaker",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.2 },
          "conduction_velocity_m_s": 0.5,
          "transmitter": "GABA",
          "synapse": {
            "weight_distribution": { "type": "Gaussian", "mean": 1.0, "std": 0.1 },
            "stp_rule": "Depressing_GABA",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        }
      ]
    },
    {
      "id": "vta_modulator",
      "coordinates_mm": [0.0, -18.0, -10.0],
      "radius_mm": 1.5,
      "size": 600,
      "composition": [
        { "cell_type": "Tonic_Pacemaker", "fraction": 0.80, "receptors": { "Soma": ["GABA_A", "GABA_B"] } },
        { "cell_type": "Basket_FS", "fraction": 0.20, "receptors": { "Soma": ["AMPA"] } }
      ],
      "projections": [
        {
          "id": "mesocortical_dopamine_projection",
          "from_type": "Tonic_Pacemaker",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Pyramidal_RS",
          "target_compartment": "ApicalDendrite",
          "topology": { "type": "FixedIndegree", "k": 20 },
          "conduction_velocity_m_s": 1.5,
          "transmitter": "DA",
          "synapse": {
            "weight_distribution": { "type": "Constant", "value": 1.0 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "mesospinal_dopamine_projection",
          "from_type": "Tonic_Pacemaker",
          "to_nucleus": "motor_ventral_horn",
          "to_type": "Spinal_Alpha_Motor",
          "target_compartment": "Soma",
          "topology": { "type": "FixedIndegree", "k": 20 },
          "conduction_velocity_m_s": 1.5,
          "transmitter": "DA",
          "synapse": {
            "weight_distribution": { "type": "Constant", "value": 1.0 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "vta_local_inhibition",
          "from_type": "Basket_FS",
          "to_nucleus": "vta_modulator",
          "to_type": "Tonic_Pacemaker",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.3 },
          "conduction_velocity_m_s": 0.5,
          "transmitter": "GABA",
          "synapse": {
            "weight_distribution": { "type": "Gaussian", "mean": 1.5, "std": 0.2 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        }
      ]
    },
    {
      "id": "sensory_thalamus_vpl",
      "coordinates_mm": [8.0, -15.0, 5.0],
      "radius_mm": 3.0,
      "size": 2000,
      "composition": [
        { "cell_type": "Thalamic_Relay", "fraction": 0.80, "receptors": { "Soma": ["GABA_A", "GABA_B"] } },
        { "cell_type": "Basket_FS", "fraction": 0.20, "receptors": { "Soma": ["AMPA"] } }
      ],
      "projections": [
        {
          "id": "thalamocortical_lemniscal_tract",
          "from_type": "Thalamic_Relay",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Pyramidal_RS",
          "target_compartment": "Soma",
          "topology": { "type": "Topographic", "sigma_rel": 0.25, "max_prob": 0.4, "axes": [0, 1, 2] },
          "conduction_velocity_m_s": 10.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": 0.3, "sigma": 0.3 },
            "stp_rule": "Depressing_Glu",
            "ltp_rule": "Unmodulated_Sensory_STDP",
            "structural_plasticity": false
          }
        },
        {
          "id": "thalamic_relay_to_interneuron",
          "from_type": "Thalamic_Relay",
          "to_nucleus": "sensory_thalamus_vpl",
          "to_type": "Basket_FS",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.05 },
          "conduction_velocity_m_s": 1.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": 0.0, "sigma": 0.3 },
            "stp_rule": "Depressing_Glu",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "thalamic_feedforward_inhibition",
          "from_type": "Basket_FS",
          "to_nucleus": "sensory_thalamus_vpl",
          "to_type": "Thalamic_Relay",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.1 },
          "conduction_velocity_m_s": 0.5,
          "transmitter": "GABA",
          "synapse": {
            "weight_distribution": { "type": "Gaussian", "mean": 1.0, "std": 0.1 },
            "stp_rule": "Depressing_GABA",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        }
      ]
    },
    {
      "id": "nociceptive_relay",
      "coordinates_mm": [4.0, -28.0, -20.0],
      "radius_mm": 1.0,
      "size": 400,
      "composition": [
        { "cell_type": "Thalamic_Relay", "fraction": 1.0, "receptors": {} }
      ],
      "projections": [
        {
          "id": "innate_withdrawal_reflex_arc",
          "from_type": "Thalamic_Relay",
          "to_nucleus": "motor_ventral_horn",
          "to_type": "Spinal_Alpha_Motor",
          "target_compartment": "Soma",
          "topology": { "type": "Topographic", "sigma_rel": 0.08, "max_prob": 0.2, "axes": [0] },
          "conduction_velocity_m_s": 20.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "Constant", "value": 1.5 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "aversive_vta_suppression",
          "from_type": "Thalamic_Relay",
          "to_nucleus": "vta_modulator",
          "to_type": "Basket_FS",
          "target_compartment": "Soma",
          "topology": { "type": "FixedIndegree", "k": 40 },
          "conduction_velocity_m_s": 5.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "Constant", "value": 1.0 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        }
      ]
    },
    {
      "id": "cortex_S1_M1",
      "coordinates_mm": [15.0, 10.0, 35.0],
      "radius_mm": 5.0,
      "size": 10000,
      "composition": [
        {
          "cell_type": "Pyramidal_RS",
          "fraction": 0.80,
          "receptors": {
            "Soma": ["AMPA", "NMDA", "GABA_A"],
            "ApicalDendrite": ["AMPA", "NMDA", "M1_Muscarinic", "D1_Dopaminergic"]
          }
        },
        { "cell_type": "Basket_FS", "fraction": 0.20, "receptors": { "Soma": ["AMPA", "NMDA", "GABA_A"] } }
      ],
      "gap_junctions": [
        {
          "between_type": "Basket_FS",
          "topology": { "type": "SpatialGaussian", "sigma_mm": 0.6, "max_prob": 0.4 },
          "conductance": 0.005
        }
      ],
      "projections": [
        {
          "id": "cortical_recurrent_association",
          "from_type": "Pyramidal_RS",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Pyramidal_RS",
          "target_compartment": "ApicalDendrite",
          "topology": { "type": "SpatialGaussian", "sigma_mm": 1.5, "max_prob": 0.1, "allow_autapses": false },
          "conduction_velocity_m_s": 1.5,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": -0.5, "sigma": 0.5 },
            "stp_rule": "Depressing_Glu",
            "ltp_rule": "Cortical_ThreeFactor_STDP",
            "structural_plasticity": true,
            "sprout_initial_weight": 0.1
          }
        },
        {
          "id": "cortical_excitation_of_interneurons",
          "from_type": "Pyramidal_RS",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Basket_FS",
          "target_compartment": "Soma",
          "topology": { "type": "SpatialGaussian", "sigma_mm": 1.0, "max_prob": 0.2 },
          "conduction_velocity_m_s": 1.5,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": 0.0, "sigma": 0.3 },
            "stp_rule": "Depressing_Glu",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "L23_perisomatic_inhibition",
          "from_type": "Basket_FS",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Pyramidal_RS",
          "target_compartment": "Soma",
          "topology": { "type": "SpatialGaussian", "sigma_mm": 1.0, "max_prob": 0.5 },
          "conduction_velocity_m_s": 1.0,
          "transmitter": "GABA",
          "synapse": {
            "weight_distribution": { "type": "Gaussian", "mean": 2.5, "std": 0.3 },
            "stp_rule": "Depressing_GABA",
            "ltp_rule": "Homeostatic_Inhibitory_iSTDP",
            "structural_plasticity": false
          }
        },
        {
          "id": "interneuron_mutual_inhibition",
          "from_type": "Basket_FS",
          "to_nucleus": "cortex_S1_M1",
          "to_type": "Basket_FS",
          "target_compartment": "Soma",
          "topology": { "type": "SpatialGaussian", "sigma_mm": 1.0, "max_prob": 0.3, "allow_autapses": false },
          "conduction_velocity_m_s": 1.0,
          "transmitter": "GABA",
          "synapse": {
            "weight_distribution": { "type": "Gaussian", "mean": 1.0, "std": 0.1 },
            "stp_rule": "Depressing_GABA",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "corticospinal_pyramidal_tract",
          "from_type": "Pyramidal_RS",
          "to_nucleus": "motor_ventral_horn",
          "to_type": "Spinal_Alpha_Motor",
          "target_compartment": "Soma",
          "topology": { "type": "Topographic", "sigma_rel": 0.1, "max_prob": 0.05, "axes": [0] },
          "conduction_velocity_m_s": 25.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": -0.2, "sigma": 0.4 },
            "stp_rule": "Facilitating_Glu",
            "ltp_rule": "Corticospinal_ThreeFactor_STDP",
            "structural_plasticity": true,
            "sprout_initial_weight": 0.1
          }
        },
        {
          "id": "corticofugal_aras_feedback",
          "from_type": "Pyramidal_RS",
          "to_nucleus": "aras_core",
          "to_type": "Basket_FS",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.005 },
          "conduction_velocity_m_s": 5.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": 0.0, "sigma": 0.1 },
            "stp_rule": "Facilitating_Glu",
            "ltp_rule": "Unmodulated_Sensory_STDP",
            "structural_plasticity": false
          }
        }
      ]
    },
    {
      "id": "motor_ventral_horn",
      "coordinates_mm": [2.0, -40.0, -60.0],
      "radius_mm": 1.5,
      "size": 500,
      "composition": [
        { "cell_type": "Spinal_Alpha_Motor", "fraction": 0.80, "receptors": { "Soma": ["AMPA", "NMDA", "GABA_A"] } },
        { "cell_type": "Basket_FS", "fraction": 0.20, "receptors": { "Soma": ["AMPA"] } }
      ],
      "projections": [
        {
          "id": "motor_recurrent_collaterals",
          "from_type": "Spinal_Alpha_Motor",
          "to_nucleus": "motor_ventral_horn",
          "to_type": "Basket_FS",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.2 },
          "conduction_velocity_m_s": 1.0,
          "transmitter": "Glu",
          "synapse": {
            "weight_distribution": { "type": "LogNormal", "mu": 0.0, "sigma": 0.2 },
            "stp_rule": "None",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        },
        {
          "id": "recurrent_motor_inhibition",
          "from_type": "Basket_FS",
          "to_nucleus": "motor_ventral_horn",
          "to_type": "Spinal_Alpha_Motor",
          "target_compartment": "Soma",
          "topology": { "type": "Random", "probability": 0.2 },
          "conduction_velocity_m_s": 1.0,
          "transmitter": "GABA",
          "synapse": {
            "weight_distribution": { "type": "Gaussian", "mean": 1.0, "std": 0.1 },
            "stp_rule": "Depressing_GABA",
            "ltp_rule": "None",
            "structural_plasticity": false
          }
        }
      ]
    }
  ],
  "io_interfaces": {
    "sensory_inputs": [
      {
        "id": "somatosensory_mechanoreceptors",
        "target_nucleus": "sensory_thalamus_vpl",
        "target_type": "Thalamic_Relay",
        "target_compartment": "Soma",
        "target_subrange": [0.0, 0.8],
        "channel_axis": 0,
        "dimensions": 64,
        "encoding": "PoissonRate",
        "min_input": 0.0,
        "max_input": 1.0,
        "min_rate_hz": 0.0,
        "max_rate_hz": 120.0,
        "injection_weight_mv": 8.0
      },
      {
        "id": "proprioceptive_muscle_spindles",
        "target_nucleus": "sensory_thalamus_vpl",
        "target_type": "Thalamic_Relay",
        "target_compartment": "Soma",
        "target_subrange": [0.8, 1.0],
        "channel_axis": 0,
        "dimensions": 8,
        "encoding": "PopulationGaussianReceptiveField",
        "min_input": -1.0,
        "max_input": 1.0,
        "receptive_field_sigma": 0.15,
        "gain_current": 6.5
      },
      {
        "id": "nociceptive_error_input",
        "target_nucleus": "nociceptive_relay",
        "target_type": "Thalamic_Relay",
        "target_compartment": "Soma",
        "target_subrange": [0.0, 1.0],
        "channel_axis": 0,
        "dimensions": 8,
        "encoding": "PoissonRate",
        "min_input": 0.0,
        "max_input": 1.0,
        "min_rate_hz": 0.0,
        "max_rate_hz": 200.0,
        "injection_weight_mv": 12.0
      },
      {
        "id": "appetitive_reward_input",
        "target_nucleus": "vta_modulator",
        "target_type": "Tonic_Pacemaker",
        "target_compartment": "Soma",
        "target_subrange": [0.0, 1.0],
        "channel_axis": 0,
        "dimensions": 1,
        "encoding": "DirectCurrent",
        "min_input": 0.0,
        "max_input": 1.0,
        "min_current": 0.0,
        "max_current": 10.0
      }
    ],
    "motor_outputs": [
      {
        "id": "upper_limb_muscle_synergies",
        "source_nucleus": "motor_ventral_horn",
        "source_type": "Spinal_Alpha_Motor",
        "source_subrange": [0.0, 1.0],
        "channel_axis": 0,
        "dimensions": 8,
        "decoding": "ExponentialRateTrace",
        "tau_trace_ms": 30.0,
        "rate_normalization_hz": 50.0,
        "output_gain": 1.0,
        "clamp_bounds": [0.0, 1.0]
      }
    ]
  }
}
```
