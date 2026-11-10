# `brain.json` Architecture & Configuration Specification (v4.3)

This document defines the declarative schema for the **Pure Core Neural Simulation Engine**. The engine is purely mathematical and has no built-in biological names. Anatomy, chemical kinetics, eligibility-trace pipelines, ligand-gated plasticity, network topology and sensory/motor transducers all come from configuration documents.

A brain can be split into reusable **modules**: separate files for a region, a neuromodulator system or a shared library. A new region (amygdala, hippocampus, an attractor network) is added by including its module. Existing files are never edited ([§5](#5-modules--composition)).

The keywords **MUST**, **MUST NOT**, **SHOULD** and **MAY** are used as in RFC 2119. A conforming engine produces bit-identical results for the same documents, seed, input stream and control stream, whatever its thread count ([§6.4](#64-determinism)).

---

## Table of Contents
1. [Root Schema Overview](#1-root-schema-overview)
2. [Units & Conventions](#2-units--conventions)
3. [Enum Reference Index](#3-enum-reference-index)
4. [Detailed Section Specifications](#4-detailed-section-specifications)
   - [4.1 Meta & Simulation](#41-meta--simulation)
   - [4.2 Neurotransmitters (Ligand Pools)](#42-neurotransmitters-ligand-pools)
   - [4.3 Receptors](#43-receptors)
   - [4.4 Plasticity Rules](#44-plasticity_rules)
   - [4.5 Short-Term Dynamics](#45-short_term_dynamics)
   - [4.6 Cell Types](#46-cell_types)
   - [4.7 Nuclei & Populations](#47-nuclei--populations)
   - [4.8 Projections](#48-projections)
   - [4.9 Structural Plasticity & Neurogenesis](#49-structural-plasticity--neurogenesis)
   - [4.10 External I/O Interfaces](#410-external-io-interfaces)
   - [4.11 Recording](#411-recording)
   - [4.12 Runtime Controls](#412-runtime-controls)
5. [Modules & Composition](#5-modules--composition)
6. [Execution Semantics](#6-execution-semantics)
7. [Validation Rules](#7-validation-rules)
8. [Reference Examples](#8-reference-examples)

---

## 1. Root Schema Overview

A **document** is a JSON object with these top-level properties:

```json
{
  "meta": { ... },               // Versioning, naming, deterministic RNG seed
  "includes": [ ... ],           // Other documents (modules) merged into this one
  "simulation": { ... },         // Clock rates and global constants
  "neurotransmitters": { ... },  // Abstract ligands and clearance kinetics
  "receptors": { ... },          // Conductance channels and cellular modulation
  "plasticity_rules": { ... },   // Coincidence -> Trace -> Ligand-gated weight transfer
  "short_term_dynamics": { ... },// Presynaptic depression / facilitation
  "cell_types": { ... },         // Neuron and compartment dynamics
  "nuclei": [ ... ],             // Regions, populations, gap junctions, embedded projections
  "projections": [ ... ],        // Free-standing projections between any nuclei
  "augment": { ... },            // Additive changes to populations defined elsewhere
  "io_interfaces": { ... },      // Sensory encoders and motor decoders
  "recording": { ... },          // What to observe
  "runtime_controls": [ ... ]    // Named host-settable experiment controls
}
```

The **root document** is the one handed to the compiler. After all includes are merged ([§5](#5-modules--composition)), the result **MUST** contain `meta`, `simulation`, `neurotransmitters`, `receptors`, `plasticity_rules`, `short_term_dynamics`, `cell_types`, a non-empty `nuclei` and `io_interfaces`. Any individual document **MAY** contain any subset of the sections.

JSON object members are unordered (RFC 8259). The engine **MUST NOT** depend on member order. Cross-references are resolved after all documents are merged. Unknown properties, and properties that don't apply to the selected model or enum value, are validation **errors**, so typos are never silently ignored.

**Identifiers** (dictionary keys, `id` fields, population names) match `^[A-Za-z_][A-Za-z0-9_]*$`. The dot `.` is reserved as the namespace separator ([§5.2](#52-namespaces--name-resolution)). `"None"` is reserved: it means "no rule" in `stp_rule` and `ltp_rule`, and **MUST NOT** be used as an identifier.

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
| Intracellular calcium | dimensionless (c.u.) | Abstract units. |
| Rate | Hz | Converted to ms⁻¹ ($r/1000$) wherever it enters a ms-based equation. |
| Distance | mm | Stereotaxic coordinates. |
| Feature-space coordinates | arbitrary, per population | E.g. degrees of heading, metres of arena ([§4.7.4](#474-feature-space)). |
| Conduction velocity | m/s | Since 1 mm ÷ 1 m/s = 1 ms, delay in ms = distance in mm ÷ velocity in m/s. |
| Synaptic weight $w$ | dimensionless, ≥ 0 | Scales transmitter release. Excitation vs. inhibition comes **only** from the receptor's $E_{\text{rev}}$. |

**Sign convention:** every current term is written as *depolarising positive*. Synaptic current is $I_{\text{syn}} = \sum_r g_r\,B_r(V)\,(E_r - V)$.

$H(\cdot)$ is the Heaviside step, $[x]_+ = \max(0, x)$, and $\sigma(x) = 1/(1 + e^{-x})$.

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
Each modulation produces a multiplicative factor $F$ ([§4.3.5](#435-cellular-modulation)). Factors from several modulations acting on the same target multiply together.

| Value | Byte | Extra fields | Effect of factor $F$ |
| :--- | :---: | :--- | :--- |
| `None` | `0` | — | No effect. |
| `MembraneExcitability` | `1` | — | Input gain: synaptic, sensory and gap-junction current summed per compartment is multiplied by $F$. Intrinsic and homeostatic currents are not scaled. |
| `SpikeAdaptation` | `2` | — | Multiplies the post-spike adaptation increment ($d$ for Izhikevich, $b$ for AdEx). No effect on `LIF` (warning). |
| `DendriticCoupling` | `3` | `compartment` (optional) | Multiplies the axial conductance $g_c$ between `compartment` and its parent, or all couplings if omitted. No effect on single-compartment models (warning). |
| `HomeostaticSetPoint` | `4` | — | Multiplies the cell's homeostatic $r_{\text{target}}$. |
| `ReceptorConductance` | `5` | `receptor` | Multiplies $g_{\max}$ of the named conductance receptor in every compartment of the cell (e.g. D1 → NMDA enhancement). |
| `PresynapticRelease` | `6` | `projections` (optional) | Heteroreceptor at the input site. Multiplies the release of every event arriving in **the compartment where this receptor is expressed**, restricted to the listed projections if given (e.g. GABA_B presynaptic inhibition, ACh suppression of recurrent collaterals, endocannabinoid retrograde suppression). |

### 3.3 `ReceptorKineticsModel`

| Value | Byte | Description |
| :--- | :---: | :--- |
| `DualExponentialConductance` | `0` | Ionotropic: $I = g_{\max}\,s(t)\,(E_{\text{rev}} - V)$. |
| `VoltageGatedConductance` | `1` | As above, multiplied by the Mg²⁺ block $B(V)$. |
| `MetabotropicLinearGain` | `2` | Non-conducting. Its activation $s(t)$ drives one or more `cellular_modulation`s. |

$s(t)$ is the receptor activation defined in [§4.3.1](#431-activation-cascade).

### 3.4 `CoincidenceDetectionModel`

| Value | Byte | Summary (full definition in [§4.4.2](#442-stage-1--coincidence-models)) |
| :--- | :---: | :--- |
| `None` | `0` | Static synapse. Not allowed inside a plasticity rule; use `"ltp_rule": "None"` instead. |
| `AsymmetricSTDP` | `1` | Pair-based causal STDP, all-to-all pairing via traces. |
| `SymmetricSTDP` | `2` | Vogels–Sprekeler inhibitory plasticity. |
| `TripletSTDP` | `3` | Pfister–Gerstner all-to-all triplet rule. |
| `BCM_Rate` | `4` | Rate-based BCM with a sliding threshold. |
| `CalciumControl` | `5` | Calcium-threshold rule (Shouval/Graupner–Brunel family), driven by the target compartment's calcium. |
| `VoltageClopath` | `6` | Voltage-based rule (Clopath et al.), driven by the target compartment's voltage. |
| `PlateauBTSP` | `7` | Behavioural-timescale plasticity: seconds-wide window around dendritic plateau events. |

### 3.5 `ShortTermPlasticityModel`

| Value | Byte | Description |
| :--- | :---: | :--- |
| `None` | `0` | Reserved; selected with `"stp_rule": "None"`. Gives $r_{\text{STP}} = 1$. |
| `TsodyksMarkram` | `1` | Resources $x$ and utilisation $u$ ([§4.5](#45-short_term_dynamics)). |

### 3.6 `NeuronDynamicsModel`

| Value | Byte | Allowed `compartments` |
| :--- | :---: | :--- |
| `Izhikevich_1C` | `0` | `["Soma"]` |
| `Izhikevich_2C` | `1` | `["Soma", "ApicalDendrite"]` or `["Soma", "BasalDendrite"]` |
| `AdEx` | `2` | `["Soma"]` |
| `LIF` | `3` | `["Soma"]` |
| `Izhikevich_MC` | `4` | `"Soma"` plus 1–3 distinct dendritic compartments forming a tree ([§4.6.2](#462-multi-compartment-models)) |

### 3.7 `CompartmentType`

| Value | Byte | Role |
| :--- | :---: | :--- |
| `Soma` | `0` | Spike generation; target of perisomatic inhibition. |
| `ApicalDendrite` | `1` | Apical trunk / oblique dendrites; top-down and modulatory input. |
| `BasalDendrite` | `2` | Proximal tree; feedforward input. |
| `ApicalTuft` | `3` | Distal tuft; long-range input; site of plateau potentials. |

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
| `SpatialGaussian` | `4` | `sigma_mm`, `max_prob` | $P = P_{\max}\exp(-d_{ij}^2/2\sigma^2)$, $d_{ij}$ = anatomical distance. Shorthand for `Kernel` in `Anatomical` space. |
| `Topographic` | `5` | `sigma_rel`, `max_prob`, `axes` (default `[0,1,2]`) | $P = P_{\max}\exp(-\lVert\hat p_i - \hat p_j\rVert^2_{\text{axes}}/2\sigma_{\text{rel}}^2)$. Shorthand for `Kernel` in `Normalized` space. |
| `Kernel` | `6` | `space`, `axes` (default: all), `kernel`, `offset` (default 0), `max_prob` | $P = \text{clamp}(P_{\max}\,K(\delta_{ij}), 0, 1)$, where $\delta_{ij}$ is the target-minus-source displacement in `space`, minus `offset` ([§4.8.3](#483-kernels--displacements)). |
| `ExplicitList` | `7` | `path` *or* `pairs` | An exact connection list ([§4.8.4](#484-explicit-connection-lists)). |

Every topology except `ExplicitList` also accepts `allow_autapses` (default `false`). It only matters when the source and target populations are the same. Multapses (more than one synapse per pair) are never created at build time.

**Expected indegree.** For an interior target neuron, `SpatialGaussian` gives $\mathbb E[K] \approx \rho\,P_{\max}\,(2\pi\sigma^2)^{3/2}$, where $\rho$ is the source density per mm³. Neurons near a nucleus boundary get fewer. σ must be chosen for the **model's** density, not biological density. The compiler reports realised indegree statistics ([§7](#7-validation-rules)).

### 3.10 `DistributionType`

| Value | Byte | Fields | Notes |
| :--- | :---: | :--- | :--- |
| `Constant` | `0` | `value` | |
| `Uniform` | `1` | `min`, `max` | |
| `Gaussian` | `2` | `mean`, `std` | |
| `LogNormal` | `3` | `mu`, `sigma` | Parameters of the underlying normal; median $= e^{\mu}$. |

Sampled weights are multiplied by the projection's `weight_kernel` if present ([§4.8.3](#483-kernels--displacements)). They are then **clipped** to $[w_{\min}, w_{\max}]$ of the projection's `ltp_rule`, or to $[0, \infty)$ for static synapses. A synapse whose initial weight is exactly 0 *because of the weight kernel* is not created.

### 3.11 `SensoryEncodingModel`

For scalar encoders, the normalised input is $\hat x = \text{clamp}\!\left(\frac{x - x_{\min}}{x_{\max} - x_{\min}}, 0, 1\right)$, with $x_{\min}, x_{\max}$ = `min_input`, `max_input`.

| Value | Byte | Fields | Mechanism (per neuron of the channel's block) |
| :--- | :---: | :--- | :--- |
| `DirectCurrent` | `0` | `min_current`, `max_current` | $I = I_{\min} + \hat x\,(I_{\max} - I_{\min})$, held until the next input frame. |
| `PoissonRate` | `1` | `min_rate_hz`, `max_rate_hz`, `injection_weight_mv` | Independent Poisson process at $\lambda = r_{\min} + \hat x(r_{\max} - r_{\min})$. Each event adds `injection_weight_mv` to the target compartment's $V$. |
| `TimeToFirstSpike` | `2` | `window_ms`, `min_activation`, `injection_weight_mv` | At the start of each window, if $\hat x \ge$ `min_activation`, one kick is scheduled at latency $(1-\hat x)\cdot$`window_ms`, rounded to a whole step. |
| `PopulationGaussianReceptiveField` | `3` | `receptive_field_sigma`, `gain_current` | The $n$ neurons of the block get preferred values $\mu_k = x_{\min} + \frac{k + 0.5}{n}(x_{\max} - x_{\min})$ and current $I_k = \text{gain}\cdot\exp(-(x - \mu_k)^2 / 2\sigma^2)$, where σ is in raw input units and $x$ is clamped to $[x_{\min}, x_{\max}]$. |
| `MultiDimGaussianReceptiveField` | `4` | `receptive_field_sigma`, `gain_current`, `centers`, `periodic` (optional) | The input is **one $d$-dimensional vector**, where $d$ = `dimensions` (e.g. arena $x, y$ or heading). The whole slice is a single block; neuron $k$ has a centre $\boldsymbol\mu_k$ and gets $I_k = \text{gain}\cdot\exp\!\big(-\tfrac12\sum_a (\delta_a/\sigma_a)^2\big)$. See [§4.10.2](#4102-multi-dimensional-receptive-fields). |

### 3.12 `MotorDecodingModel`

Each source neuron $i$ keeps a rate trace $y_i$ in Hz. It decays with `tau_trace_ms` and jumps by $1000/\tau_{\text{trace}}$ on each spike, so it estimates the firing rate. A channel's activity is $\bar y_c = \frac{1}{n_c}\sum_{i \in c} y_i$.

| Value | Byte | Fields | Output |
| :--- | :---: | :--- | :--- |
| `ExponentialRateTrace` | `0` | `tau_trace_ms`, `rate_normalization_hz` | $o_c = \text{gain}\cdot\bar y_c / r_{\text{norm}}$ |
| `PopulationVector` | `1` | `tau_trace_ms`, `rate_normalization_hz`, `preferred_directions` | $\mathbf o = \text{gain}\cdot\frac{1}{N}\sum_i (y_i / r_{\text{norm}})\,\mathbf p_i$; `dimensions` must be 2 or 3. `preferred_directions` is `"UniformCircle"`, `"UniformSphere"` (spread evenly by rank; Fibonacci lattice for the sphere), `"FeatureSpace"` (1-D periodic feature coordinate φ of period $L$ → $\mathbf p = (\cos 2\pi\varphi/L, \sin 2\pi\varphi/L)$), or an explicit list, one vector per neuron. |
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

### 3.14 `TransferFunctionType`
Shapes a deviation $\Delta$ (ligand or activation minus its reference). Used by `modulator_couplings[].transfer_function` and `cellular_modulation.transfer_function`. Default `Linear`.

| Value | Byte | Fields | $\phi(\Delta)$ |
| :--- | :---: | :--- | :--- |
| `Linear` | `0` | — | $\Delta$ |
| `Rectified` | `1` | `side` (`"Positive"` or `"Negative"`) | $[\Delta]_+$ for Positive, $-[-\Delta]_+$ for Negative (e.g. low-affinity receptors that see only bursts, high-affinity ones that see only dips) |
| `DeadZone` | `2` | `theta` | $\text{sign}(\Delta)\,[\lvert\Delta\rvert - \theta]_+$ |
| `Saturating` | `3` | `half_saturation` ($k$) | $\Delta / (1 + \lvert\Delta\rvert / k)$ |
| `Sigmoid` | `4` | `threshold`, `slope`, `amplitude` | $\text{amplitude}\cdot\big(\sigma((\Delta - \text{threshold})/\text{slope}) - \sigma(-\text{threshold}/\text{slope})\big)$, so that $\phi(0) = 0$ |

### 3.15 `ShapeType`
Nucleus geometry ([§4.7.1](#471-shape--placement)).

| Value | Byte | Fields | Half-extents $h$ used for normalisation |
| :--- | :---: | :--- | :--- |
| `Sphere` | `0` | `radius_mm` | $(r, r, r)$ |
| `Ellipsoid` | `1` | `radii_mm` $[a,b,c]$ | $(a, b, c)$ |
| `Box` | `2` | `size_mm` $[x,y,z]$ | $(x/2, y/2, z/2)$ |

### 3.16 `CoordinateSpace`

| Value | Byte | Coordinates | Distance |
| :--- | :---: | :--- | :--- |
| `Anatomical` | `0` | World position $p$ (mm) | Euclidean. |
| `Normalized` | `1` | $\hat p$ in the nucleus's local frame, scaled by half-extents | Euclidean. Each population uses its own nucleus's $\hat p$. |
| `Feature` | `2` | Population feature coordinates $\varphi$ ([§4.7.4](#474-feature-space)) | Per axis; periodic axes use the minimum-image difference. |

### 3.17 `KernelType`
Kernels are functions of a displacement $\delta$ with peak 1 at $\delta = 0$ unless stated.

| Value | Byte | Fields | $K(\delta)$, with $d = \lVert\delta\rVert$ |
| :--- | :---: | :--- | :--- |
| `Gaussian` | `0` | `sigma` (scalar or per-axis array) | $\exp\!\big(-\tfrac12\sum_a(\delta_a/\sigma_a)^2\big)$ |
| `DifferenceOfGaussians` | `1` | `sigma_center`, `sigma_surround`, `amp_center`, `amp_surround` | $a_c e^{-d^2/2\sigma_c^2} - a_s e^{-d^2/2\sigma_s^2}$. May be negative; used as a probability it is clamped at 0. |
| `VonMises` | `2` | `kappa` | $\exp\!\big(\kappa(\cos(2\pi\delta/L) - 1)\big)$. One periodic `Feature` axis of period $L$ only. |
| `Box` | `3` | `radius` | $1$ if $d \le$ radius, else $0$ |
| `Constant` | `4` | — | $1$ |

### 3.18 `ReleaseMode`

| Value | Byte | Description |
| :--- | :---: | :--- |
| `Synaptic` | `0` | Default. Point-to-point synapses built from `topology`. |
| `Volume` | `1` | Diffuse release from axonal arbors into every target within a radius (volume transmission, [§4.8.5](#485-volume-transmission)). |

### 3.19 `PostEventType`
The postsynaptic event that coincidence models pair with ([§4.4.1](#441-timing-conventions--post-events)).

| Value | Byte | Event |
| :--- | :---: | :--- |
| `SomaticSpike` | `0` | Default. A somatic threshold crossing. |
| `DendriticPlateau` | `1` | Plateau onset in `post_event_compartment` ([§4.6.2](#462-multi-compartment-models)). |

### 3.20 `WeightDependence`

| Value | Byte | Applied change for a raw update $\Delta = M\,E$ |
| :--- | :---: | :--- |
| `Additive` | `0` | $\Delta$ (default) |
| `SoftBound` | `1` | $\Delta\,\frac{w_{\max} - w}{w_{\max} - w_{\min}}$ if $\Delta > 0$; $\Delta\,\frac{w - w_{\min}}{w_{\max} - w_{\min}}$ otherwise |

### 3.21 `SynapticScalingMode`

| Value | Byte | Effect ([§4.6.5](#465-homeostasis--synaptic-scaling)) |
| :--- | :---: | :--- |
| `None` | `0` | Default. Not scaled. |
| `Direct` | `1` | Scaled **up** when the target fires below its set point (excitatory inputs). |
| `Inverse` | `2` | Scaled **down** when the target fires below its set point (inhibitory inputs). |

### 3.22 `ControlType`
Host-settable experiment controls ([§4.12](#412-runtime-controls)).

| Value | Byte | Value semantics |
| :--- | :---: | :--- |
| `PlasticityGate` | `0` | Multiplies the Stage-2 factor $M$ (0 freezes weights; traces still run). |
| `StructuralGate` | `1` | 0 disables pruning, sprouting and neurogenesis in scope; 1 enables them. |
| `ReceptorBlock` | `2` | Fraction $b \in [0, 1]$ of the receptor blocked (pharmacology, e.g. AP5 on NMDA). |
| `LigandClamp` | `3` | $v \ge 0$: pools in scope are held at $v$. $v < 0$: off. |
| `NoiseScale` | `4` | Multiplies intrinsic-noise σ and shot-noise rates in scope. |
| `InputGain` | `5` | Multiplies the drive of the named sensory input. |

---

## 4. Detailed Section Specifications

### 4.1 `meta` & `simulation`

`meta`: `schema_version` (must be `"4.3"`), `name`, optional `description`, and `seed` (unsigned 64-bit integer). `seed` is required in the root document and ignored in included documents. `meta` is optional in included documents.

| `simulation` field | Default | Meaning |
| :--- | :--- | :--- |
| `dt_ms` | required | Base integration step. |
| `neuron_substeps` | `2` | Number of Euler sub-steps per `dt` for the nonlinear membrane equations ([§6.2](#62-per-step-update-order)). |
| `plasticity_update_interval_ms` | required | Batch interval $\Delta_p$ for trace→weight transfer. Must be an integer multiple of `dt_ms`. |
| `structural_update_interval_ms` | required | Interval $\Delta_s$ for pruning, sprouting and neurogenesis. Must be an integer multiple of $\Delta_p$. |
| `plasticity_warmup_ms` | `0` | For $t <$ warmup, weight transfer (Stage 2), consolidation, synaptic scaling and structural updates are disabled. Traces, running references and homeostatic bias still run, so `RunningAverage` references settle before learning starts. |
| `plasticity_activity_epsilon` | `1e-3` | Presynaptic-trace threshold below which per-step rules (`CalciumControl`, `VoltageClopath`) skip a synapse ([§4.4.2](#442-stage-1--coincidence-models)). |
| `default_resting_potential_mv` | `-65.0` | Initial $V$ of every compartment. Izhikevich $u_0 = b\,V_0$; AdEx $w_0 = 0$. |
| `validation_max_rate_hz` | `100.0` | Worst-case sustained presynaptic rate used by the divergence checks in [§7](#7-validation-rules). |

### 4.2 `neurotransmitters` (Ligand Pools)

This is a dictionary keyed by an arbitrary ligand ID. Any signalling molecule is a ligand: classical transmitters, neuromodulators, neuropeptides, retrograde messengers, and abstract signals such as a plasticity-related-protein (PRP) supply or a climbing-fibre teaching signal.

For every compartment of every neuron, the engine keeps one concentration $C_{i,c,k}$ per ligand $k$, initialised to `baseline_ambient`. Only (population, compartment, ligand) combinations that are written (by release, volume release or activity release) or read (by a receptor, a coupling or consolidation capture) are allocated. All other combinations stay constant at `baseline_ambient`.

| Field | Meaning |
| :--- | :--- |
| `clearance_model` | `LigandClearanceModel`. |
| `baseline_ambient` | $C_{\text{base}} \ge 0$. The clearance target. |
| `clearance_tau_ms` | For `ExponentialDecay` only. |
| `v_max`, `k_m` | For `MichaelisMenten` only. |
| `quantal_release` | $q$: concentration added per unit of release. |

**Release.** When a presynaptic event reaches synapse $j \to (i, c)$ after its delay, the target pool of each released ligand $k$ ([§4.8.2](#482-transmitter--co-transmission)) is incremented:
$$C_{i,c,k} \mathrel{+}= w_{ij}\; q_k\; r^{\text{STP}}_{j}\; \rho_{k}\; G_{k,j}\; F^{\text{pre}}_{i,c,j}$$
- $r^{\text{STP}}$ is the release fraction computed at spike emission ([§4.5](#45-short_term_dynamics)).
- $\rho_k$ is the component's `release_scale`, and $G_{k,j}$ is its rate gate (1 for single-transmitter projections).
- $F^{\text{pre}}$ is the product of `PresynapticRelease` factors at the arrival site ([§4.3.5](#435-cellular-modulation)).

This is the **only** way synaptic weight affects postsynaptic dynamics. Concentration is clamped to $C \ge 0$.

**Clearance (per step, exact or exponential-Euler):**
- `ExponentialDecay`: $\Delta \leftarrow \Delta\, e^{-dt/\tau}$.
- `MichaelisMenten`: $\Delta \leftarrow \Delta\, \exp\!\left(-\frac{V_{\max}\,dt}{K_m + |\Delta|}\right)$. This is unconditionally stable and keeps the sign. For small $\Delta$ the time constant is $K_m / V_{\max}$.

### 4.3 `receptors`

| Field | Applies to | Meaning |
| :--- | :--- | :--- |
| `ligand` | all | Key in `neurotransmitters`. |
| `kinetics` | all | `ReceptorKineticsModel`. |
| `tau_rise_ms`, `tau_decay_ms` | all | Activation cascade time constants; rise < decay. |
| `desensitization` | all, optional | See [§4.3.2](#432-desensitisation). |
| `g_max` | conductance kinetics | Conductance (ms⁻¹) per unit of activation. |
| `reversal_potential_mv` | conductance kinetics | $E_{\text{rev}}$. |
| `mg_block_conc_mm` | `VoltageGatedConductance` | $[\text{Mg}^{2+}]_o$. |
| `calcium_fraction` | conductance kinetics, optional (default 0) | Fraction of the inward current that becomes calcium influx ([§4.6.3](#463-intracellular-calcium)). |
| `cellular_modulation` | `MetabotropicLinearGain` (required); not allowed on conductance kinetics | One object or an array of objects ([§4.3.5](#435-cellular-modulation)). |

#### 4.3.1 Activation cascade
Each receptor $r$ expressed in compartment $(i, c)$ filters its ligand pool through two first-order stages. The steady-state gain is 1, so a constant concentration $C$ gives $s = C$:
$$\tau_{\text{rise}}\frac{da}{dt} = -a + C_{i,c,\text{ligand}(r)}, \qquad \tau_{\text{decay}}\frac{ds}{dt} = -s + a$$
Both stages are updated with exponential Euler, which is exact for piecewise-constant input, in the order $C \to a \to s$. This is stable for any `dt`, including $\tau_{\text{rise}} < dt$.

The total charge from one release event of size $\Delta C_0$ into an exponentially cleared pool is $g_{\max}\,\Delta C_0\,\tau_{\text{clear}}\,(E_{\text{rev}} - V)$. This is the main quantity for calibrating `g_max`.

#### 4.3.2 Desensitisation
Optional `desensitization`: `tau_onset_ms`, `tau_recovery_ms`, `max_fraction` $\in (0, 1]$. An availability $D \in [1 - \text{max\_fraction}, 1]$, starting at 1, evolves as
$$\frac{dD}{dt} = \frac{1 - D}{\tau_{\text{rec}}} - \frac{D\,s}{\tau_{\text{onset}}}$$
It is integrated with exponential Euler (coefficients frozen over the step) and then clamped. Everywhere below, the **effective activation** is $\tilde s = D\,s$. Without desensitisation, $\tilde s = s$.

#### 4.3.3 Conductance current
$$I_{r}(i,c) = g_{\max,r}\,F^{\text{RC}}_{i,r}\,(1 - b_r)\;\tilde s_r\; B_r(V_{i,c})\;(E_r - V_{i,c}), \qquad I_{\text{syn}}(i,c) = \sum_r I_r(i,c)$$
- $B(V) = \left(1 + \frac{[\text{Mg}^{2+}]_o}{3.57}e^{-0.062V}\right)^{-1}$ for `VoltageGatedConductance`; $B \equiv 1$ otherwise.
- $F^{\text{RC}}$ is the cell's `ReceptorConductance` factor for $r$.
- $b_r$ is the active `ReceptorBlock` control value (0 if none).

Use $V$ from the start of the step.

#### 4.3.4 Metabotropic activation
For metabotropic receptors, $\tilde s$ is also multiplied by $(1 - b_r)$ when a `ReceptorBlock` control applies.

#### 4.3.5 Cellular modulation
```json
"cellular_modulation": {
  "target": "MembraneExcitability",
  "gain": 1.25,
  "reference": { "mode": "Fixed", "value": 0.2 },
  "transfer_function": { "type": "Linear" },
  "min_factor": 0.5,
  "max_factor": 2.0
}
```
$$F = \text{clamp}\big(1 + \text{gain}\cdot\phi(\bar s - s_{\text{ref}}),\ \text{min\_factor},\ \text{max\_factor}\big)$$
The defaults are `min_factor` = 0.25 and `max_factor` = 4.0. $\phi$ is the `transfer_function` (default `Linear`).

- **Cell-wide targets** (`MembraneExcitability`, `SpikeAdaptation`, `DendriticCoupling`, `HomeostaticSetPoint`, `ReceptorConductance`): $\bar s$ is the effective activation averaged over the cell's compartments that express the receptor. A cell's factor for a target is the product over its modulations for that target (1 if there are none).
- **`PresynapticRelease`**: $\bar s$ is the activation in the compartment where the receptor is expressed. The factor applies to events arriving **in that compartment** from the listed projections (all projections into that compartment if `projections` is omitted). The value at the arrival step is used. A negative `gain` gives suppression.

`cellular_modulation` **MAY** be an array, so one receptor can drive several targets.

### 4.4 `plasticity_rules`

Every plastic synapse stores a weight $w_{ij}$, an eligibility trace $e_{ij}$, the batch integral $E_{ij}$, and the per-synapse state its coincidence model needs. With consolidation enabled, $w = w^{\text{early}} + w^{\text{late}}$ ([§4.4.5](#445-consolidation-tagging--capture)).

```json
"Rule_Name": {
  "coincidence_model": "AsymmetricSTDP",
  "params": { ... },
  "post_event": "SomaticSpike",
  "trace_tau_ms": 1200.0,
  "base_transfer_rate": 0.00005,
  "modulator_couplings": [
    { "ligand": "DA", "reference": { "mode": "RunningAverage", "tau_ms": 5000.0 },
      "transfer_gain": 0.1, "transfer_function": { "type": "Linear" } }
  ],
  "weight_dependence": "Additive",
  "consolidation": { ... },
  "w_min": 0.0,
  "w_max": 6.0
}
```

#### 4.4.1 Timing conventions & post events
- $t_{\text{pre}}$ is the **arrival** time at the synapse (spike time + delay). $t_{\text{post}}$ is the time of the rule's post event. $\Delta t = t_{\text{post}} - t_{\text{pre}}$.
- `post_event` (`PostEventType`, default `SomaticSpike`) selects the post event for `AsymmetricSTDP`, `SymmetricSTDP` and `TripletSTDP`. With `DendriticPlateau`, `post_event_compartment` names a compartment of the target cell that has a `plateau` ([§4.6.2](#462-multi-compartment-models)). `PlateauBTSP` always uses `DendriticPlateau`. `BCM_Rate`, `CalciumControl` and `VoltageClopath` do not take `post_event`.
- Within one step, arrivals are processed before the neuron update and post events after it ([§6.2](#62-per-step-update-order)). So an arrival and a post event in the same step count as **causal** ($\Delta t = 0^+$).
- All traces decay exponentially between events, computed lazily from the last-update timestamp. A presynaptic trace is per synapse; a postsynaptic trace is per neuron per rule.

#### 4.4.2 Stage 1 — Coincidence models
Each event adds $\delta e$ to $e_{ij}$. Between events, $e_{ij}$ decays: $\dot e = -e/\tau_{\text{trace}}$.

**`AsymmetricSTDP`** — `tau_plus_ms`, `tau_minus_ms`, `a_plus`, `a_minus`. Traces $x_{\text{pre}}$ ($\tau_+$) and $x_{\text{post}}$ ($\tau_-$), each incremented by 1 per event.
- Pre arrival: $\delta e = -A_-\,x_{\text{post}}$, then $x_{\text{pre}}$ += 1.
- Post event: $\delta e = +A_+\,x_{\text{pre}}$, then $x_{\text{post}}$ += 1.

This reproduces all-to-all pair STDP: $+A_+e^{-\Delta t/\tau_+}$ for $\Delta t \ge 0$ and $-A_-e^{\Delta t/\tau_-}$ for $\Delta t < 0$.

**`SymmetricSTDP`** (Vogels–Sprekeler) — `tau_ms`, `eta`, `target_rate_hz`. Traces $x_{\text{pre}}$, $x_{\text{post}}$ (τ), each +1 per event. $\alpha = 2\,(r_{\text{target}}/1000)\,\tau$ (dimensionless).
- Pre arrival: $\delta e = \eta\,(x_{\text{post}} - \alpha)$, then $x_{\text{pre}}$ += 1.
- Post event: $\delta e = \eta\,x_{\text{pre}}$, then $x_{\text{post}}$ += 1.

**`TripletSTDP`** (Pfister–Gerstner, all-to-all) — `tau_plus_ms`, `tau_minus_ms`, `tau_x_ms`, `tau_y_ms`, `a2_plus`, `a3_plus`, `a2_minus`, `a3_minus`. Presynaptic traces $r_1$ ($\tau_+$) and $r_2$ ($\tau_x$); postsynaptic traces $o_1$ ($\tau_-$) and $o_2$ ($\tau_y$).
- Pre arrival: $\delta e = -o_1\,(A_2^- + A_3^-\,r_2)$, then $r_1$ += 1, $r_2$ += 1.
- Post event: $\delta e = +r_1\,(A_2^+ + A_3^+\,o_2)$, then $o_1$ += 1, $o_2$ += 1.

$r_2$ and $o_2$ are read *before* their own increment.

**`BCM_Rate`** — `eta`, `tau_rate_ms`, `tau_theta_ms`, `target_rate_hz`. Rate traces $\rho_{\text{pre}}$ and $\rho_{\text{post}}$ in Hz (jump $1000/\tau_{\text{rate}}$ per spike). The sliding threshold is $\theta_M = \langle\rho_{\text{post}}^2\rangle_{\tau_\theta} / r_{\text{target}}$, updated each batch. At every batch boundary, $\delta e = \eta\,\rho_{\text{pre}}\,\rho_{\text{post}}\,(\rho_{\text{post}} - \theta_M)\cdot\Delta_p/1000$.

**`CalciumControl`** — `tau_pre_ms`, `theta_d`, `theta_p`, `gamma_d`, `gamma_p` (ms⁻¹). It uses a presynaptic trace $x_{\text{pre}}$ ($\tau_{\text{pre}}$, +1 per arrival) and the calcium $Ca_{i,c}$ of the synapse's target compartment, which must have calcium ([§4.6.3](#463-intracellular-calcium)). Every step, for synapses with $x_{\text{pre}} >$ `plasticity_activity_epsilon`:
$$\delta e = x_{\text{pre}}\;\Omega(Ca_{i,c})\;dt, \qquad \Omega(Ca) = \begin{cases}\gamma_p & Ca \ge \theta_p\\ -\gamma_d & \theta_d \le Ca < \theta_p\\ 0 & \text{otherwise}\end{cases}$$
The rule is synapse-specific through $x_{\text{pre}}$ and compartment-specific through $Ca$: moderate calcium gives LTD, high calcium gives LTP.

**`VoltageClopath`** — `a_ltd`, `a_ltp`, `theta_minus_mv`, `theta_plus_mv`, `tau_minus_ms`, `tau_plus_ms`, `tau_x_ms`. $u$ is the membrane potential of the synapse's **target compartment**. $\bar u_-$ and $\bar u_+$ are low-pass filters of $u$ (per compartment, with $\tau_-$ and $\tau_+$), and $\bar x$ is a presynaptic trace ($\tau_x$, +1 per arrival).
- Pre arrival: $\delta e = -A_{\text{LTD}}\,[\bar u_- - \theta_-]_+$.
- Every step, for synapses with $\bar x >$ `plasticity_activity_epsilon`: $\delta e = A_{\text{LTP}}\,\bar x\,[u - \theta_+]_+\,[\bar u_+ - \theta_-]_+\,dt$.

**`PlateauBTSP`** — `tau_et_ms`, `tau_is_ms`, `eta`, `eta_depress` (default 0), and `post_event_compartment` at rule level. The presynaptic eligibility trace $x_{\text{pre}}$ ($\tau_{\text{et}}$, typically ~1–2 s) gets +1 per arrival. The postsynaptic instructive trace $y_{\text{is}}$ ($\tau_{\text{is}}$) is per neuron.
- Plateau onset in `post_event_compartment`: for **every** synapse of this rule on the neuron, $\delta e = \eta\,x_{\text{pre}} - \eta_{\text{dep}}$. Then $y_{\text{is}}$ += 1.
- Pre arrival: $\delta e = \eta\,y_{\text{is}}$, then $x_{\text{pre}}$ += 1.

This gives a symmetric, seconds-wide plasticity window around each plateau. `eta_depress` adds uniform heterosynaptic depression, which together with `SoftBound` lets established fields shift. Typical use is `trace_tau_ms: 1.0`, `base_transfer_rate: 1.0`, optionally gated by a ligand.

#### 4.4.3 Stage 2 — Ligand-gated transfer
The modulation factor of synapse $j \to (i,c)$ over batch $b$ is
$$M_{i,c} = \Big(\beta_0 + \sum_{m} g_m\,\phi_m\big(\bar C_{i,c,\text{ligand}(m)} - C^{\text{ref}}_{m,i,c}\big)\Big)\cdot\Gamma$$
- $\bar C$ is the pool concentration averaged over the batch (the engine accumulates a per-pool sum each step).
- $\phi_m$ is the coupling's `transfer_function` (default `Linear`).
- $\Gamma$ is the product of active `PlasticityGate` controls for this rule or projection (1 if none).
- $\beta_0$ and $g_m$ are in ms⁻¹ and ms⁻¹·c.u.⁻¹ respectively.

$M$ is held constant over the batch, and the continuous rule $\dot w = M\,e$ is integrated **exactly**. The engine keeps a per-synapse running integral $E_{ij} = \int e\,dt$ over the current batch. On every trace event at time $t$, and at the batch boundary:
```
h      = t - t_last
decay  = exp(-h / τ_trace)
E     += e · τ_trace · (1 - decay)
e      = e · decay  (+ δe if this is an event)
t_last = t
```
Per-step rules (`CalciumControl`, `VoltageClopath`) add their $\delta e$ at the step time through the same update. At the batch boundary, the raw change $\Delta = M\,E$ is shaped by `weight_dependence` ([§3.20](#320-weightdependence)) and applied to $w$ (or to $w^{\text{early}}$ with consolidation). The total is clamped to $[w_{\min}, w_{\max}]$, and then $E \leftarrow 0$. The trace $e$ carries over.

**Effective gains.** One coincidence $\delta e$ with no modulation eventually transfers $\beta_0\,\tau_{\text{trace}}\,\delta e$. A ligand deviation $\Delta\bar C$ held for $T$ ms transfers about $g\,\phi(\Delta\bar C)\,T\,e$.

| Recipe | Settings | Behaviour |
| :--- | :--- | :--- |
| Pure STDP | `trace_tau_ms: 1.0`, `base_transfer_rate: 1.0`, `modulator_couplings: []` | $\beta_0\tau = 1$, so each $\delta e$ goes into $w$ unchanged. |
| Three-factor RL | `trace_tau_ms` ≈ 1000, `base_transfer_rate` ≤ $0.05/\tau$, coupling to a reward ligand with a `RunningAverage` reference | Ungated drift ≤ 5% of a coincidence. Bursts potentiate tagged synapses; pauses depress them. |
| Teaching-signal LTD (e.g. climbing fibre) | Abstract ligand released by the teacher into the learner's compartment, negative `transfer_gain`, `Rectified` Positive | Coincident input followed by the teacher signal depresses the synapse. |
| Opponent receptors (D1 vs D2) | Two rules with opposite-sign gains, or `Rectified` Positive vs Negative | Each cell class learns from bursts or from dips. |

As in standard R-STDP, a negative modulation combined with a negative trace gives *potentiation*.

#### 4.4.4 Weight bounds
After every change, $w$ is clamped to $[w_{\min}, w_{\max}]$. With `SoftBound`, $w$ is the total weight in the bound factors.

#### 4.4.5 Consolidation (tagging & capture)
The optional `consolidation` object splits the weight into a labile early part and a stable late part, $w = w^{\text{early}} + w^{\text{late}}$:

| Field | Default | Meaning |
| :--- | :--- | :--- |
| `early_decay_tau_ms` | required | $w^{\text{early}}$ decays exponentially to 0 (early LTP/LTD fades). |
| `tag_threshold` | required | A synapse is **tagged** while $\lvert w^{\text{early}}\rvert \ge \theta_{\text{tag}}$. |
| `capture_ligand` | required | Cell-wide signal (e.g. `"PRP"`) read from `capture_compartment`. |
| `capture_compartment` | `"Soma"` | Where the capture signal is read. |
| `capture_threshold` | required | Capture happens only while $\bar P > \theta_{\text{cap}}$. |
| `capture_rate` | required | $\kappa$ (ms⁻¹ per c.u.). |
| `late_decay_tau_ms` | ∞ (omit) | Optional slow forgetting of $w^{\text{late}}$. |

At each batch, after the transfer:
1. Decay $w^{\text{early}}$ (and $w^{\text{late}}$ if `late_decay_tau_ms` is set) exactly over $\Delta_p$.
2. For tagged synapses, let $c = \min\big(1, \kappa\,[\bar P - \theta_{\text{cap}}]_+\,\Delta_p\big)$ and move $c\,w^{\text{early}}$ from early to late.
3. Clamp the total to the bounds by adjusting $w^{\text{early}}$.

Initial weights are written to $w^{\text{late}}$, with $w^{\text{early}} = 0$. Stage-2 transfer writes to $w^{\text{early}}$. Release, pruning and soft bounds use the total $w$. The capture signal is produced by `activity_release` ([§4.6.4](#464-activity-dependent-release)), so the tag-and-capture logic (strong stimulation plus neuromodulation → protein supply) is itself configured as data.

### 4.5 `short_term_dynamics`

```json
"Depressing_Glu": { "model": "TsodyksMarkram", "U_release_prob": 0.5, "tau_recovery_ms": 800.0, "tau_facilitation_ms": 20.0 }
```
State $(x, u)$ is kept **per presynaptic neuron per projection**. This is exact because all synapses of a projection share the rule and are updated at spike emission. Between spikes, $x \to 1$ with $\tau_{\text{rec}}$ and $u \to U$ with $\tau_{\text{facil}}$ (exact exponentials). At a spike:
$$u \leftarrow u + U(1 - u), \qquad r^{\text{STP}} = u\,x, \qquad x \leftarrow x - r^{\text{STP}}$$
The value $r^{\text{STP}}$ travels with the spike event to every synapse (or volume link) of the projection. Initial state: $x = 1$, $u = U$.

### 4.6 `cell_types`

| Field | Meaning |
| :--- | :--- |
| `extends` | Optional parent cell type ([§5.4](#54-inheritance-extends)). |
| `model` | `NeuronDynamicsModel`. |
| `compartments` | See [§3.6](#36-neurondynamicsmodel). |
| `params` | Somatic model parameters (below). |
| `dendrite` | `Izhikevich_2C` only (required). |
| `dendrites` | `Izhikevich_MC` only (required): map compartment → dendrite object with `parent`. |
| `parameter_jitter` | $j \ge 0$. Per neuron, each `params` entry except `v_peak_mv`, `v_thresh_mv` and `refractory_ms` is set to $p(1 + j\xi)$, with $\xi \sim \mathcal N(0,1)$ truncated to $[-3, 3]$. |
| `intrinsic_current` | `IntrinsicCurrentType` object, injected into the soma. |
| `calcium` | Optional intracellular calcium ([§4.6.3](#463-intracellular-calcium)). |
| `activity_release` | Optional list of activity-dependent self-release rules ([§4.6.4](#464-activity-dependent-release)). |
| `homeostasis` | `{ "enabled": false }`, or the full object ([§4.6.5](#465-homeostasis--synaptic-scaling)). |
| `structural_plasticity` | Optional; see [§4.9](#49-structural-plasticity--neurogenesis). |

Every model has `refractory_ms`. After a spike, $V_{\text{soma}}$ is held at the reset value for that long; the other state variables keep evolving.

#### 4.6.1 Point models
**`Izhikevich_1C`** — `a`, `b`, `c`, `d`, `v_peak_mv`, `refractory_ms`:
$$\dot v = 0.04v^2 + 5v + 140 - u + I_{\text{tot}}, \qquad \dot u = a(bv - u)$$
When $v \ge v_{\text{peak}}$: spike, $v \leftarrow c$, $u \leftarrow u + d\cdot F_{\text{SpikeAdaptation}}$.

**`AdEx`** — `tau_m_ms`, `e_leak_mv`, `v_t_mv`, `delta_t_mv`, `a` (dimensionless), `tau_w_ms`, `b` (mV), `v_reset_mv`, `v_peak_mv`, `refractory_ms`:
$$\dot V = \frac{-(V - E_L) + \Delta_T e^{(V - V_T)/\Delta_T} - w}{\tau_m} + I_{\text{tot}}, \qquad \tau_w\dot w = a(V - E_L) - w$$
When $V \ge v_{\text{peak}}$: $V \leftarrow V_{\text{reset}}$, $w \leftarrow w + b\cdot F_{\text{SpikeAdaptation}}$.

**`LIF`** — `tau_m_ms`, `e_leak_mv`, `v_thresh_mv`, `v_reset_mv`, `refractory_ms`:
$$\dot V = -(V - E_L)/\tau_m + I_{\text{tot}}$$
Spike and reset at $v_{\text{thresh}}$.

#### 4.6.2 Multi-compartment models
A **dendrite object** has these fields: `coupling_g` ($g_c$, ms⁻¹, to its parent), `tau_ms` ($\tau_d$), `e_leak_mv`, `bap_kick_mv` (default 0; added on each somatic spike), and an optional `plateau` {`g_max`, `v_half_mv`, `slope_mv`, `reversal_potential_mv`, `refractory_ms` (default 50)}.

**`Izhikevich_2C`** uses one dendrite object under `dendrite`; its parent is the soma.

**`Izhikevich_MC`** uses `dendrites`, a map from each non-soma compartment to a dendrite object with an extra `parent` field (`"Soma"` or another listed dendrite). The parent links **MUST** form a tree rooted at the soma. Example: `BasalDendrite → Soma`, `ApicalDendrite → Soma`, `ApicalTuft → ApicalDendrite`.

The soma follows the Izhikevich equations above, plus coupling to its children. Each dendrite $c$ with parent $\pi(c)$ and children $\kappa(c)$ follows
$$\dot v_c = -\frac{v_c - E_{L,c}}{\tau_{d,c}} + I_{\text{tot},c} + \sum_{n \in \{\pi(c)\}\cup\kappa(c)} g_{c\leftrightarrow n}\,F_{\text{DC}}\,(v_n - v_c) + g_{p,c}\;p_c\;(E_{p,c} - v_c)$$
- The plateau gate is $p_c = \sigma\big((v_c - v_{1/2})/k_p\big)$.
- $g_{c\leftrightarrow n}$ is the `coupling_g` of whichever of the pair is the child; coupling is symmetric.
- The soma gets $\sum_{n \in \kappa(\text{soma})} g_{n}F_{\text{DC}}(v_n - v_s)$.
- $F_{\text{DC}}$ is the `DendriticCoupling` factor (per compartment if the modulation names one).

**Plateau events.** A `DendriticPlateau` event occurs in compartment $c$ when $p_c$ crosses 0.5 upward, and at least the plateau's `refractory_ms` has passed since the last event there. Plateau events can drive plasticity (`post_event`, `PlateauBTSP`), calcium influx and `activity_release`.

#### 4.6.3 Intracellular calcium
Optional `calcium` object: `tau_ms`, `spike_influx` (map compartment → amount added per somatic spike, i.e. bAP-driven influx), `plateau_influx_per_ms` (default 0). Every compartment of the cell gets $Ca \ge 0$, starting at 0:
$$\frac{dCa_c}{dt} = -\frac{Ca_c}{\tau_{Ca}} + \sum_{r \in c} \text{calcium\_fraction}_r\,[I_r]_+ + \text{plateau\_influx}\cdot p_c$$
It is integrated with exponential Euler, with the spike influx added at the spike step. Calcium is read by `CalciumControl` and can be recorded.

#### 4.6.4 Activity-dependent release
`activity_release` is a list of rules by which a neuron's own events write to its own ligand pools. This models retrograde messengers (endocannabinoids), autocrine signals, and cell-wide plasticity signals (PRP supply for capture):
```json
"activity_release": [
  { "ligand": "PRP", "compartment": "Soma", "event": "DendriticPlateau", "event_compartment": "ApicalTuft",
    "amount": 0.2, "rate_gate": { "threshold_hz": 5.0, "slope_hz": 1.0, "rate_tau_ms": 2000.0 } }
]
```
On each event (`SomaticSpike`, or `DendriticPlateau` in `event_compartment`), $C_{i,\text{compartment},\text{ligand}}$ += $\text{amount}\cdot G$. The optional rate gate is $G = \sigma\big((\hat r - \theta)/\text{slope}\big)$, where $\hat r$ is the neuron's rate trace with `rate_tau_ms` ($G$ is a step if `slope_hz` = 0). Release takes effect in the same step, with no delay.

#### 4.6.5 Homeostasis & synaptic scaling
`homeostasis`: `enabled`, `target_rate_hz`, `rate_estimate_tau_ms` (default 1000), `adaptation_tau_ms`, `bias_gain` (cu per Hz, default 0.5; 0 disables the bias current), `max_bias_current` (default 5.0), and optional `synaptic_scaling` {`tau_ms`}.

- **Rate estimate.** A rate trace $\hat r$ in Hz (jump $1000/\tau_{\text{est}}$ per spike).
- **Intrinsic bias.** A somatic bias current, integrated each step and clamped to $\pm$`max_bias_current`:
$$\dot I_h = \frac{\text{bias\_gain}\,\big(r_{\text{target}}F_{\text{HSP}} - \hat r\big)}{\tau_{\text{adapt}}}$$
- **Synaptic scaling.** At each batch (after warmup), every incoming synapse whose projection sets `synapse.synaptic_scaling` to `Direct` or `Inverse` is multiplied by
$$S = \exp\!\Big(\pm\,\frac{\Delta_p\,(r_{\text{target}}F_{\text{HSP}} - \hat r)}{r_{\text{target}}F_{\text{HSP}}\,\tau_{\text{scale}}}\Big)$$
with $+$ for `Direct` and $-$ for `Inverse`. Both $w^{\text{early}}$ and $w^{\text{late}}$ are scaled, then clamped. Static synapses are scaled and clamped to $[0, \infty)$.

#### 4.6.6 Total current
Per compartment:
$$I_{\text{tot}} = F_{\text{ME}}\,(I_{\text{syn}} + I_{\text{gap}} + I_{\text{sensory}}) + I_{\text{int}} + I_{\text{h}}$$
$I_{\text{int}}$ and $I_{\text{h}}$ go to the soma only. Voltage kicks (Poisson sensory, shot noise) are added directly to $V$ and are not scaled. During neurogenesis maturation, $F_{\text{ME}}$ also includes the young-neuron factor ([§4.9.3](#493-neurogenesis)).

### 4.7 `nuclei` & Populations

| Nucleus field | Meaning |
| :--- | :--- |
| `id` | Unique (after namespacing). |
| `coordinates_mm` | Shape centre (world frame). |
| `radius_mm` *or* `shape` | `radius_mm` is shorthand for `{"type":"Sphere","radius_mm":r}`. `shape` is a `ShapeType` object with optional `rotation_deg` $[r_x, r_y, r_z]$. |
| `layer_axis` | Local axis (0–2, default 2) along which `depth_range` is measured. |
| `size` | Total neuron count, including neurogenesis reserves. |
| `composition[]` | Populations ([§4.7.2](#472-populations)). |
| `gap_junctions[]` | Optional: `between_type` (population name), `topology` (any synaptic `TopologyType`), `conductance` (ms⁻¹). |
| `projections[]` | Embedded efferent projections ([§4.8](#48-projections)); may be empty. |

#### 4.7.1 Shape & placement
Local-to-world transform: $p = c + R\,p_{\text{local}}$, with $R = R_z(r_z)R_y(r_y)R_x(r_x)$. The normalised coordinate is $\hat p = p_{\text{local}} / h$ (component-wise, $h$ from [§3.15](#315-shapetype)). It lies in the unit ball for spheres and ellipsoids, and in $[-1, 1]^3$ for boxes.

Each neuron is placed uniformly at random inside its shape, from the `Placement` RNG stream, by rejection sampling. If its population has a `depth_range` $[a, b] \subseteq [-1, 1]$, it is also restricted to $a \le \hat p_{\text{layer\_axis}} \le b$. Several populations of one nucleus with different `depth_range`s form **layers**. Separate nuclei with the same centre and shape can also overlap freely.

#### 4.7.2 Populations
| Composition field | Meaning |
| :--- | :--- |
| `name` | Population name, unique within the nucleus; default = `cell_type`. Projections, I/O, probes and augments refer to populations by this name. |
| `cell_type` | Key in `cell_types`. |
| `fraction` | Fractions of a nucleus sum to 1 (±1e-6). |
| `receptors` | Map compartment → list of receptor IDs (may be `{}`). |
| `depth_range` | Optional layer restriction. |
| `feature_space` | Optional ([§4.7.4](#474-feature-space)). |
| `neurogenesis` | Optional ([§4.9.3](#493-neurogenesis)). |

Population sizes are $\lfloor \text{size}\cdot f \rfloor$, with the remainder handed out by the largest-remainder method (ties go to the earlier composition entry). A neuron's **rank** is its 0-based index within its population, in placement order.

#### 4.7.3 Receptor expression
A release activates **every** receptor for that ligand expressed in the target compartment. Two populations with the same dynamics but different receptor sets (e.g. D1- vs D2-type cells) are two composition entries. They can share one cell type, provided they have different `name`s.

#### 4.7.4 Feature space
Some circuits are organised by an abstract variable rather than anatomy: heading for a ring attractor, position for grid and place cells, orientation for a hypercolumn. A population **MAY** declare feature coordinates:
```json
"feature_space": { "dimensions": 1, "extent": [360.0], "periodic": [true], "layout": "Lattice", "lattice_shape": [120] }
```
- `extent` $L_a$ and `periodic` are per axis. Coordinates lie in $[0, L_a)$.
- `Lattice`: requires `lattice_shape` with product equal to the population size. Rank $r$ maps to a row-major multi-index $(k_a)$ (last axis fastest), and $\varphi_a = (k_a + 0.5)\,L_a / n_a$.
- `Random`: $\varphi_a \sim U[0, L_a)$, drawn from the `Placement` stream.

On a periodic axis, the difference $\delta_a$ is wrapped to $[-L_a/2, L_a/2)$. Feature coordinates don't affect anatomical position or delays.

### 4.8 Projections

Projections are declared either **embedded** in their source nucleus's `projections[]`, or **free-standing** in the top-level `projections[]` with an additional `from_nucleus`. The two forms are equivalent. A module uses free-standing projections to connect to and from nuclei it does not own ([§5](#5-modules--composition)).

#### 4.8.1 Fields
| Field | Meaning |
| :--- | :--- |
| `id` | Unique (after namespacing). |
| `from_nucleus` | Free-standing projections only. |
| `from_type` | Source population name. |
| `to_nucleus`, `to_type` | Target nucleus and population name. |
| `target_compartment` | Must be one of the target cell type's `compartments`. |
| `release_mode` | `ReleaseMode`, default `Synaptic`. |
| `topology` | `TopologyType` object (`Synaptic` only). |
| `volume` | `Volume` only ([§4.8.5](#485-volume-transmission)). |
| `conduction_velocity_m_s` | > 0. |
| `synaptic_delay_ms` | Optional, default 0. Added to the conduction delay. |
| `transmitter` | Ligand ID, or a co-transmission list ([§4.8.2](#482-transmitter--co-transmission)). |
| `synapse.weight_distribution` | `DistributionType` object. |
| `synapse.weight_kernel` | Optional kernel modulating initial weights ([§4.8.3](#483-kernels--displacements)). |
| `synapse.stp_rule` | Key in `short_term_dynamics`, or `"None"`. |
| `synapse.ltp_rule` | Key in `plasticity_rules`, or `"None"`. |
| `synapse.synaptic_scaling` | `SynapticScalingMode`, default `None`. |
| `synapse.structural_plasticity` | bool. |
| `synapse.sprout_initial_weight` | Required when `structural_plasticity` is true. |

**Delay.** $\text{delay} = \lVert p_i - p_j\rVert / v + \text{synaptic\_delay}$, quantised to $\max(1, \text{round}(\text{delay}/dt))$ steps. `ExplicitList` may override the delay per pair. The spike ring buffer holds at least max steps + 1 slots.

#### 4.8.2 Transmitter & co-transmission
`transmitter` is either a ligand ID, or a list of components:
```json
"transmitter": [
  { "ligand": "Glu" },
  { "ligand": "DA", "release_scale": 0.5 },
  { "ligand": "Neuropeptide_Y", "rate_gate": { "threshold_hz": 20.0, "slope_hz": 4.0, "rate_tau_ms": 200.0 } }
]
```
Each component releases into its own pool with the same weight, delay and STP state, scaled by `release_scale` (default 1) and its rate gate $G$. $G = \sigma((\hat r_{\text{pre}} - \theta)/\text{slope})$, where $\hat r_{\text{pre}}$ is the presynaptic neuron's rate trace with `rate_tau_ms`; $G = 1$ if there is no gate. Peptides released only during high-frequency firing are modelled with a gate. A ligand **MUST NOT** appear twice in one list.

#### 4.8.3 Kernels & displacements
A `Kernel` topology, or a `weight_kernel`, is:
```json
{ "space": "Feature", "axes": [0], "kernel": { "type": "VonMises", "kappa": 8.0 }, "offset": [12.0] }
```
plus `max_prob` and `type: "Kernel"` when used as a topology.

**Displacement.** $\delta_{ij} = \text{coord}_{\text{tgt}}(i) - \text{coord}_{\text{src}}(j) - \text{offset}$, restricted to `axes`. Periodic `Feature` axes are wrapped after subtracting the offset. A nonzero `offset` gives **asymmetric (shifted) connectivity**, as used for path integration in ring and grid attractors.

`Feature` space requires both populations to declare feature spaces whose axes in `axes` have identical `extent` and `periodic`. `Normalized` and `Anatomical` spaces work between any populations.

A **`weight_kernel`** multiplies each sampled initial weight by $K(\delta_{ij})$. Negative products become 0, and such synapses are not created. Typical uses are Mexican-hat profiles (excitatory `Gaussian` plus a broad inhibitory projection, or `DifferenceOfGaussians`) and graded topographic weights.

#### 4.8.4 Explicit connection lists
`ExplicitList` takes exactly one of:
- `pairs`: inline array of `[source_rank, target_rank]`, `[…, weight]` or `[…, weight, delay_ms]`.
- `path`: CSV file, relative to the declaring document, with header `source,target` and optional columns `weight` and `delay_ms`.

Ranks refer to populations ([§4.7.2](#472-populations)). A `weight` overrides `weight_distribution` (still clipped). A `delay_ms` overrides the geometric delay (still quantised). Duplicate pairs are an error, and so are self-pairs on recurrent projections. Lists make any connectome (traced, generated offline, from atlases) expressible.

#### 4.8.5 Volume transmission
With `"release_mode": "Volume"`, the projection has no `topology`. Instead it has:
```json
"volume": { "arbors_per_source": 1, "sigma_mm": 0.5, "cutoff_mm": 1.5 }
```
At build time, each source neuron gets `arbors_per_source` arbor centres. Each centre is the position of a target neuron drawn uniformly (`Topology` stream). Every target neuron within `cutoff_mm` of a centre gets a **volume link** with factor $K = \exp(-d^2/2\sigma^2)$ and a weight drawn from `weight_distribution`.

On a spike, each link releases $w\,q\,r^{\text{STP}}\,K$ (times the co-transmission and presynaptic factors) into the target compartment's pool. The delay is $\lVert p_{\text{src}} - \text{centre}\rVert / v + \text{synaptic\_delay}$. Volume links **MUST** use `"ltp_rule": "None"` and `structural_plasticity: false`. They take STP, and they count as release for validation purposes.

#### 4.8.6 Gap junctions
Gap junctions are sampled once per unordered pair within a population (any synaptic topology, including `Kernel` and `ExplicitList`). They are symmetric and connect somata only:
$$I_{\text{gap},i} = \sum_j g\,(V_j - V_i)$$
Use voltages from the start of the step.

### 4.9 Structural Plasticity & Neurogenesis

#### 4.9.1 Parameters
Cell-type `structural_plasticity`: `max_incoming_synapses` (all incoming synapses from every projection), `prune_weight_threshold`, `sprout_probability_per_sec`, `sprout_grace_period_ms`.

#### 4.9.2 Pruning & sprouting
At each structural update (after warmup, and while no `StructuralGate` in scope is 0), in this order:
1. **Prune.** Every synapse of a projection with `structural_plasticity: true` is removed by swap-and-pop if its total weight is below `prune_weight_threshold` and its age exceeds the grace period. Per-synapse state (w, w^early, w^late, e, E, traces, delay) moves with it. The engine **MUST NOT** keep synapse indices across a structural update.
2. **Sprout.** For each active target neuron of such a projection, with probability $1 - e^{-p\,\Delta_s/1000}$ and only if its indegree is below the maximum, one candidate source is drawn uniformly from the source population's active neurons. It is accepted with the projection's topology probability:
   - $P$ for `Random`, `SpatialGaussian`, `Topographic` and `Kernel`;
   - 1 for `AllToAll` and `FixedIndegree`;
   - the matching rank for `OneToOne`;
   - membership of a currently absent listed pair for `ExplicitList`.

   Up to 16 attempts are made. Autapses (unless allowed), multapses and duplicates are rejected. A new synapse gets `sprout_initial_weight` (into $w^{\text{late}}$ with consolidation), $e = 0$, fresh traces, its geometric delay (list delay for `ExplicitList`), and the projection's rules.

#### 4.9.3 Neurogenesis
A population **MAY** declare:
```json
"neurogenesis": { "reserve_fraction": 0.2, "birth_rate_per_sec": 0.5, "maturation_ms": 60000.0, "young_excitability_factor": 2.0 }
```
- The last ⌈`reserve_fraction`·N⌉ ranks start **dormant**. They have positions, but no synapses, and they are not integrated (no spikes, no outputs).
- At each structural update, $n \sim \text{Poisson}(\lambda\,\Delta_s/1000)$ dormant neurons become active (lowest rank first; `Structural` stream). On birth:
  - For each **incoming** projection with `structural_plasticity: true`, synapses are sprouted (as in §4.9.2 but without the per-update probability) until the newborn's indegree from that projection reaches the projection's realised mean indegree at build time, or 16× that many attempts have been made.
  - For each **outgoing** such projection, the same is done until the newborn's outdegree reaches the realised mean outdegree.
- During maturation, $F_{\text{ME}}$ is multiplied by $1 + (\text{young\_excitability\_factor} - 1)\,(1 - \text{age}/\text{maturation\_ms})$ for age < maturation.
- Every projection into or out of a neurogenic population **SHOULD** have `structural_plasticity: true`. Otherwise newborns have no connections through it (warning).

### 4.10 External I/O Interfaces

#### 4.10.1 Channel assignment
Shared by inputs and outputs:
1. Order the target (or source) population by $\hat p$ along `channel_axis` (default 0), breaking ties by rank.
2. Keep the slice of the order given by `target_subrange` (or `source_subrange`) $[a, b) \subseteq [0, 1]$, default `[0, 1]`.
3. Split the slice into `dimensions` contiguous blocks whose sizes differ by at most 1. Block $c$ is channel $c$. `MultiDimGaussianReceptiveField` and `PopulationVector` instead use the whole slice as one block.

A 1-dimensional input therefore drives the whole slice. Because `Topographic` with `axes: [0]` maps $\hat p_0$ to $\hat p_0$, channel $c$ of a nucleus projects onto channel $c$ of the target. Several inputs **MAY** overlap on the same neurons, and their effects add; the compiler warns about overlaps. Dormant neurons ignore inputs and contribute 0 to outputs.

#### 4.10.2 Multi-dimensional receptive fields
For `MultiDimGaussianReceptiveField`, `min_input` and `max_input` are arrays of length $d$ (or scalars, broadcast to all axes). `receptive_field_sigma` is likewise a scalar or a per-axis array, in raw input units. `periodic` (per axis, default false) wraps differences with period $x_{\max,a} - x_{\min,a}$. `centers` is one of:
- `{"type": "Lattice", "lattice_shape": [...]}`, whose product must equal the block size. Centres sit at cell midpoints, row-major by rank in channel order.
- `{"type": "Random"}`: uniform in the input box (`SensoryEncoding` stream).
- `{"type": "FeatureSpace"}`: the population's feature space must have $d$ dimensions. Centre $\mu_a = x_{\min,a} + \varphi_a / L_a\,(x_{\max,a} - x_{\min,a})$. This ties tuning to attractor position.

$\delta_a = x_a - \mu_a$ (wrapped if periodic). $x$ is clamped to the box on non-periodic axes.

#### 4.10.3 Inputs and outputs
**`sensory_inputs[]`**: `id`, `target_nucleus`, `target_type`, `target_compartment`, `target_subrange`, `channel_axis`, `dimensions`, `encoding`, `min_input`, `max_input`, plus the encoding's fields from [§3.11](#311-sensoryencodingmodel). The host writes a frame of length `dimensions` before a step, and it stays in effect until overwritten.

**`motor_outputs[]`**: `id`, `source_nucleus`, `source_type`, `source_subrange`, `channel_axis`, `dimensions`, `decoding`, `output_gain`, `clamp_bounds` (optional), plus the decoding's fields from [§3.12](#312-motordecodingmodel). Outputs are readable after every step.

Modulatory nuclei are ordinary nuclei. External valence signals reach them through sensory transducers or projections. There is no special-case reward code in the engine.

### 4.11 Recording

`recording.probes[]` declares what the engine makes observable. Where the data goes (memory, file, network) is decided by a host-provided sink; storage format is not part of this schema.

```json
"recording": {
  "probes": [
    {
      "id": "ctx_spikes",
      "nucleus": "cortex_S1_M1",
      "population": "Pyramidal_RS",
      "selection": { "type": "Random", "count": 200 },
      "variables": ["Spikes"]
    },
    {
      "id": "ca1_state",
      "nucleus": "hpc.ca1",
      "population": "CA1_Pyramidal",
      "selection": { "type": "First", "count": 10 },
      "sample_interval_ms": 1.0,
      "variables": [
        "V:Soma", "V:ApicalTuft", "Calcium:BasalDendrite", "Ligand:hpc.PRP@Soma",
        "Activation:hpc.NMDA_Ca@BasalDendrite", "Factor:MembraneExcitability",
        "HomeostaticBias", "RateEstimate", "Plateau:ApicalTuft"
      ]
    },
    {
      "id": "schaffer_weights",
      "projection": "hpc.schaffer_collaterals",
      "selection": { "type": "Random", "count": 1000 },
      "sample_interval_ms": 1000.0,
      "variables": ["Weight", "EarlyWeight", "LateWeight", "Eligibility"]
    },
    {
      "id": "dg_newborns",
      "nucleus": "hpc.dentate",
      "population": "DG_Granule",
      "selection": { "type": "All" },
      "sample_interval_ms": 1000.0,
      "variables": ["Alive"]
    },
    {
      "id": "hd_rate",
      "nucleus": "hd.hd_ring",
      "population": "Ring",
      "variables": ["PopulationRate"],
      "rate_window_ms": 50.0,
      "sample_interval_ms": 10.0
    },
    { "id": "limb", "motor_output": "upper_limb_muscle_synergies", "sample_interval_ms": 1.0 },
    { "id": "freezing", "motor_output": "fear.freezing_response", "sample_interval_ms": 10.0 },
    { "id": "heading", "motor_output": "hd.decoded_heading", "sample_interval_ms": 10.0 },
    { "id": "learning_state", "control": "freeze_learning", "sample_interval_ms": 10.0 }
  ]
},
"runtime_controls": [
  {
    "id": "freeze_learning",
    "type": "PlasticityGate",
    "rules": ["Cortical_ThreeFactor_STDP", "Corticospinal_ThreeFactor_STDP", "fear.Fear_NE_STDP", "hpc.CA1_BTSP"],
    "default": 1.0
  },
  { "id": "ap5", "type": "ReceptorBlock", "receptor": "hpc.NMDA_Ca", "nuclei": ["hpc.ca1", "hpc.dentate"], "default": 0.0 },
  { "id": "da_clamp", "type": "LigandClamp", "ligand": "DA", "nuclei": ["cortex_S1_M1"], "default": -1.0 },
  { "id": "no_sprouting", "type": "StructuralGate", "default": 1.0 },
  { "id": "quiet_arousal", "type": "NoiseScale", "nuclei": ["aras_core"], "default": 1.0 },
  { "id": "place_input_gain", "type": "InputGain", "input": "hpc.arena_position", "default": 1.0 }
]

```

| Probe kind | Selector fields | Variables |
| :--- | :--- | :--- |
| Neuron | `nucleus`, `population`, `selection` | `Spikes` (event list), `V:<comp>`, `Calcium:<comp>`, `Ligand:<lig>@<comp>`, `Activation:<rec>@<comp>`, `Factor:<CellularModulationTarget>`, `HomeostaticBias`, `RateEstimate`, `Plateau:<comp>` (event list), `Alive` (neurogenesis) |
| Synapse | `projection`, `selection`, `include_new` (default false) | `Weight`, `EarlyWeight`, `LateWeight`, `Eligibility`, `Delay` |
| Population | `nucleus`, `population`, `variables: ["PopulationRate"]`, `rate_window_ms` | Mean rate in Hz |
| Motor output | `motor_output` | Output vector |
| Control | `control` | Current control value |

- **Selection**: `All`, `First` {`count`}, `Random` {`count`} (`Recording` stream), or `Explicit` {`ranks`} (neurons) / {`indices`} (synapses at the probe's start).
- Synapse probes follow their selected synapses through swap-and-pop. A pruned synapse reports NaN from then on.
- `sample_interval_ms` (default `dt_ms`) must be a multiple of `dt_ms`. Event variables ignore it. `start_ms` and `stop_ms` are optional.
- Recording **MUST NOT** change simulation results.

### 4.12 Runtime Controls

`runtime_controls[]` declares named experiment knobs. The host sets them by id between steps (`SetControl(id, value)`), and changes take effect at the start of the next step. Controls make lesion, pharmacology, clamping and train/test protocols part of the declared model, not of ad-hoc host code.

```json
"runtime_controls": [
  {
    "id": "freeze_learning",
    "type": "PlasticityGate",
    "rules": ["Cortical_ThreeFactor_STDP", "Corticospinal_ThreeFactor_STDP", "fear.Fear_NE_STDP", "hpc.CA1_BTSP"],
    "default": 1.0
  },
  { "id": "ap5", "type": "ReceptorBlock", "receptor": "hpc.NMDA_Ca", "nuclei": ["hpc.ca1", "hpc.dentate"], "default": 0.0 },
  { "id": "da_clamp", "type": "LigandClamp", "ligand": "DA", "nuclei": ["cortex_S1_M1"], "default": -1.0 },
  { "id": "no_sprouting", "type": "StructuralGate", "default": 1.0 },
  { "id": "quiet_arousal", "type": "NoiseScale", "nuclei": ["aras_core"], "default": 1.0 },
  { "id": "place_input_gain", "type": "InputGain", "input": "hpc.arena_position", "default": 1.0 }
]


```

**Scope** is set with `nuclei` (list; default: all), and optionally `populations` (names, together with a single nucleus). `PlasticityGate` takes `rules` and/or `projections` (default: all plastic synapses). If several controls apply, `PlasticityGate`, `NoiseScale` and `InputGain` values multiply. For `ReceptorBlock`, the largest value wins. For `LigandClamp`, the last-declared active control wins.

**Effects:**
- `LigandClamp` sets the pool after clearance each step, and its value also enters $\bar C$.
- `ReceptorBlock` acts as in [§4.3.3](#433-conductance-current) and [§4.3.4](#434-metabotropic-activation).
- `InputGain` multiplies currents, rates and kick sizes of the named input.

---

## 5. Modules & Composition

### 5.1 Includes
```json
"includes": [
  { "path": "brain.json" },
  { "path": "modules/fear_circuit.json", "namespace": "fear" }
]
```
- `path` is resolved relative to the including document.
- `namespace` is optional. Without one, the included document shares the includer's namespace.
- `root_namespace: true` loads the document into the **root** namespace, whatever the includer's namespace is. This is how a namespaced module pulls in a shared library ([§5.2](#52-namespaces--name-resolution)). It can't be combined with `namespace`.
- Loading is depth-first in list order. The same (canonical path, effective namespace) pair is loaded **once** (diamond includes are fine). It is an error for a file (by canonical path) to appear twice on the current include chain, whatever its namespace.
- `simulation` comes from the root document if it has one. Otherwise exactly one document in the include graph may define it (more than one is an error). `meta` is always taken from the root.

### 5.2 Namespaces & name resolution
A document's **effective namespace** is the includer's namespace, extended by `namespace` if given (e.g. `hpc` inside `lab` → `lab.hpc`; the root's is empty).

**Qualified names.** Every identifier *defined* in a document gets its effective namespace prefixed with a dot (`fear.lateral`). This covers dictionary keys of the five definition sections, nucleus ids, projection ids, I/O ids, probe ids and control ids. Population names are scoped to their nucleus and are not prefixed.

**Resolving references.** A reference is resolved by the first match in this order:
- If it contains a dot, it is absolute and used as written.
- Otherwise it is tried in the document's effective namespace, then in each enclosing namespace outward, ending at the root.

So a module can refer to `Glu`, `AMPA` or `cortex_S1_M1` from the base model without qualification, while its own `lateral` stays private as `fear.lateral`.

**Ligand identity.** Ligand identity follows the qualified name. Shared signalling molecules (e.g. `NE`) **SHOULD** therefore be defined once in a shared library module, which every user includes with `root_namespace: true`. That way all modules release into and sense the same pools.

### 5.3 Merging
- **Dictionaries** (`neurotransmitters`, `receptors`, `plasticity_rules`, `short_term_dynamics`, `cell_types`): union by qualified key. Defining the same qualified key twice is an error, *unless* both definitions are deep-equal after inheritance resolution (so shared libraries may be included repeatedly).
- **Arrays** (`nuclei`, `projections`, `io_interfaces.sensory_inputs`, `io_interfaces.motor_outputs`, `recording.probes`, `runtime_controls`): concatenated in depth-first post-order. Each included document's entries come before the includer's own entries. This order defines neuron indexing and build order ([§6.1](#61-compilation-order--indexing)).
- `augment` sections are collected and applied after merging ([§5.5](#55-augment)).

### 5.4 Inheritance (`extends`)
Any entry of the five dictionary sections may have `"extends": "<key>"`. The parent is resolved by name (it may live in another namespace), and the child is a **deep merge** of the parent and the child's own fields:
- Objects merge recursively. Scalars and arrays in the child replace the parent's.
- A child value of `null` deletes the key.
- An object containing `"$replace": true` replaces the parent's object entirely (the marker itself is dropped).

Chains are allowed; cycles are an error. Inheritance is resolved before validation, so the merged entry must be valid on its own. Example: `"CA3_Pyramidal": { "extends": "Pyramidal_RS", "params": { "d": 6.0 } }`.

### 5.5 Augment
A module may extend populations it doesn't own, **additively only**:
```json
"augment": {
  "populations": [
    { "nucleus": "cortex_S1_M1", "population": "Pyramidal_RS",
      "add_receptors": { "ApicalDendrite": ["Beta_Adrenergic"] } }
  ],
  "gap_junctions": [
    { "nucleus": "cortex_S1_M1", "between_type": "Basket_FS",
      "topology": { "type": "Random", "probability": 0.01 }, "conductance": 0.002 }
  ]
}
```
Adding a receptor that is already expressed has no effect. Augments can't remove or change anything, so a base model never changes behaviour except through what modules explicitly add.

### 5.6 Extensibility guarantee
With includes, namespaces, free-standing projections, `extends` and `augment`, a new region and its afferents, efferents, ligands, receptors and modulatory effects on existing regions are declared entirely in new files. Each existing document compiles unchanged on its own.

---

## 6. Execution Semantics

### 6.1 Compilation order & indexing
1. Load and merge all documents ([§5](#5-modules--composition)), resolve inheritance, apply augments, then resolve and validate every reference ([§7](#7-validation-rules)).
2. Assign dense indices to ligands, receptors, rules and cell types by **ordinal (byte-wise) string sort** of their qualified keys.
3. Global neuron indices follow merged `nuclei` order, then `composition` order, contiguously. Positions and feature coordinates are sampled in index order.
4. Build connectivity in this order: embedded projections (merged nucleus order, then declaration order), then free-standing projections (merged order), then gap junctions. Within a projection, targets go in ascending index order, and sources in ascending index order within each target.

### 6.2 Per-step update order
For step $n$ ($t \to t + dt$):
0. **Controls.** Apply control values set since the last step.
1. **Spike delivery.** Pop ring-buffer slot $n$. For each arriving event: add release to the pools ([§4.2](#42-neurotransmitters-ligand-pools)), using presynaptic factors from the previous step's activations. Then run the pre-arrival coincidence updates ([§4.4.2](#442-stage-1--coincidence-models)).
2. **Sensory injection.** Poisson and TTFS kicks to $V$; current-based encoders set $I_{\text{sensory}}$.
3. **Clearance** of every pool, then `LigandClamp`.
4. **Receptors.** Update activations $a \to s$ and desensitisation $D$. Accumulate the batch sums of $C$. Update modulation factors $F$ (and modulation running references).
5. **Currents** $I_{\text{syn}}$, $I_{\text{gap}}$, $I_{\text{int}}$ (advance OU/shot noise), $I_h$, using state from the start of the step.
6. **Membrane integration.** `neuron_substeps` forward-Euler sub-steps of the nonlinear voltage equations with the currents held fixed. Recovery variables ($u$, $w$) use one Euler step. Detect spikes, reset, apply refractoriness. Detect plateau onsets. Update calcium.
7. **Event processing.** For each neuron with events, in ascending index order:
   - STP update and event enqueue for each outgoing projection;
   - post-event coincidence updates (spikes and plateaus);
   - `activity_release`;
   - rate traces (homeostasis, rate gates);
   - motor traces.
8. **Per-step plasticity.** `CalciumControl` and `VoltageClopath` LTP terms for active synapses; Clopath voltage filters.
9. If $(n+1)\,dt$ is a multiple of $\Delta_p$, run the batch:
   - transfer ([§4.4.3](#443-stage-2--ligand-gated-transfer));
   - consolidation;
   - synaptic scaling;
   - coupling-reference updates;
   - `BCM_Rate` batch terms.
10. If it is a multiple of $\Delta_s$: **structural update** (prune, sprout, neurogenesis births).
11. **Recording** of all probes due at this step.

### 6.3 Numerical requirements
- Every linear decay (pools, receptor cascades, desensitisation, calcium, traces, STP, OU, consolidation decay) **MUST** use exact or exponential-Euler updates. Plain Euler on these is not conforming.
- Single precision (`float`) is sufficient for state. Timestamps **MUST** be integer step counts.

### 6.4 Determinism
- All randomness comes from a counter-based generator (Philox4x32-10), keyed by (`seed`, stream ID, entity index, step). The stream IDs are fixed: `Placement`, `Jitter`, `Topology`, `Weights`, `GapJunctions`, `IntrinsicNoise`, `SensoryEncoding`, `Structural`, `Recording`.
- Floating-point accumulation into shared targets (pools, gap currents, heterosynaptic updates) **MUST** run in a fixed order, regardless of thread scheduling. For example, accumulate per target in ascending synapse index.
- Control changes are part of the input stream: the same sequence of (step, id, value) gives the same result.

---

## 7. Validation Rules

The compiler **MUST** reject a configuration with any error and **SHOULD** report every warning.

**Errors**
1. Wrong `schema_version`; a missing required section or field; an unknown or inapplicable property; an invalid identifier; the identifier `"None"`.
2. A missing include file; an include cycle; `simulation` defined by more than one document when the root has none; a conflicting duplicate definition ([§5.3](#53-merging)); an `extends` cycle or unknown parent; an unresolvable or ambiguous reference; duplicate qualified ids or duplicate population names within a nucleus.
3. `plasticity_update_interval_ms` not a multiple of `dt_ms`, or `structural_update_interval_ms` not a multiple of it.
4. `compartments` not allowed for the model; `dendrite`/`dendrites` missing or present on the wrong model; a `dendrites` parent graph that is not a tree rooted at the soma.
5. `composition` fractions not summing to 1; receptor expression (including via `augment`) on a compartment the cell type does not have; `depth_range` outside $[-1, 1]$ or empty; `feature_space` lattice size mismatch.
6. `target_compartment` not on the target cell type.
7. **Dead projection:** a released ligand is not read in the target compartment. It is read if any of these holds: a receptor for it is expressed there; a modulator coupling of a plastic projection into that compartment reads it; or a consolidation `capture_ligand` reads it in that compartment. For co-transmission, this applies to every component.
8. `cellular_modulation` missing on a `MetabotropicLinearGain` receptor or present on a conductance receptor; `g_max` missing on a conductance receptor; `ReceptorConductance` naming a non-conductance or unknown receptor; `PresynapticRelease` listing a projection that does not target the compartment where the receptor is expressed.
9. `ExponentialDecay` without `clearance_tau_ms`; `MichaelisMenten` without `v_max`/`k_m`; both kinds of field present.
10. **Michaelis–Menten divergence:** for any pool, the worst-case sustained release $\sum_{\text{proj}} \bar K \cdot (r_{\max}/1000)\cdot w_{\text{upper}}\cdot q\cdot\rho$ (plus `activity_release` at $r_{\max}$) $\ge V_{\max}$. Here $\bar K$ is the realised mean indegree (sum of link factors for volume links), $r_{\max}$ is `validation_max_rate_hz`, and $w_{\text{upper}}$ is `w_max` (plastic) or the largest initial weight (static).
11. `FixedIndegree` with $k > N_{\text{src}}$; `OneToOne` with unequal sizes; `Kernel` in `Feature` space between incompatible feature spaces; `VonMises` on a non-periodic or multi-axis space; an `ExplicitList` rank out of range, duplicate pair, or forbidden self-pair.
12. `structural_plasticity: true` on a projection whose target cell type has no `structural_plasticity` object, or without `sprout_initial_weight`; `Volume` release with a plastic or structural synapse, or with a `topology`; `synaptic_scaling` other than `None` into a cell type without `homeostasis.synaptic_scaling`.
13. `CalciumControl` on a target compartment without calcium; `post_event: DendriticPlateau` or `PlateauBTSP` without a valid `post_event_compartment` that has a `plateau`; `activity_release` on an event compartment without a plateau.
14. `Uniform` with min > max; a non-positive `std`, `sigma`, `tau`, extent or radius; `w_min > w_max`; `min_input >= max_input` on any axis.
15. A runtime control, probe or augment referencing an unknown nucleus, population, projection, rule, receptor, ligand, input, motor output or control; a duplicate control id; a `sample_interval_ms` not a multiple of `dt_ms`.

**Warnings**
1. An expressed receptor whose ligand pool is never written and has `baseline_ambient` = 0 (never activated).
2. A modulator coupling or capture ligand that is never written in the synapse's target or capture compartment (inert).
3. A population with no inbound drive (no afferent projection, sensory input or intrinsic current), or with no efferent projection and no motor readout (dead end).
4. More than 1% of initial weight mass clipped by `w_min`/`w_max`.
5. Realised mean indegree < 1 for any projection.
6. A modulation target with no effect on the model (`SpikeAdaptation` on `LIF`, `DendriticCoupling` on a single-compartment cell).
7. Overlapping sensory subranges on one population.
8. A three-factor rule with $\beta_0\,\tau_{\text{trace}} > 0.1$ (large ungated drift).
9. A neurogenic population with a non-structural incoming or outgoing projection.
10. An included document whose `simulation` is ignored because the root defines its own.

The compiler **SHOULD** print a per-projection table of realised synapse counts, mean/min/max indegree, and delay range.

---

## 8. Reference Examples

| File | Role |
| :--- | :--- |
| [`examples/brain.json`](../examples/brain.json) | Base model: closed-loop conditioned avoidance and motor control. Complete on its own. |
| [`examples/modules/neuromodulators.json`](../examples/modules/neuromodulators.json) | Namespace-free shared library: noradrenaline (`NE`) and its β-adrenergic receptor. |
| [`examples/modules/fear_circuit.json`](../examples/modules/fear_circuit.json) | Amygdala and locus coeruleus (namespace `fear`). |
| [`examples/modules/hippocampus.json`](../examples/modules/hippocampus.json) | Entorhinal–dentate–CA3–CA1 memory loop (namespace `hpc`). |
| [`examples/modules/head_direction.json`](../examples/modules/head_direction.json) | Ring attractor with path integration (namespace `hd`). |
| [`examples/brain_extended.json`](../examples/brain_extended.json) | Root that includes all of the above, with recording and runtime controls. |

`brain_extended.json` adds three regions to `brain.json` without editing it. This demonstrates [§5.6](#56-extensibility-guarantee).

### 8.1 Base model (`brain.json`)
It implements a **self-organising conditioned avoidance and motor control loop**:
1. **`aras_core`** pacemakers keep a tonic cholinergic (`ACh`) arousal tone on cortical apical dendrites (`M1_Muscarinic` → `MembraneExcitability`). Cortical activity feeds back onto ARAS interneurons, which inhibit the pacemakers. This is a negative-feedback arousal loop.
2. **`sensory_thalamus_vpl`** receives 64 somatosensory channels (subrange 0–0.8) and 8 proprioceptive channels (subrange 0.8–1.0), with local feedforward inhibition. It relays topographically to **`cortex_S1_M1`**.
3. **`cortex_S1_M1`** has recurrent excitation (three-factor STDP, structural plasticity), E→I drive onto basket cells, perisomatic inhibition with iSTDP, mutual inhibition, and electrically coupled basket cells. It projects to the motor pool with broad random wiring (`Random`, about 60 inputs per motor neuron), so any cortical pattern can learn to drive any muscle channel. Only the innate reflex is channel-aligned.
4. **`nociceptive_relay`** receives an 8-channel error signal. It triggers an **innate reflex** (static topographic arc onto the matching motor channels). It also drives **`vta_modulator`** interneurons, which **inhibit the DA pacemakers**: a DA *dip* below the running reference depresses recently tagged synapses.
5. **`appetitive_reward_input`** depolarises the VTA pacemakers: a DA *burst* above the reference consolidates tagged synapses. DA reaches **both** the cortical apical pools (recurrent synapses) and the spinal somatic pools (corticospinal synapses). That is where the eligibility traces of the motor pathway live.
6. **`motor_ventral_horn`** has Renshaw-like recurrent inhibition. Its 8 channels are decoded as rate traces normalised to 50 Hz.

Worst-case DA release per pool is 20 × 0.1 ms⁻¹ × 1.0 × 0.002 = 0.004 c.u./ms, below $V_{\max}$ = 0.005, so the pool is bounded. At tonic 5 Hz the DA pool sits about 0.008 above ambient, and a 20 Hz burst lifts it about 0.04. ACh settles at about 20 × 0.005 × 0.0025 × 400 ≈ 0.1 above ambient at 5 Hz. The longest delay is about 37 ms (VTA → cortex), so the ring buffer needs at least 75 slots at `dt` = 0.5 ms.

### 8.2 Extension modules
- **`fear_circuit`** (amygdala). A locus coeruleus releases `NE` during nociceptive input. The lateral amygdala receives the CS (thalamic and cortical, through free-standing projections from base nuclei) and the US (nociceptive relay). CS synapses learn with NE-gated three-factor STDP. Intercalated cells gate the central nucleus, whose rate is read out as a `freezing_response`. An `augment` adds β-adrenergic receptors to cortical pyramidal apical dendrites, and NE reaches them by **volume transmission**.
- **`hippocampus`**:
  - Entorhinal cells have 2-D place-tuned input (`MultiDimGaussianReceptiveField`).
  - Dentate granule cells have **neurogenesis** and calcium-based plasticity (`CalciumControl`).
  - CA3 has recurrent collaterals learning with `VoltageClopath`, suppressed by septal ACh through a `PresynapticRelease` heteroreceptor (encoding/retrieval switching).
  - CA1 pyramidal cells are **3-compartment-plus-tuft** (`Izhikevich_MC`). Entorhinal input to the tuft triggers plateaus, which drive **`PlateauBTSP`** at CA3→CA1 synapses with soft bounds and **tag-and-capture consolidation**. The plateau-triggered `activity_release` of `PRP` supplies the capture signal.
- **`head_direction`**. A ring population with periodic **feature space**. Recurrent `VonMises` excitation and global inhibition form a bump attractor. A shifted (`offset`) rotation population, driven by angular velocity, moves the bump. A visual-cue input is tuned through `FeatureSpace` centres, and the heading is decoded with a `PopulationVector` from feature coordinates.

### 8.3 Realised connectivity of `brain.json`
From a 200-target Monte Carlo sample of the placement model:

| Projection | Mean indegree (min–max) | Mean delay (ms) |
| :--- | :--- | :--- |
| `aras_cholinergic_tone` | 20 | 31.5 |
| `aras_local_inhibition` | 30 | 4.0 |
| `mesocortical_dopamine_projection` | 20 | 36.8 |
| `mesospinal_dopamine_projection` | 20 | 36.5 |
| `vta_local_inhibition` | 36 | 3.1 |
| `thalamocortical_lemniscal_tract` | 27.1 (14–42) | 4.0 |
| `thalamic_relay_to_interneuron` | 80 | 3.1 |
| `thalamic_feedforward_inhibition` | 40 | 6.1 |
| `innate_withdrawal_reflex_arc` | 9.1 (1–14) | 2.1 |
| `aversive_vta_suppression` | 40 | 3.0 |
| `cortical_recurrent_association` | 52.9 (29–82) | 3.4 |
| `cortical_excitation_of_interneurons` | 36.7 (19–52) | 3.4 |
| `L23_perisomatic_inhibition` | 23.8 (9–34) | 5.2 |
| `interneuron_mutual_inhibition` | 14.2 (6–20) | 5.1 |
| `corticospinal_pyramidal_tract` | 60 | 4.3 |
| `corticofugal_aras_feedback` | 40 | 12.6 |
| `motor_recurrent_collaterals` | 80 | 1.5 |
| `recurrent_motor_inhibition` | 20 | 1.5 |

### 8.4 `brain.json` listing
The listing below must stay byte-identical to the file.

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
          "topology": { "type": "Random", "probability": 0.0075 },
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
