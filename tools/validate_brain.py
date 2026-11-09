#!/usr/bin/env python3
"""Reference validator for brain.json documents (schema v4.3).

Usage:
    python3 tools/validate_brain.py examples/brain_extended.json

Requires numpy. Loads the root document and its includes, resolves namespaces,
`extends` and `augment`, then checks references and a subset of the validation
rules in docs/brain-json-spec.md section 7: dead releases, inert couplings,
unread receptors, Michaelis-Menten divergence, weight clipping, feature-space
compatibility, plateau/calcium prerequisites, structural/scaling configuration,
cycles, and probe/control references.

It also prints realised mean/min/max indegree and mean delay per projection,
estimated by Monte Carlo over a sample of up to 200 target neurons (fixed seed).

This is a development aid, not the engine's compiler: it does not check every
field or enum value, and its placement sampling does not follow the engine's
Philox RNG streams. Exit code is 1 if any error is found.
"""
import json, sys, os, math, copy, re
import numpy as np
from math import erf, sqrt, log

ERR, WARN = [], []
DICTS = ["neurotransmitters", "receptors", "plasticity_rules", "short_term_dynamics", "cell_types"]
IDRE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def q(ns, name): return f"{ns}.{name}" if ns else name

# ---------- loading ----------
loaded = {}   # (path, ns) -> True
docs = []     # post-order list of (doc, ns, dir)
def load(path, ns, stack):
    path = os.path.realpath(path)
    key = (path, ns)
    if path in stack: ERR.append(f"include cycle at {path}"); return
    if key in loaded: return
    loaded[key] = True
    d = json.load(open(path))
    for inc in d.get("includes", []):
        if inc.get("root_namespace") and "namespace" in inc: ERR.append("root_namespace with namespace")
        cns = "" if inc.get("root_namespace") else (q(ns, inc["namespace"]) if "namespace" in inc else ns)
        load(os.path.join(os.path.dirname(path), inc["path"]), cns, stack | {path})
    docs.append((d, ns, os.path.dirname(path), path))

root = sys.argv[1]
load(root, "", frozenset())
rootdoc = docs[-1][0]

def resolve(name, ns, table, what):
    if "." in name:
        if name in table: return name
    else:
        parts = ns.split(".") if ns else []
        for i in range(len(parts), -1, -1):
            cand = q(".".join(parts[:i]), name)
            if cand in table: return cand
    ERR.append(f"unresolved {what} '{name}' from ns '{ns}'"); return None

# ---------- merge dictionaries ----------
defs = {s: {} for s in DICTS}
defns = {s: {} for s in DICTS}
for d, ns, _, path in docs:
    for s in DICTS:
        for k, v in d.get(s, {}).items():
            if not IDRE.match(k) or k == "None": ERR.append(f"bad id {k}")
            qk = q(ns, k)
            if qk in defs[s] and defs[s][qk] != v: ERR.append(f"conflicting duplicate {s}.{qk}")
            defs[s][qk] = v; defns[s][qk] = ns

def deep_merge(parent, child):
    if isinstance(child, dict) and child.get("$replace"):
        c = {k: v for k, v in child.items() if k != "$replace"}; return c
    if not (isinstance(parent, dict) and isinstance(child, dict)): return copy.deepcopy(child)
    out = copy.deepcopy(parent)
    for k, v in child.items():
        if v is None: out.pop(k, None)
        elif k in out: out[k] = deep_merge(out[k], v)
        else: out[k] = deep_merge({}, v) if isinstance(v, dict) and v.get("$replace") else copy.deepcopy(v)
    return out

resolved = {s: {} for s in DICTS}
def resolve_entry(s, k, seen=()):
    if k in resolved[s]: return resolved[s][k]
    v = defs[s][k]
    if "extends" in v:
        if k in seen: ERR.append(f"extends cycle {k}"); return v
        pk = resolve(v["extends"], defns[s][k], defs[s], f"{s} parent")
        if pk is None: return v
        parent = resolve_entry(s, pk, seen + (k,))
        child = {kk: vv for kk, vv in v.items() if kk != "extends"}
        v = deep_merge(parent, child)
    resolved[s][k] = v; return v
for s in DICTS:
    for k in list(defs[s]): resolve_entry(s, k)
NT, RC, PR, ST, CT = (resolved[s] for s in DICTS)
def bail():
    if ERR: print("ERRORS", ERR); print("WARNINGS", WARN); sys.exit(1)
bail()

# resolve references inside definitions
for k, r in RC.items():
    r["ligand"] = resolve(r["ligand"], defns["receptors"][k], NT, "ligand")
    mods = r.get("cellular_modulation")
    if mods is not None:
        if r["kinetics"] != "MetabotropicLinearGain": ERR.append(f"modulation on conductance receptor {k}")
        for m in (mods if isinstance(mods, list) else [mods]):
            if m["target"] == "ReceptorConductance": m["receptor"] = resolve(m["receptor"], defns["receptors"][k], RC, "receptor")
            if m["target"] == "PresynapticRelease" and "projections" in m:
                m["_ns"] = defns["receptors"][k]
    elif r["kinetics"] == "MetabotropicLinearGain": ERR.append(f"metabotropic without modulation {k}")
    if r["kinetics"] != "MetabotropicLinearGain" and "g_max" not in r: ERR.append(f"g_max missing {k}")
for k, rule in PR.items():
    ns = defns["plasticity_rules"][k]
    for c in rule.get("modulator_couplings", []): c["ligand"] = resolve(c["ligand"], ns, NT, "ligand")
    if "consolidation" in rule: rule["consolidation"]["capture_ligand"] = resolve(rule["consolidation"]["capture_ligand"], ns, NT, "ligand")
for k, n in NT.items():
    em = n["clearance_model"] == "ExponentialDecay"
    if em != ("clearance_tau_ms" in n) or (not em) != ("v_max" in n and "k_m" in n): ERR.append(f"clearance fields {k}")
for k, c in CT.items():
    for ar in c.get("activity_release", []): ar["ligand"] = resolve(ar["ligand"], defns["cell_types"][k], NT, "ligand")
    m = c["model"]; comps = c["compartments"]
    if m in ("Izhikevich_1C", "AdEx", "LIF") and comps != ["Soma"]: ERR.append(f"compartments {k}")
    if m == "Izhikevich_2C" and ("dendrite" not in c or len(comps) != 2): ERR.append(f"2C {k}")
    if m == "Izhikevich_MC":
        dd = c.get("dendrites", {})
        if set(dd) != set(comps) - {"Soma"} or "Soma" not in comps: ERR.append(f"MC compartments {k}")
        for comp in dd:
            seen = set(); cur = comp
            while cur != "Soma":
                if cur in seen or cur not in dd: ERR.append(f"MC tree {k}"); break
                seen.add(cur); cur = dd[cur]["parent"]

# ---------- nuclei & populations ----------
nuclei, nucns = {}, {}
for d, ns, _, _ in docs:
    for n in d.get("nuclei", []):
        qn = q(ns, n["id"]); n = copy.deepcopy(n); n["_ns"] = ns
        if qn in nuclei: ERR.append(f"dup nucleus {qn}")
        nuclei[qn] = n
rng = np.random.default_rng(0)

def rot(r):
    rx, ry, rz = np.radians(r)
    Rx = np.array([[1,0,0],[0,np.cos(rx),-np.sin(rx)],[0,np.sin(rx),np.cos(rx)]])
    Ry = np.array([[np.cos(ry),0,np.sin(ry)],[0,1,0],[-np.sin(ry),0,np.cos(ry)]])
    Rz = np.array([[np.cos(rz),-np.sin(rz),0],[np.sin(rz),np.cos(rz),0],[0,0,1]])
    return Rz @ Ry @ Rx

pops = {}
for qn, n in nuclei.items():
    shape = n.get("shape", {"type": "Sphere", "radius_mm": n.get("radius_mm")})
    t = shape["type"]
    h = np.array([shape["radius_mm"]]*3) if t == "Sphere" else np.array(shape["radii_mm"]) if t == "Ellipsoid" else np.array(shape["size_mm"])/2
    R = rot(shape.get("rotation_deg", [0,0,0])); la = n.get("layer_axis", 2)
    if abs(sum(c["fraction"] for c in n["composition"]) - 1) > 1e-6: ERR.append(f"fractions {qn}")
    names = set()
    for c in n["composition"]:
        name = c.get("name", c["cell_type"])
        if name in names: ERR.append(f"dup population {qn}/{name}")
        names.add(name)
        ctk = resolve(c["cell_type"], n["_ns"], CT, "cell_type"); ct = CT[ctk]
        N = round(n["size"]*c["fraction"])
        dr = c.get("depth_range", [-1, 1])
        pts = []
        while len(pts) < N:
            u = rng.uniform(-1, 1, size=(4*N, 3))
            ok = (np.linalg.norm(u, axis=1) <= 1) if t != "Box" else np.ones(len(u), bool)
            ok &= (u[:, la] >= dr[0]) & (u[:, la] <= dr[1])
            pts.extend(u[ok][: N - len(pts)])
        u = np.array(pts)
        x = np.array(n["coordinates_mm"]) + (u*h) @ R.T
        fs = c.get("feature_space"); phi = None
        if fs:
            L = np.array(fs["extent"])
            if fs["layout"] == "Lattice":
                shp = fs["lattice_shape"]
                if int(np.prod(shp)) != N: ERR.append(f"lattice size {qn}/{name}")
                idx = np.array(np.unravel_index(np.arange(N), shp)).T
                phi = (idx + 0.5) * L / np.array(shp)
            else: phi = rng.random((N, len(L))) * L
        dormant = np.zeros(N, bool)
        if "neurogenesis" in c: dormant[N - math.ceil(c["neurogenesis"]["reserve_fraction"]*N):] = True
        rec = {}
        for comp, rl in c["receptors"].items():
            if comp not in ct["compartments"]: ERR.append(f"receptor comp {qn}/{name}/{comp}")
            rec[comp] = set(resolve(r, n["_ns"], RC, "receptor") for r in rl)
        pops[(qn, name)] = dict(N=N, u=u, x=x, phi=phi, fs=fs, ct=ct, ctk=ctk, rec=rec, dormant=dormant, neuro="neurogenesis" in c)

# augment
for d, ns, _, _ in docs:
    for a in d.get("augment", {}).get("populations", []):
        qn = resolve(a["nucleus"], ns, nuclei, "nucleus")
        p = pops.get((qn, a["population"]))
        if not p: ERR.append(f"augment pop {a}"); continue
        for comp, rl in a["add_receptors"].items():
            if comp not in p["ct"]["compartments"]: ERR.append("augment comp")
            p["rec"].setdefault(comp, set()).update(resolve(r, ns, RC, "receptor") for r in rl)

# ---------- projections ----------
projs = {}
for d, ns, ddir, _ in docs:
    lst = [(p, ns, q(ns, n["id"])) for n in d.get("nuclei", []) for p in n.get("projections", [])]
    lst += [(p, ns, None) for p in d.get("projections", [])]
    for p, pns, fromn in lst:
        p = copy.deepcopy(p); qid = q(pns, p["id"])
        if qid in projs: ERR.append(f"dup projection {qid}")
        p["_from"] = fromn or resolve(p["from_nucleus"], pns, nuclei, "nucleus")
        p["_to"] = resolve(p["to_nucleus"], pns, nuclei, "nucleus")
        tr = p["transmitter"]
        comps = [{"ligand": tr}] if isinstance(tr, str) else tr
        p["_ligs"] = [(resolve(c["ligand"], pns, NT, "ligand"), c.get("release_scale", 1.0)) for c in comps]
        if len({l for l, _ in p["_ligs"]}) != len(p["_ligs"]): ERR.append(f"dup co-transmitter {qid}")
        sy = p["synapse"]
        sy["_stp"] = None if sy["stp_rule"] == "None" else resolve(sy["stp_rule"], pns, ST, "stp")
        sy["_ltp"] = None if sy["ltp_rule"] == "None" else resolve(sy["ltp_rule"], pns, PR, "ltp")
        p["_ns"] = pns; projs[qid] = p

def coords(pop, space, axes):
    if space == "Feature": return pop["phi"][:, axes]
    if space == "Normalized": return pop["u"][:, axes]
    return pop["x"][:, axes]

def kernel_val(k, delta):
    t = k["type"]
    if t == "Gaussian":
        s = np.array(k["sigma"]) if isinstance(k["sigma"], list) else k["sigma"]
        return np.exp(-0.5*((delta/s)**2).sum(1))
    d = np.linalg.norm(delta, axis=1)
    if t == "DifferenceOfGaussians":
        return k["amp_center"]*np.exp(-d**2/(2*k["sigma_center"]**2)) - k["amp_surround"]*np.exp(-d**2/(2*k["sigma_surround"]**2))
    if t == "Box": return (d <= k["radius"]).astype(float)
    if t == "Constant": return np.ones(len(d))
    raise ValueError(t)

def displacement(src, tgt, ti, spec):
    space = spec["space"]; axes = spec.get("axes", [0, 1, 2] if space != "Feature" else list(range(len(src["fs"]["extent"]))))
    if space == "Feature":
        for a in axes:
            if not (src["fs"] and tgt["fs"]) or src["fs"]["extent"][a] != tgt["fs"]["extent"][a] or src["fs"]["periodic"][a] != tgt["fs"]["periodic"][a]:
                ERR.append("incompatible feature spaces"); return None, axes
    delta = coords(tgt, space, axes)[ti] - coords(src, space, axes) - np.array(spec.get("offset", [0.0]*len(axes)))
    if space == "Feature":
        for j, a in enumerate(axes):
            if src["fs"]["periodic"][a]:
                L = src["fs"]["extent"][a]; delta[:, j] = (delta[:, j] + L/2) % L - L/2
    return delta, axes

def probs(p, src, tgt, ti, same):
    t = p["topology"]; ty = t["type"]
    if ty == "Random": pr = np.full(src["N"], t["probability"])
    elif ty == "AllToAll": pr = np.ones(src["N"])
    elif ty == "OneToOne":
        if src["N"] != tgt["N"]: ERR.append(f"OneToOne sizes {p['id']}")
        pr = np.zeros(src["N"]); pr[ti] = 1; return pr
    elif ty == "FixedIndegree":
        if t["k"] > (~src["dormant"]).sum(): ERR.append(f"k too large {p['id']}")
        return None
    elif ty == "SpatialGaussian":
        pr = t["max_prob"]*np.exp(-((src["x"]-tgt["x"][ti])**2).sum(1)/(2*t["sigma_mm"]**2))
    elif ty == "Topographic":
        ax = t.get("axes", [0, 1, 2]); pr = t["max_prob"]*np.exp(-((src["u"][:, ax]-tgt["u"][ti, ax])**2).sum(1)/(2*t["sigma_rel"]**2))
    elif ty == "Kernel":
        delta, axes = displacement(src, tgt, ti, t)
        if delta is None: return np.zeros(src["N"])
        if t["kernel"]["type"] == "VonMises":
            if len(axes) != 1 or not src["fs"]["periodic"][axes[0]]: ERR.append("VonMises on non-periodic")
            L = src["fs"]["extent"][axes[0]]
            K = np.exp(t["kernel"]["kappa"]*(np.cos(2*np.pi*delta[:, 0]/L)-1))
        else: K = kernel_val(t["kernel"], delta)
        pr = np.clip(t["max_prob"]*K, 0, 1)
    else: raise ValueError(ty)
    pr = pr.copy()
    if same and not t.get("allow_autapses", False): pr[ti] = 0
    pr[src["dormant"]] = 0
    return pr

writes = {}   # (nuc,pop,comp,lig) -> list of (kind, info)
indeg = {}
print(f"{'projection':45s} {'mean_K':>7s} {'min':>6s} {'max':>6s} {'delay':>6s}")
for qid, p in projs.items():
    sk, tk = (p["_from"], p["from_type"]), (p["_to"], p["to_type"])
    if sk not in pops or tk not in pops: ERR.append(f"{qid} population missing {sk} {tk}"); continue
    src, tgt = pops[sk], pops[tk]; comp = p["target_compartment"]
    if comp not in tgt["ct"]["compartments"]: ERR.append(f"{qid} compartment")
    sy = p["synapse"]
    if sy["structural_plasticity"] and ("structural_plasticity" not in tgt["ct"] or "sprout_initial_weight" not in sy): ERR.append(f"{qid} structural config")
    if sy.get("synaptic_scaling", "None") != "None" and "synaptic_scaling" not in tgt["ct"].get("homeostasis", {}): ERR.append(f"{qid} scaling without target config")
    if (src["neuro"] or tgt["neuro"]) and not sy["structural_plasticity"]: WARN.append(f"{qid}: non-structural projection on neurogenic population")
    ts = np.flatnonzero(~tgt["dormant"]); ts = rng.choice(ts, size=min(200, len(ts)), replace=False)
    if p.get("release_mode") == "Volume":
        if "topology" in p or sy["_ltp"] or sy["structural_plasticity"]: ERR.append(f"{qid} volume config")
        v = p["volume"]; nsrc = (~src["dormant"]).sum()
        centers = tgt["x"][rng.integers(tgt["N"], size=nsrc*v["arbors_per_source"])]
        ks = []
        for i in ts:
            d = np.linalg.norm(centers - tgt["x"][i], axis=1); m = d <= v["cutoff_mm"]
            ks.append(np.exp(-d[m]**2/(2*v["sigma_mm"]**2)).sum())
        ks = np.array(ks); centroid = centers
    else:
        ks = []
        for i in ts:
            pr = probs(p, src, tgt, i, sk == tk)
            ks.append(p["topology"]["k"] if pr is None else pr.sum())
        ks = np.array(ks, float); centroid = tgt["x"]
    dl = np.linalg.norm(src["x"][rng.integers(src["N"], size=500)] - centroid[rng.integers(len(centroid), size=500)], axis=1).mean()/p["conduction_velocity_m_s"]
    indeg[qid] = ks.mean()
    print(f"{qid:45s} {ks.mean():7.1f} {ks.min():6.1f} {ks.max():6.1f} {dl:6.1f}")
    if ks.mean() < 1: WARN.append(f"{qid} mean indegree < 1")
    for lig, rs in p["_ligs"]:
        writes.setdefault((tk[0], tk[1], comp, lig), []).append(("proj", qid, rs))
    # weight clipping
    w = sy["weight_distribution"]; r = sy["_ltp"]
    lo, hi = (PR[r]["w_min"], PR[r]["w_max"]) if r else (0, math.inf)
    Phi = lambda z: 0.5*(1+erf(z/sqrt(2)))
    if w["type"] == "LogNormal": m = (1-Phi((log(hi)-w["mu"])/w["sigma"]) if hi < math.inf else 0) + (Phi((log(lo)-w["mu"])/w["sigma"]) if lo > 0 else 0)
    elif w["type"] == "Gaussian": m = (1-Phi((hi-w["mean"])/w["std"]) if hi < math.inf else 0) + Phi((lo-w["mean"])/w["std"])
    elif w["type"] == "Constant": m = 0 if lo <= w["value"] <= hi else 1
    else: m = 0
    if m > 0.01: WARN.append(f"{qid} clips {m:.1%}")
    # rule-specific checks
    if r:
        rule = PR[r]; cm = rule["coincidence_model"]
        if cm == "CalciumControl" and "calcium" not in tgt["ct"]: ERR.append(f"{qid} CalciumControl without calcium")
        if cm == "PlateauBTSP" or rule.get("post_event") == "DendriticPlateau":
            pc = rule.get("post_event_compartment")
            dd = tgt["ct"].get("dendrites", {}); d2 = tgt["ct"].get("dendrite")
            ok = (pc in dd and "plateau" in dd[pc]) or (d2 is not None and pc in tgt["ct"]["compartments"] and pc != "Soma" and "plateau" in d2)
            if not ok: ERR.append(f"{qid} plateau compartment {pc}")
        if rule["base_transfer_rate"]*rule["trace_tau_ms"] > 0.1 and rule["modulator_couplings"]: WARN.append(f"{r} large ungated drift")

# activity release writes
for (qn, name), p in pops.items():
    for ar in p["ct"].get("activity_release", []):
        writes.setdefault((qn, name, ar["compartment"], ar["ligand"]), []).append(("activity", name, 1))
        if ar["event"] == "DendriticPlateau":
            ec = ar["event_compartment"]
            if "plateau" not in p["ct"].get("dendrites", {}).get(ec, {}): ERR.append(f"activity_release plateau comp {name}")

# readers
def reads(qn, name, comp, lig):
    p = pops[(qn, name)]
    if any(RC[r]["ligand"] == lig for r in p["rec"].get(comp, [])): return True
    for qid, pr in projs.items():
        if (pr["_to"], pr["to_type"]) != (qn, name) or not pr["synapse"]["_ltp"]: continue
        rule = PR[pr["synapse"]["_ltp"]]
        if pr["target_compartment"] == comp and any(c["ligand"] == lig for c in rule["modulator_couplings"]): return True
        co = rule.get("consolidation")
        if co and co["capture_ligand"] == lig and co.get("capture_compartment", "Soma") == comp: return True
    return False
for (qn, name, comp, lig), lst in writes.items():
    if not reads(qn, name, comp, lig):
        for kind, qid, _ in lst: ERR.append(f"dead release {kind} {qid}: {lig} into {qn}/{name}/{comp}")
for (qn, name), p in pops.items():
    for comp, rs in p["rec"].items():
        for r in rs:
            lig = RC[r]["ligand"]
            if (qn, name, comp, lig) not in writes and NT[lig]["baseline_ambient"] == 0: WARN.append(f"{qn}/{name}/{comp}/{r} never activated")
            mods = RC[r].get("cellular_modulation")
            for m in (mods if isinstance(mods, list) else [mods] if mods else []):
                if m["target"] == "PresynapticRelease":
                    for pj in m.get("projections", []):
                        qp = resolve(pj, m["_ns"], projs, "projection")
                        if qp and (projs[qp]["_to"], projs[qp]["to_type"], projs[qp]["target_compartment"]) != (qn, name, comp):
                            ERR.append(f"PresynapticRelease {r} lists {qp} not targeting {qn}/{name}/{comp}")
for qid, pr in projs.items():
    if not pr["synapse"]["_ltp"]: continue
    rule = PR[pr["synapse"]["_ltp"]]
    for c in rule["modulator_couplings"]:
        if (pr["_to"], pr["to_type"], pr["target_compartment"], c["ligand"]) not in writes: WARN.append(f"{qid}: coupling {c['ligand']} inert")
    co = rule.get("consolidation")
    if co and (pr["_to"], pr["to_type"], co.get("capture_compartment", "Soma"), co["capture_ligand"]) not in writes: WARN.append(f"{qid}: capture inert")

# io
sens, mot = {}, {}
for d, ns, _, _ in docs:
    io = d.get("io_interfaces", {})
    for s in io.get("sensory_inputs", []):
        qn = resolve(s["target_nucleus"], ns, nuclei, "nucleus"); sens[q(ns, s["id"])] = (qn, s["target_type"], s)
        if (qn, s["target_type"]) not in pops: ERR.append(f"input pop {s['id']}")
        if s["encoding"] == "MultiDimGaussianReceptiveField" and s["centers"]["type"] == "FeatureSpace":
            fs = pops[(qn, s["target_type"])]["fs"]
            if not fs or fs["dimensions"] != s["dimensions"]: ERR.append(f"FeatureSpace centers {s['id']}")
    for m in io.get("motor_outputs", []):
        qn = resolve(m["source_nucleus"], ns, nuclei, "nucleus"); mot[q(ns, m["id"])] = (qn, m["source_type"])
        if (qn, m["source_type"]) not in pops: ERR.append(f"output pop {m['id']}")
# drive / dead-end
for key, p in pops.items():
    inb = any((pr["_to"], pr["to_type"]) == key for pr in projs.values()) or any(v[:2] == key for v in sens.values()) or p["ct"]["intrinsic_current"]["type"] != "None"
    outb = any((pr["_from"], pr["from_type"]) == key for pr in projs.values()) or key in mot.values()
    if not inb: WARN.append(f"{key} no inbound drive")
    if not outb: WARN.append(f"{key} dead end")
# MM divergence
maxr = None
for d, *_ in docs:
    if "simulation" in d and (d is rootdoc or maxr is None): maxr = d["simulation"].get("validation_max_rate_hz", 100)/1000
for key, lst in writes.items():
    lig = NT[key[3]]
    if lig["clearance_model"] != "MichaelisMenten": continue
    rate = 0
    for kind, qid, rs in lst:
        if kind != "proj": continue
        sy = projs[qid]["synapse"]
        wu = PR[sy["_ltp"]]["w_max"] if sy["_ltp"] else sy["weight_distribution"].get("value", 1)
        rate += indeg[qid]*maxr*wu*lig["quantal_release"]*rs
    if rate >= lig["v_max"]: ERR.append(f"MM divergence {key}")
# recording & controls
ctrl_ids = set()
for d, ns, _, _ in docs:
    for c in d.get("runtime_controls", []):
        ctrl_ids.add(q(ns, c["id"]))
        for n in c.get("nuclei", []): resolve(n, ns, nuclei, "nucleus")
        for r in c.get("rules", []): resolve(r, ns, PR, "rule")
        for pj in c.get("projections", []): resolve(pj, ns, projs, "projection")
        if "receptor" in c: resolve(c["receptor"], ns, RC, "receptor")
        if "ligand" in c: resolve(c["ligand"], ns, NT, "ligand")
        if "input" in c: resolve(c["input"], ns, sens, "input")
for d, ns, _, _ in docs:
    for pb in d.get("recording", {}).get("probes", []):
        if "nucleus" in pb:
            qn = resolve(pb["nucleus"], ns, nuclei, "nucleus")
            if (qn, pb["population"]) not in pops: ERR.append(f"probe pop {pb['id']}")
            p = pops.get((qn, pb["population"]))
            for v in pb["variables"]:
                m = re.match(r"(V|Calcium|Plateau):(\w+)$", v)
                if m and m.group(2) not in p["ct"]["compartments"]: ERR.append(f"probe comp {v}")
                if m and m.group(1) == "Calcium" and "calcium" not in p["ct"]: ERR.append(f"probe calcium {v}")
                m = re.match(r"(Ligand|Activation):([\w.]+)@(\w+)$", v)
                if m:
                    tbl = NT if m.group(1) == "Ligand" else RC
                    resolve(m.group(2), ns, tbl, m.group(1))
        if "projection" in pb: resolve(pb["projection"], ns, projs, "projection")
        if "motor_output" in pb: resolve(pb["motor_output"], ns, mot, "motor output")
        if "control" in pb: resolve(pb["control"], ns, ctrl_ids, "control")
sims = [d for d, *_ in docs if "simulation" in d]
if "simulation" not in rootdoc and len(sims) != 1: ERR.append("simulation source ambiguous")
print("DOCS", [os.path.relpath(p) for *_, p in docs])
print("ERRORS", ERR); print("WARNINGS", WARN)
sys.exit(1 if ERR else 0)
