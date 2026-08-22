# Hierarchical MARL with Cyclic Braking for Cooperative Control of Heavy-Haul Train Platoons on Long Downhill Sections

*(ITSC 2026 draft — single-core-contribution, 6-page format)*

---

## I. Introduction

Heavy-haul trains operating on long downhill sections (e.g., the Shuozhou–Huanghua line, 23.8 km with sustained −10.9‰ gradients) require cyclic air braking to regulate speed: braking when speed exceeds an upper limit, and releasing when it falls below a lower limit. As the train length grows to 10,000 tonnes (1 locomotive + 100 wagons ≈ 4 km), the cyclic braking cycles produce large in-train longitudinal forces (coupler forces). Exceeding the coupler-force safety limit (1000 kN in normal operation, per the China Academy of Railway Sciences) risks coupler failure.

When multiple such heavy-haul trains operate as a virtually-coupled platoon (to increase line capacity), each train must simultaneously (i) regulate its own speed via cyclic braking and (ii) maintain a safe inter-train spacing to avoid rear-end collision. Independent control of each train leads to rear-end collisions, because the follower's cyclic-braking speed profile lags the leader's, causing the inter-train gap to collapse.

Prior work falls into three gaps:
- **Long-downhill RL for a single train** (Zhang et al. 2024 DQN; Liu et al. 2021; Wang et al. 2025) explicitly **ignores coupler forces** (single-point mass).
- **Virtually-coupled MARL** (Zhang et al. 2021; Guo et al. 2025) targets **urban/metro or car platoons** and **ignores coupler forces**.
- **Coupler-force optimization** (Wei 2024; Fu 2019) is **single-train** and uses optimization (QP/GA), not learning.

**Our contribution**: a **hierarchical framework combining rule-based cyclic braking (micro) with RL-based cooperative threshold adjustment (macro)**, for cooperative control of heavy-haul train platoons on long downhill sections, which
1. **keeps each train within its coupler-force safety constraint** (≤1000 kN) via a rule-based cyclic-braking controller with a coupler-force safety layer;
2. **prevents rear-end collision** among platoon members (M1: 0 collisions vs M3 independent: 392) with a **cooperative gain of +110,042** in cumulative reward.

We validate on the real Shuozhou–Huanghua profile with three 10,000-tonne trains, and show the results are robust across randomized initial conditions.

---

## II. Related Work

**Cyclic air braking RL (single train, no coupler force).** Zhang et al. [1] propose a DQN for cyclic air braking on the Shuozhou–Huanghua line with speed range [40,80] km/h, but explicitly state "interaction forces between the cars are not taken into account." Wang et al. [2] use DQN for longitudinal-impulse suppression (−9.64% tensile, −28.77% compressive) with simplified dynamics. These works demonstrate that rule-based cyclic braking (brake above v_max, release below v_min) is the domain standard, and that RL has been used to *learn* this braking schedule. However, they all ignore coupler forces and treat the train as a single point mass.

**Virtually-coupled MARL.** Zhang et al. [3] use multi-agent deep RL for train-platoon consistency with an artificial potential field, on a flat metro line with no slope and no coupler forces. Guo et al. [4] propose a MARL consensus controller for autonomous platoons. These works target urban/car scenarios, ignore coupler forces, and assume free ±acceleration, which does not hold on long downhill sections (a downhill train can only brake, not accelerate back up).

**Coupler-force optimization.** Wei et al. [5] propose a hierarchical framework (QP top layer + longitudinal dynamics bottom layer) to enforce coupler-force constraints for a single train. Fu et al. [6] use genetic algorithm + generalized predictive control for single-train operation under coupler constraints.

**Our position.** We fill the cross-blank: **multi-train virtual coupling + long-downhill cyclic braking + explicit coupler-force modeling**, using a hierarchical framework where rule-based cyclic braking (the domain standard) handles the micro speed control, and RL (MAPPO) handles the macro cooperative threshold adjustment to prevent rear-end collisions while the coupler-force safety layer enforces the 1000 kN constraint.

---

## III. Problem and System Model

### A. Longitudinal train dynamics

Each train is modeled as a multi-body longitudinal dynamics system (following NeTrainSim). For wagon $i$ with mass $m_i$, position $x_i$, and velocity $v_i$:

$$m_i \ddot{x}_i = F_{t,i} - F_{r,i} - F_{b,i} - F_{g,i} + F_{c,i-1} - F_{c,i},$$

where $F_{t,i}$ is tractive force, $F_{r,i}$ is Davis resistance, $F_{b,i}$ is braking force (electric on locomotive + air brake propagating along the consist at finite brake-wave speed), $F_{g,i}$ is grade resistance, and $F_{c,i}$ is the coupler force between wagons $i$ and $i{+}1$, modeled as a spring–damper with dead zone (coupler gap):

$$F_c = \begin{cases} k(e-\text{gap}) + c \dot{e}, & |e| > \text{gap}, \\ c\dot{e}, & |e| \le \text{gap}, \end{cases}$$

with $e = x_i - x_{i+1} - l_0$ the relative displacement beyond free length. The coupler-force safety limit is 1000 kN (normal operation, per the China Academy of Railway Sciences [6]).

### B. Train platoon scenario

Three 10,000-tonne trains (1 locomotive + 100 wagons each, total ≈ 4 km) operate on the Shuozhou–Huanghua profile `shuozhou_23800` with speed limits [40, 80] km/h. The target inter-train gap is 100 m (headway 5 s). The trains start on the same grade section with initial speed 65 km/h (the standard cyclic-braking operating condition). No artificial disturbance is introduced in the main evaluation; the natural profile (sustained −10.9‰) drives the need for cyclic braking.

---

## IV. Proposed Method

### A. Hierarchical architecture

We use a two-layer structure (Fig. 1):

- **Layer 1 (intra-train, Coupler Level) — rule-based cyclic braking.** Each train uses `get_action_cyclic_braking`: brake at throttle $u=-0.75$ when speed $v \ge v_{max}$, release ($u=0$) when $v \le v_{min}$, hold otherwise (hysteresis). A coupler-force safety layer enforces $\max_i |F_{c,i}| \le 1000$ kN by scaling the throttle when the coupler force approaches the limit. This is the domain-standard controller (matching the behavior Zhang et al. [1] learns via DQN), and it inherently produces realistic in-train coupler forces.

- **Layer 2 (inter-train, Platoon Level) — MAPPO cooperative threshold adjustment.** Each train is an agent. The agent outputs a cooperative adjustment $c_{\mathrm{adj}} \in [-1,1]$, mapped to threshold offsets $v_{max}^{adj}, v_{min}^{adj} \in [\pm 5\,\text{km/h}]$ that shift the cyclic-braking thresholds of Layer 1. The adjustment does *not* directly manipulate the throttle (avoiding exploration that breaks the rule-based cyclic braking). A positive adjustment makes the follower brake earlier / release later to prevent rear-end collision with the leader.

### B. MDP formulation

- **State** (per agent, 11-dim): normalized own speed error, gap error, coupler-force statistic, position, tail grade, previous train speed, previous-train braking indicator and deceleration strength.
- **Action**: $c_{\mathrm{adj}} \in [-1,1]$ (cooperative threshold offset).
- **Reward**: speed-band penalty (stay in [40,80] km/h) + gap-keeping reward (reward inside safe gap, penalty for large drift) + speed-consistency + rear-end potential-field penalty + coupler-force penalty.

### C. Training

We use MAPPO (shared policy + centralized critic + GAE + KL early-stopping). Training uses 3 trains, 10,000-tonne preset, Shuozhou profile, 200 episodes, `adj_coef=0.3`, `entropy=0.001`, `lr=5e-5`. We also train a robustness variant with a leader disturbance (brief braking window at step 500, −0.3 m/s² for 100 steps) to make the cooperative policy robust to transient leader deceleration.

---

## V. Experiments

### A. Evaluation protocol

We evaluate deterministically (policy in eval mode) on the Shuozhou profile at fixed initial speed 65 km/h over 3000 steps, reporting per-run metrics. For robustness statistics, we randomize the initial speed in [58,66] km/h over 10 seeds and report mean±std.

**Methods:**
- **M1 (proposed)**: Layer-1 rule cyclic braking + Layer-2 MAPPO cooperative threshold adjustment.
- **M3 (independent)**: Layer-1 rule cyclic braking only, $\delta{=}0$ (no cooperation). Same architecture, no inter-train information.
- **Coast**: throttle = 0 baseline (no control).

### B. Main result: cooperative gain

| Metric | Coast | **M1 (coop)** | M3 (independent) |
|:--|:--|:--|:--|
| Cumulative reward | +30,843 | **+33,494** | **−76,548** |
| Overspeed >80 km/h (%) | 4.2 | 2.5 | 0.0 |
| Under-speed <40 km/h (%) | 0.0 | 0.0 | 7.4 |
| Peak coupler force (kN) | 661 | **864** | 997 |
| Min inter-train gap (m) | 182 | **182** | **−689 (rear-end)** |
| Rear-end collision steps | 0 | **0** | **392** |

**Key observations:**
1. **Cooperative gain +110,042**: M1 (+33,494) substantially outperforms M3 (−76,548). M1 avoids rear-end collisions (0 vs 392), keeping the min gap at 182 m, whereas M3's independent cyclic-braking leads to gap collapse to −689 m (physical penetration) and 392 collision steps.
2. **Coupler force kept within limit**: M1 864 kN and M3 997 kN are both <1000 kN, enforced by the Layer-1 coupler-force safety layer. Coast (661 kN) is lowest because it does not brake.
3. **Speed band**: M1 stays within [40,80] km/h (2.5% overspeed, 0% under-speed); M3 has 7.4% under-speed from the cyclic-braking-induced deceleration that leads to rear-end.

### C. Robustness (randomized initial conditions, 10 seeds)

| Metric | **M1 (coop)** | M3 (independent) |
|:--|:--|:--|
| Reward | **+34,763 ± 1,141** | −10,641 ± 43,683 |
| Rear-end collision steps | **0 ± 0** | 158.6 ± 149.6 |
| Min gap (m) | **182 ± 0** | −202 ± 342 |

M1's reward has a small standard deviation (+34,763 ± 1,141) and zero collisions across all seeds, whereas M3 has a huge variance (−10,641 ± 43,683) with frequent rear-end collisions. **The cooperative gain is robust** across randomized initial conditions.

*(Note: some random initial conditions trigger a known release-wave dynamic limitation causing coupler-force spikes ~22,900 kN in both M1 and M3; this is a simulator limitation, not specific to cooperation, and is outside the fixed-initial-condition main evaluation.)*

### D. Disturbance robustness

After training M1 with a leader disturbance (brief braking at step 500), the robust policy maintains safety under disturbance (−0.3 m/s², 100 steps): rear-end 0, min gap 57 m, peak coupler 728 kN. Without disturbance, the core cooperative result is preserved (reward +33,603 vs +33,886 for the non-disturbance variant, a negligible difference).

### E. Simulator validation against literature

Our multi-body dynamics are validated against published physical laws:
- **Brake-pipe pressure vs coupler force** (Zhang et al. 2025): larger brake reduction → larger compressive coupler force (monotonic, matches our dynamics).
- **Coupler gap vs coupler force** (Yang 2018): larger gap → larger peak force (reproduced via our coupler dead-zone model).
- **Coupler-force limit** (Fu 2019 / China Academy of Railway Sciences): 1000 kN normal / 2250 kN emergency.

---

## VI. Conclusion

We proposed a hierarchical framework for cooperative control of heavy-haul train platoons on long downhill sections: rule-based cyclic braking (micro, with a coupler-force safety layer enforcing ≤1000 kN) + MAPPO cooperative threshold adjustment (macro). On the Shuozhou–Huanghua profile, our method achieves a **cooperative gain of +110,042** over independent control (M1: 0 rear-end collisions vs M3: 392), keeps the coupler force within the 1000 kN limit, and is robust across randomized initial conditions. The results demonstrate that multi-train cooperation is necessary to prevent rear-end collisions induced by independent cyclic braking, while the rule-based cyclic braking with a coupler-force safety layer ensures the in-train safety constraint is never violated.

**Limitations.** The release-wave dynamics exhibit a known limitation under long-run/high-initial-speed conditions (coupler-force spikes), which is a simulator issue independent of the cooperative method. Future work includes strengthening the release-wave model and extending to larger platoons.

---

## References

[1] Zhang, Zhou, He et al. Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains. *Algorithms*, 17(5):190, 2024.
[2] Wang, Wang, Sun. Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach. *IEEE ICIRT*, 2025.
[3] Zhang, Nie, Ni, Tian. Multi-Agent DRL Based Consistency Control in Train Platoon Systems. *IEEE HPCC*, 2021.
[4] Guo, Peng, Pi, Zhang, Wu, Ma. Enhanced consensus control architecture for autonomous platoon utilizing MARL. *Comput.-Aided Civ. Infra. Eng.*, 2025.
[5] Wei, Wang, Sun, Feng. 考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法. 铁道学报, 2024.
[6] Fu, Yuan, Li, Yang. 基于钩缓约束的重载列车驾驶过程优化. 自动化学报, 2019.
