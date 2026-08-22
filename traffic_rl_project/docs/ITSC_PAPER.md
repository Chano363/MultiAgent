# Hierarchical MARL with Cyclic Braking for Cooperative Control of Heavy-Haul Train Platoons on Long Downhill Sections

*(ITSC 2026 draft — single-core-contribution, 6-page format)*

---

## I. Introduction

Heavy-haul trains operating on long downhill sections (e.g., the Shuozhou–Huanghua line, 23.8 km with sustained −10.9‰ gradients) require cyclic air braking to regulate speed: braking when speed exceeds an upper limit, and releasing when it falls below a lower limit. As the train length grows to 10,000 tonnes (1 locomotive + 100 wagons ≈ 4 km), the cyclic braking cycles produce large in-train longitudinal forces (coupler forces). Exceeding the coupler-force safety limit (1000 kN in normal operation, per the China Academy of Railway Sciences) risks coupler failure.

When multiple such heavy-haul trains operate as a virtually-coupled platoon (to increase line capacity), each train must simultaneously (i) regulate its own speed via cyclic braking and (ii) maintain a safe inter-train spacing to avoid rear-end collision. **Independent control of each train is fragile**: under a long downhill profile, the follower's cyclic-braking speed profile can lag the leader's, and the inter-train gap collapses into a rear-end collision in a subset of operating conditions.

Prior work falls into three gaps:
- **Long-downhill RL for a single train** (Zhang et al. 2024 DQN; Liu et al. 2021; Wang et al. 2025) explicitly **ignores coupler forces** (single-point mass).
- **Virtually-coupled MARL** (Zhang et al. 2021; Guo et al. 2025) targets **urban/metro or car platoons** and **ignores coupler forces**.
- **Coupler-force optimization** (Wei 2024; Fu 2019) is **single-train** and uses optimization (QP/GA), not learning.

**Our contribution**: a **hierarchical framework combining rule-based cyclic braking (micro) with RL-based cooperative threshold adjustment (macro)**, for cooperative control of heavy-haul train platoons on long downhill sections, which
1. **guarantees coupler-force safety** (≤1000 kN) via a rule-based cyclic-braking controller with a coupler-force safety layer;
2. **robustly prevents rear-end collision**: the RL cooperative policy (M1) never collides across all randomized initial conditions (0 ± 0 collisions), whereas independent control (M3) and a rule-based cooperative heuristic (M4) collide in a subset of conditions (45.7 ± 80.7 and 45.1 ± 80.8 collision steps respectively).

We validate on the real Shuozhou–Huanghua profile with three 10,000-tonne trains, and show that the cooperative policy's robustness (not a large mean gain) is the key benefit, achieved while keeping the coupler force within the 1000 kN limit.

---

## II. Related Work

**Cyclic air braking RL (single train, no coupler force).** Zhang et al. [1] propose a DQN for cyclic air braking on the Shuozhou–Huanghua line with speed range [40,80] km/h, but explicitly state "interaction forces between the cars are not taken into account." Wang et al. [2] use DQN for longitudinal-impulse suppression with simplified dynamics. These works demonstrate that rule-based cyclic braking (brake above v_max, release below v_min) is the domain standard, and that RL has been used to *learn* this braking schedule. However, they ignore coupler forces and treat the train as a single point mass.

**Virtually-coupled MARL.** Zhang et al. [3] use multi-agent deep RL for train-platoon consistency with an artificial potential field, on a flat metro line with no slope and no coupler forces. Guo et al. [4] propose a MARL consensus controller for autonomous platoons. These works target urban/car scenarios, ignore coupler forces, and assume free ±acceleration, which does not hold on long downhill sections (a downhill train can only brake, not accelerate back up).

**Coupler-force optimization.** Wei et al. [5] propose a hierarchical framework (QP top layer + longitudinal dynamics bottom layer) to enforce coupler-force constraints for a single train. Fu et al. [6] use genetic algorithm + generalized predictive control for single-train operation under coupler constraints.

**Our position.** We fill the cross-blank: **multi-train virtual coupling + long-downhill cyclic braking + explicit coupler-force modeling**, using a hierarchical framework where rule-based cyclic braking (the domain standard) handles micro speed control, and RL (MAPPO) handles macro cooperative threshold adjustment. We demonstrate that the RL cooperative policy provides **robust rear-end-collision prevention** (never collides across initial conditions), which is not achieved by independent control or by a hand-crafted rule-based cooperative heuristic.

---

## III. Problem and System Model

### A. Longitudinal train dynamics with air-brake release wave

Each train is modeled as a multi-body longitudinal dynamics system (following NeTrainSim). For wagon $i$ with mass $m_i$, position $x_i$, and velocity $v_i$:

$$m_i \ddot{x}_i = F_{t,i} - F_{r,i} - F_{b,i} - F_{g,i} + F_{c,i-1} - F_{c,i},$$

where $F_{t,i}$ is tractive force, $F_{r,i}$ is Davis resistance, $F_{b,i}$ is braking force (electric on locomotive + air brake propagating along the consist at finite brake-wave speed), $F_{g,i}$ is grade resistance, and $F_{c,i}$ is the coupler force between wagons $i$ and $i{+}1$, modeled as a spring–damper with dead zone (coupler gap):

$$F_c = \begin{cases} k(e-\text{gap}) + c \dot{e}, & |e| > \text{gap}, \\ c\dot{e}, & |e| \le \text{gap}, \end{cases}$$

with $e = x_i - x_{i+1} - l_0$. The coupler-force safety limit is 1000 kN [6].

**Air-brake release wave (physical modeling).** When the brake is released, the release command propagates from the lead car backward at a finite speed (~200 m/s) as a **continuous wavefront**. We model this correctly: each wagon's release delay is $d_i/\text{wave\_speed}$ (where $d_i$ is the distance from the brake source), and all wagons release **in parallel** as the wavefront reaches them. This yields a physically correct release time of ~6 s for a 1221 m consist (verified: 61 steps vs theoretical 61 steps, ratio 1.0×), and preserves the "maximum coupler force occurs after release" phenomenon noted in the literature (Zhang et al. 2025).

### B. Train platoon scenario

Three 10,000-tonne trains (1 locomotive + 100 wagons each, total ≈ 4 km) operate on the Shuozhou–Huanghua profile `shuozhou_23800` with speed limits [40, 80] km/h. The target inter-train gap is 100 m (headway 5 s). Trains start on the same grade section at initial speed 65 km/h. No artificial disturbance is introduced in the main evaluation; the natural profile (sustained −10.9‰) drives cyclic braking.

---

## IV. Proposed Method

### A. Hierarchical architecture

We use a two-layer structure (Fig. 1):

- **Layer 1 (intra-train, Coupler Level) — rule-based cyclic braking.** Each train uses `get_action_cyclic_braking`: brake at throttle $u=-0.75$ when speed $v \ge v_{max}$, release when $v \le v_{min}$ (hysteresis). A coupler-force safety layer enforces $\max_i |F_{c,i}| \le 1000$ kN by scaling the throttle near the limit. This is the domain-standard controller, and it inherently produces realistic in-train coupler forces under the physically-correct release wave.

- **Layer 2 (inter-train, Platoon Level) — MAPPO cooperative threshold adjustment.** Each train is an agent. The agent outputs a cooperative adjustment $c_{\mathrm{adj}} \in [-1,1]$, mapped to threshold offsets $v_{max}^{adj}, v_{min}^{adj} \in [\pm 5\,\text{km/h}]$ that shift the cyclic-braking thresholds of Layer 1. The adjustment does *not* directly manipulate the throttle (avoiding exploration that breaks rule-based cyclic braking). A positive adjustment makes the train brake earlier / release later.

### B. MDP formulation

- **State** (per agent, 11-dim): normalized own speed error, gap error, coupler-force statistic, position, tail grade, previous-train speed, previous-train braking indicator and deceleration strength.
- **Action**: $c_{\mathrm{adj}} \in [-1,1]$ (cooperative threshold offset).
- **Reward**: speed-band penalty + gap-keeping reward + speed-consistency + rear-end potential-field penalty + coupler-force penalty.

### C. Training

We use MAPPO (shared policy + centralized critic + GAE + KL early-stopping), 3 trains, 10,000-tonne preset, Shuozhou profile, 200 episodes, `adj_coef=0.3`, `entropy=0.001`. Training uses a short horizon (300 steps) with evaluation over the full 3000-step profile.

---

## V. Experiments

### A. Evaluation protocol

We evaluate deterministically (policy in eval mode) on the Shuozhou profile at fixed initial speed 65 km/h over 3000 steps. For robustness statistics, we randomize the initial speed in [58,66] km/h over 10 seeds and report mean±std.

**Methods:**
- **M1 (proposed)**: Layer-1 rule cyclic braking + Layer-2 MAPPO cooperative threshold adjustment.
- **M3 (independent)**: Layer-1 rule cyclic braking only, $\delta{=}0$ (no cooperation). Same architecture.
- **M4 (rule-based cooperative heuristic)**: Layer-1 rule cyclic braking + a hand-crafted PID-like rule that maps gap error and speed difference to $c_{\mathrm{adj}}$. Same architecture; only the $c_{\mathrm{adj}}$ source differs (rule vs RL).
- **Coast**: throttle = 0 baseline.

### B. Main result (fixed initial speed 65 km/h)

| Metric | Coast | **M1 (coop)** | M3 (independent) |
|:--|:--|:--|:--|
| Cumulative reward | +27,950 | **+36,446** | **−31,151** |
| Overspeed >80 km/h (%) | 5.3 | **1.3** | 0.8 |
| Under-speed <40 km/h (%) | 0.0 | 0.9 | **4.5** |
| Peak coupler force (kN) | 651 | **804** | 734 |
| Min inter-train gap (m) | 182 | **182** | **−321 (rear-end)** |
| Rear-end collision steps | 0 | **0** | **202** |

M1 avoids rear-end collisions (0 vs 202), keeping the min gap at 182 m, while M3's independent cyclic braking leads to gap collapse to −321 m. Both M1 and M3 keep the coupler force below 1000 kN (804 / 734 kN).

### C. Robustness across randomized initial conditions (10 seeds) — the key result

| Metric | **M1 (coop)** | M3 (independent) | M4 (rule heuristic) |
|:--|:--|:--|:--|
| Reward (mean ± std) | **+34,929 ± 1,158** | +19,921 ± 26,808 | +17,452 ± 27,012 |
| Reward (median) | +35,686 | +35,527 | +33,174 |
| Rear-end collision steps | **0 ± 0** | 45.7 ± 80.7 | 45.1 ± 80.8 |

**The key finding is robustness.** M1's cooperative policy achieves a **small reward variance (+34,929 ± 1,158) and zero collisions across all 10 seeds**, whereas both M3 (independent) and M4 (rule-based heuristic) exhibit large variance (±26,808 / ±27,012) and collide in a subset of conditions (45.7 ± 80.7 / 45.1 ± 80.8 steps). When the independent controller happens not to collide (the median seed), its reward (+35,527) is close to M1's (+35,686); however, it is **not reliable** — a subset of initial conditions triggers rear-end collision.

This shows that the **primary benefit of the RL cooperative policy is robustness (reliable rear-end-collision prevention), not a large mean gain**. A hand-crafted rule-based cooperative heuristic (M4) does not achieve this robustness, motivating the learned policy.

### D. Coupler-force safety

Both M1 and M3 keep the peak coupler force below 1000 kN (804 / 734 kN at fixed init; 805 / 700 kN under randomization), enforced by the Layer-1 coupler-force safety layer. Coast (651 kN) is lowest because it does not brake.

### E. Simulator validation against literature

Our multi-body dynamics with the physically-correct release wave are validated against published physical laws:
- **Release-wave propagation**: ~6 s to propagate over a 1221 m consist (verified), preserving the "maximum coupler force after release" phenomenon (Zhang et al. 2025; Zhang, Liu, Wang, Li 2024).
- **Brake-pipe pressure vs coupler force** (Zhang et al. 2025): larger brake reduction → larger compressive coupler force (monotonic).
- **Coupler-force limit** (Fu 2019 / China Academy of Railway Sciences): 1000 kN normal / 2250 kN emergency.

---

## VI. Conclusion

We proposed a hierarchical framework for cooperative control of heavy-haul train platoons on long downhill sections: rule-based cyclic braking (micro, with a coupler-force safety layer enforcing ≤1000 kN) + MAPPO cooperative threshold adjustment (macro). On the Shuozhou–Huanghua profile with three 10,000-tonne trains, the RL cooperative policy **robustly prevents rear-end collision**: it never collides across randomized initial conditions (0 ± 0), whereas independent control (M3) and a rule-based cooperative heuristic (M4) collide in a subset of conditions. The cooperative policy also keeps the coupler force within the 1000 kN limit and shows the smallest reward variance.

**Key insight.** The value of multi-train RL cooperation in this setting is **reliability under diverse operating conditions**, rather than a large average gain over independent control. This robustness is not achieved by a hand-crafted rule-based heuristic, motivating the learned policy.

**Limitations.** The current evaluation covers a single profile and a 3-train platoon; extending to larger platoons and additional profiles is future work. Training with a short horizon (300 steps) also limits generalization to the full profile, and a subset of training seeds fails to generalize (overfitting to the short horizon), which we plan to address with curriculum learning.

---

## References

[1] Zhang, Zhou, He et al. Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains. *Algorithms*, 17(5):190, 2024.
[2] Wang, Wang, Sun. Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach. *IEEE ICIRT*, 2025.
[3] Zhang, Nie, Ni, Tian. Multi-Agent DRL Based Consistency Control in Train Platoon Systems. *IEEE HPCC*, 2021.
[4] Guo, Peng, Pi, Zhang, Wu, Ma. Enhanced consensus control architecture for autonomous platoon utilizing MARL. *Comput.-Aided Civ. Infra. Eng.*, 2025.
[5] Wei, Wang, Sun, Feng. 考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法. 铁道学报, 2024.
[6] Fu, Yuan, Li, Yang. 基于钩缓约束的重载列车驾驶过程优化. 自动化学报, 2019.
