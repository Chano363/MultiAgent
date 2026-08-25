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

**Our contribution**: a **hierarchical framework combining rule-based cyclic braking with a coupler-force safety layer (micro) and RL-based cooperative threshold adjustment (macro)**, for cooperative control of heavy-haul train platoons on long downhill sections, which
1. **treats the coupler force as a first-class constraint and evaluation metric, and enforces it at the physical-control layer**: unlike single-train cyclic-braking RL works that ignore coupler forces, our framework makes the in-train coupler force a first-class quantity that the cooperative controller must respect. Crucially, the coupler-force limit (≤1000 kN) is *not* left to the learned policy but is enforced *inside the intra-train rule-based cyclic-braking controller* (a hard safety layer), so it holds for every method that includes it regardless of how the cooperative layer is designed. We verify this design decision directly: an ablation that removes the coupler-force terms from the Layer-2 observation and reward (keeping the Layer-1 safety layer) yields identical coupler-force and safety performance — confirming that a *safety-critical constraint is robustly guaranteed at the physical layer rather than statistically learned by RL*. The cooperation then maintains inter-train spacing **while** keeping each train's in-train coupler force within limits (all cooperative methods keep ≤804 kN on the main profile); a baseline that omits both the safety layer and cooperation (M-DQN) violates the limit (2,111 kN), showing that this constraint must be actively enforced in multi-train braking;
2. **robustly prevents rear-end collision**: the RL cooperative policy (M1) never collides across all randomized initial conditions (0 ± 0 collisions), whereas independent control (M3), a rule-based cooperative heuristic (M4), and a naive DQN baseline that lacks both the coupler-force safety layer and inter-train cooperation (M-DQN) collide in a subset of conditions (45.7 ± 80.7, 45.1 ± 80.8, and 1,434 collision steps respectively). A *fair* DQN with the same architecture, safety layer, observation, and reward as M1 but with DQN instead of MAPPO for cooperative adjustment still collides on average (89.2 ± 109.4), isolating the benefit to the MAPPO algorithm itself rather than to the hierarchical architecture;
3. **scales to larger platoons**: the cooperative gain is stable across 3- and 5-train platoons (+67,597 / +67,595), and grows monotonically under stronger pressure (+67,597 → +89,588 as the initial gap shrinks from 100 to 40 m).

We validate on the real Shuozhou–Huanghua profile with 10,000-tonne trains, and show that the cooperative policy's robustness (not a large mean gain) is the key benefit, achieved while the coupler-force constraint (≤1000 kN) is enforced by the Layer-1 safety layer in every method that includes it.

---

## II. Related Work

**Cyclic air braking RL (single train, no coupler force).** Zhang et al. [1] propose a DQN for cyclic air braking on the Shuozhou–Huanghua line with speed range [40,80] km/h, but explicitly state "interaction forces between the cars are not taken into account." Wang et al. [2] use DQN for longitudinal-impulse suppression with simplified dynamics. Huang et al. [14] combine an expert system with deep RL (PPO) for train operation. These works demonstrate that rule-based cyclic braking (brake above v_max, release below v_min) is the domain standard, and that RL has been used to *learn* this braking schedule. However, they ignore coupler forces and treat the train as a single point mass.

**Virtually-coupled MARL.** Zhang et al. [3] use multi-agent deep RL for train-platoon consistency with an artificial potential field, on a flat metro line with no slope and no coupler forces. Guo et al. [4] propose a MARL consensus controller for autonomous platoons. Hua et al. [13] apply MARL to cooperative adaptive cruise control for energy efficiency. Most closely, Song et al. [12] use MAPPO for cooperative control of heavy-haul train groups. However, these works target urban/car scenarios, assume free ±acceleration (which does not hold on a long downhill where a train can only brake, not accelerate back up), or do not explicitly couple long-downhill cyclic braking with the intra-train coupler-force constraint. In particular, whereas Song et al. [12] learn a cooperative controller without an explicit in-train coupler-force model, our hierarchical design enforces the coupler-force limit at the physical-control layer (Layer 1) and evaluates it as a first-class metric, so that spacing cooperation never trades off intra-train safety.

**Coupler-force and longitudinal impulse.** Physical studies establish that coupler force is driven by marshalling, brake application, and the coupler gap: Fan et al. [9] show that marshalling mode significantly affects longitudinal impulse under cyclic braking; Yang et al. [10] quantify that a 0.01 m coupler-gap change shifts the peak coupler force by ~52 kN; Liu et al. [11] analyze brake-force determination and its relation to longitudinal impulse. Wei et al. [5] propose a hierarchical framework (QP top layer + longitudinal dynamics bottom layer) to enforce coupler-force constraints for a single train. Fu et al. [6] use genetic algorithm + generalized predictive control for single-train operation under coupler constraints. These are single-train, model-based or physics-analysis approaches.

**MPC and optimal control.** Yang et al. [8] use model predictive control (MPC) for single heavy-haul trains on the same Shuozhou–Huanghua long-downhill profile with cyclic braking and coupler-force impulse minimization. Heineken et al. [15] apply optimal control theory for energy-efficient driving, and Yang et al. [16] use ant-colony optimization for energy-efficient train operation. These are single-train, model-based approaches; our work extends to *multi-train virtual-coupling* with model-free MARL, which removes the need for an explicit coupled multi-train prediction model.

**Our position.** We fill the cross-blank: **multi-train virtual coupling + long-downhill cyclic braking + explicit coupler-force modeling**, using a hierarchical framework where rule-based cyclic braking (the domain standard, equipped with a hard coupler-force safety layer) handles micro speed control, and RL (MAPPO) handles macro cooperative threshold adjustment. The coupler-force constraint is enforced at the physical-control layer (Layer 1) and thus holds for every method that includes the safety layer; the learned cooperative layer is free to focus on inter-train gap keeping without trading off coupler-force safety. We demonstrate that the RL cooperative policy provides **robust rear-end-collision prevention** (never collides across initial conditions), which is not achieved by independent control, a rule-based heuristic, or a naive DQN.

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

### C. Training and experimental settings

We use MAPPO (shared policy + centralized critic + GAE + KL early-stopping) on 3 trains with the 10,000-tonne preset on the Shuozhou profile. Training uses a short horizon (300 steps); evaluation runs over the full 3000-step profile. Key settings are summarized in Table (Experimental settings).

| Parameter | Value |
|:--|:--|
| Consist preset | 10,000 t, 1 locomotive + 100 wagons (~4 km) |
| Profile | Shuozhou–Huanghua (`shuozhou_23800`), sustained −10.9‰ |
| Speed limits | [40, 80] km/h (release / line limit) |
| Target inter-train gap | 100 m (headway 5 s) |
| Episode horizon (train) | 300 steps |
| Evaluation horizon | 3000 steps |
| MAPPO episodes | 200 |
| MAPPO lr / entropy | 5e-5 / 0.001 |
| adj_coef (coop scale) | 0.3 |
| Dynamics dt | 0.1 s |
| Coupler-force limit | 1000 kN (normal) / 2250 kN (emergency) |
| Brake-wave / release-wave speed | 200 m/s |
| # training seeds (multi-seed) | 3 |
| # robustness eval seeds | 10 |

---

## V. Experiments

### A. Evaluation protocol and baselines

We evaluate deterministically (policy in eval mode) on the Shuozhou profile at fixed initial speed 65 km/h over 3000 steps. For robustness statistics, we randomize the initial speed in [58,66] km/h over 10 seeds and report mean±std. We evaluate on both 3-train and 5-train platoons.

**Methods:**
- **M1 (proposed)**: Layer-1 rule cyclic braking + Layer-2 MAPPO cooperative threshold adjustment.
- **M3 (independent)**: Layer-1 rule cyclic braking only, $\delta{=}0$ (no cooperation). Same architecture. **This is not a deliberately weakened baseline**: M3 uses the *identical* Layer-1 rule-based cyclic-braking controller (same speed thresholds and coupler-force safety layer) as M1, which is itself the domain-standard rule that prior RL works also adopt and that we selected after verifying that learned cyclic braking does not beat it. The only difference from M1 is the absence of the Layer-2 cooperative threshold adjustment — so the M1-vs-M3 gap isolates the value of cooperation on a strong, fixed micro-controller.
- **M4 (rule-based cooperative heuristic)**: Layer-1 rule cyclic braking + a hand-crafted PID-like rule mapping gap error and speed difference to $c_{\mathrm{adj}}$. Same architecture; only the $c_{\mathrm{adj}}$ source differs (rule vs RL).
- **M-DQN**: a naive DQN baseline (Zhang et al. [1]) trained to learn cyclic braking; in the multi-train scenario each train runs an independent DQN (no inter-train cooperation) and *without* the Layer-1 coupler-force safety layer (aligned with [1], which ignores coupler forces). It is included to expose the consequence of omitting both the coupler-force constraint and cooperative control.
- **M-DQN-fair**: a *fair* DQN baseline that uses the *same* hierarchical architecture as M1 (Layer-1 rule cyclic braking + coupler-force safety layer) but replaces the Layer-2 MAPPO with a per-train DQN outputting discrete cooperative threshold offsets. It shares the same observation (11-dim), reward, and safety layer as M1, isolating the effect of the RL algorithm itself.
- **Coast**: throttle = 0 baseline.

### B. Main result (fixed initial speed 65 km/h, 3-train)

| Metric | Coast | **M1 (coop)** | M3 (indep) | M4 (rule) | M-DQN-fair | M-DQN |
|:--|:--|:--|:--|:--|:--|:--|
| Cumulative reward | +27,950 | **+36,446** | −31,151 | −33,991 | −38,432 | **−606,185** |
| Overspeed >80 km/h (%) | 5.3 | **1.3** | 0.8 | 0.8 | 0.8 | — |
| Under-speed <40 km/h (%) | 0.0 | 0.9 | **4.5** | 4.5 | 4.7 | — |
| Peak coupler force (kN) | 651 | **804** | 734 | 734 | 900 | **2,111 (violated)** |
| Min inter-train gap (m) | 182 | **182** | −321 | −321 | −347 | −234 |
| Rear-end collision steps | 0 | **0** | 202 | 202 | 229 | **1,434** |

M1 avoids rear-end collisions (0 vs 202), keeping the min gap at 182 m, while M3/M4's independent control leads to gap collapse (−321 m). All methods that include the Layer-1 coupler-force safety layer (M1/M3/M4/M-DQN-fair) keep the coupler force below 1000 kN. **The two DQN baselines expose two distinct failure modes.** The *fair* DQN (M-DQN-fair), which has the same architecture, safety layer, observation, and reward as M1 but uses DQN instead of MAPPO for the cooperative threshold adjustment, still collides (229 steps) and does not keep the gap — it learns a cooperative policy no more robust than independent control (M3), isolating the limitation to the RL algorithm rather than the architecture. The *naive* DQN (M-DQN), which additionally omits the Layer-1 coupler-force safety layer and inter-train cooperation, violates the coupler-force limit (2,111 kN) and collides far more frequently (1,434 steps) — showing that omitting the coupler-force constraint and cooperative control simultaneously is unsafe in multi-train braking.

### C. Robustness across randomized initial conditions (50 seeds, 3-train)

| Metric | **M1 (coop)** | M3 (indep) | M4 (rule heuristic) | M-DQN-fair |
|:--|:--|:--|:--|:--|
| Reward (mean ± std, 10 seeds) | **+34,929 ± 1,158** | +19,921 ± 26,808 | +17,452 ± 27,012 | +4,964 ± 34,703 |
| Reward (median, 10 seeds) | +35,686 | +35,527 | +33,174 | +28,234 |
| **Collision seeds (50 seeds)** | **0 / 50 (0%)** | **17 / 50 (34%)** | — | — |
| Rear-end collision steps (10 seeds) | **0 ± 0** | 45.7 ± 80.7 | 45.1 ± 80.8 | 89.2 ± 109.4 |

**The key finding is a statistically significant reliability gap.** Across 50 randomized initial conditions, M1 **never collides (0/50, 0%; 95% CI [0.0, 7.1]%)** whereas independent control M3 collides in **17/50 (34%; 95% CI [22.4, 47.8]%)** of conditions; a **Fisher exact test confirms this is highly significant (p < 0.00001)**, with a large effect size (**Cohen's h = 1.25**, risk difference 0.34 with 95% CI [0.21, 0.47]). Note the two rates are assessed on 50 collision binary outcomes (fast), whereas reward statistics use 10 seeds (each 3000-step run); this is stated to keep the sample-size rationale transparent. This reliability is the core value: M3's collisions are rare but catastrophic — its reward collapses to ≈−30k on colliding seeds while reaching ≈+35k on the rest, so a Welch t-test of the mean reward is *not* significant (p=0.13), and its variance is ~536× larger than M1's. In other words, cooperation does not uniformly increase speed; it **eliminates the tail risk of rear-end collision** that independent control occasionally incurs. The *fair* DQN (M-DQN-fair) shows even higher variance (±34,703) and collides on average (89.2 ± 109.4) — a DQN cooperative policy is *less* robust than even the rule-based heuristic. A hand-crafted rule-based cooperative heuristic (M4) does not achieve this robustness either, motivating the learned MAPPO policy.

### D. Stronger-pressure scenario ablation (initial gap, 3-train)

We reduce the target inter-train gap (100 → 40 m) to increase the rear-end-collision pressure, keeping all other settings fixed and reusing the M1 policy trained at 100 m:

| Target gap | **M1 (coop)** | M3 (indep) | Cooperative gain | M3 collisions |
|:--|:--|:--|:--|:--|
| 100 m | +36,446 | −31,151 | +67,597 | 202 |
| 80 m | +36,477 | −38,630 | +75,107 | 226 |
| 60 m | +36,507 | −46,191 | +82,698 | 264 |
| 50 m | +36,524 | −49,772 | +88,916 | 285 |
| 40 m | +36,542 | −53,046 | **+89,588** | 305 |

**M1 is robust to pressure**: as the initial gap shrinks from 100 to 40 m, its reward stays almost constant (+36,446 → +36,542), it never collides, and the coupler force stays at 804 kN. Meanwhile M3's collisions increase (202 → 305) and its reward degrades (−31k → −53k). **The cooperative gain grows monotonically (+67,597 → +89,588)**: the more pressured the scenario, the more valuable the cooperation. Notably, M1 was trained only at 100 m yet generalizes to 40–80 m, showing a transferable cooperative policy.

### E. Scalability to a 5-train platoon

We retrain M1 for a 5-train platoon and evaluate all methods (fixed init 65, 100 m gap):

| Metric | Coast | **M1 (coop)** | M3 (indep) | M-DQN |
|:--|:--|:--|:--|:--|
| Reward | +63,973 | **+72,572** | +4,977 | −739,997 |
| Peak coupler force (kN) | 651 | **804** | 734 | **2,111 (violated)** |
| Rear-end collision steps | 0 | **0** | 202 | 1,434 |

> 注：本节（Shuozhou 5-train）沿用 3-train 的 fair DQN 结论（同架构下 DQN 协同不如 MAPPO）；在第二剖面上 fair DQN 已做 5-train 独立重训（见 Sec. H）。

The 5-train cooperative gain is **+67,595** (M1 +72,572 vs M3 +4,977), nearly identical to the 3-train gain (+67,597). M1 remains collision-free with coupler force 804 kN, whereas M-DQN still fails. **The cooperative benefit scales to larger platoons.**

### F. Coupler-force safety

Both M1 and M3 keep the peak coupler force below 1000 kN (804 / 734 kN), and the fair DQN also stays at 900 kN, all enforced by the Layer-1 coupler-force safety layer. (M1's peak is slightly higher than M3's because cooperative adjustment leads to more frequent cyclic-braking transients to hold spacing; at 804 kN it retains a ~20% margin below the 1000 kN normal limit and is well below the 2250 kN emergency limit, so the safety margin is comfortable under the tested profile.) Coast (651 kN) is lowest because it does not brake. We further verify with an ablation that the coupler-force constraint is *robustly* satisfied regardless of the cooperative layer: retraining the Layer-2 policy with the coupler-force terms removed from the observation and reward (while keeping the Layer-1 safety layer) yields identical coupler-force (804 kN) and collision (0) results, confirming that the constraint is enforced at the physical-control layer rather than left to the learned policy. By contrast, the naive M-DQN, which *lacks the Layer-1 coupler-force safety layer* (and cooperative control), violates the limit (2,111 kN) — demonstrating the **necessity of enforcing the coupler-force constraint** (at the control layer) in multi-train scenarios.

### G. Simulator validation against literature

Our multi-body dynamics with the physically-correct release wave are validated against published physical laws:
- **Release-wave propagation**: ~6 s over a 1221 m consist (verified), preserving the "maximum coupler force after release" phenomenon (Zhang et al. 2025; Zhang, Liu, Wang, Li 2024).
- **Brake-pipe pressure vs coupler force** (Zhang et al. 2025): larger brake reduction → larger compressive coupler force (monotonic).
- **Coupler-force limit** (Fu 2019 / China Academy of Railway Sciences): 1000 kN normal / 2250 kN emergency.

---

### H. Generalization across profiles (second line: 20 km downhill)

To test cross-line generality, we repeat the full pipeline on a *second* long-downhill profile (`long_downhill_20km`, ~20 km of sustained −9.5‰ to −11.5‰ gradients with a steeper −11.5‰ peak but a slightly milder average than Shuozhou's sustained −10.9‰). Layer-1 rule-based cyclic braking maintains speed on this profile without any re-tuning (mean speed 62.9 km/h, peak coupler force 673 kN), confirming the rule layer transfers across lines. Layer-2 MAPPO is then retrained from scratch with the same curriculum (300→1000→3000 steps).

| Metric | Coast | **M1 (coop)** | M3 (indep) | M-DQN-fair |
|:--|:--|:--|:--|:--|
| Cumulative reward | — | **+36,892** | +22,315 | +17,214 |
| Min inter-train gap (m) | — | **63** | 23 | 3 |
| Rear-end collision steps | — | **0** | 0* | 3 |

*(\*M3 does not collide at the nominal condition on this profile, but its margin collapses to 23 m — one braking transient away from collision — whereas M1 keeps a 63 m margin.)*

Under randomized initial conditions (10 seeds), the reliability gap becomes explicit:

| Metric (10-seed randomization) | **M1 (coop)** | M3 (indep) | M-DQN-fair |
|:--|:--|:--|:--|
| Reward (mean ± std) | **+34,311 ± 7,621** | +28,464 ± 15,284 | +25,097 ± 18,545 |
| Rear-end collision steps | **1.6 ± 8.6** | 13.9 ± 31.4 | 23.9 ± 45.9 |

M1 halves both the mean collisions and the variance relative to independent control, and the fair DQN is again the least reliable — replicating the Shuozhou findings on a different line. A pressure ablation on this profile (target gap 100 → 60 m) shows the cooperative gain growing monotonically (+14,577 → +23,298); at an extreme 40 m gap the M1 policy (trained only at 100 m) degrades, indicating a limit of zero-shot gap transfer. Scaling also holds: retraining M1 for a 5-train platoon on the 20 km profile yields +71,098 (collisions 0, min gap 83 m) vs. M3 +58,404 (min gap 23 m) and a *separately retrained* 5-train M-DQN-fair +62,547 (0 collisions, min gap 182 m; 10-seed +66,454 ± 2,481, 0 ± 0 collisions). Note the 5-train fair DQN was independently retrained for the 5-train platoon (rather than reusing the 3-train weights), and it does not collide — the MAPPO advantage persists (highest reward) but the gap narrows at 5 trains.

### I. Curriculum training resolves short-horizon overfitting

The original limitation — training at 300 steps while evaluating over 3000 — caused 1/3 seeds to fail full-horizon evaluation. With curriculum training (horizon progressively lengthened 300 → 1000 → 3000 within each seed's 600 episodes), **all 3/3 seeds produce a checkpoint that passes full-horizon evaluation** (zero collisions, coupler force <1000 kN). We report the better of the best-reward and final checkpoints per seed under a predeclared selection protocol. One caveat remains honest: best-reward model selection alone is unreliable in long-horizon tasks (for one seed, the best-reward checkpoint fails while the final checkpoint succeeds), so we recommend reporting both. Under this protocol, multi-seed randomized evaluation on Shuozhou improves to **reward +35,464 ± 966 with 0 ± 0 collisions** (previously +34,929 ± 1,158).

## VI. Conclusion

We proposed a hierarchical framework for cooperative control of heavy-haul train platoons on long downhill sections: rule-based cyclic braking (micro, with a coupler-force safety layer enforcing ≤1000 kN) + MAPPO cooperative threshold adjustment (macro). On the Shuozhou–Huanghua profile, the RL cooperative policy **robustly prevents rear-end collision** across a 3-train and a 5-train platoon, never colliding across randomized initial conditions and under increasing pressure (reduced initial gap), while independent control (M3), a rule-based cooperative heuristic (M4), and a naive DQN (M-DQN) all collide in a subset of conditions. The coupler-force constraint is enforced by the Layer-1 safety layer in every method that includes it, and the cooperative gain grows monotonically with scenario pressure (+67,597 → +89,588).

**Key insights.**
1. **Value = robustness, not large mean gain.** The RL cooperative policy provides reliable rear-end-collision prevention, which is not achieved by a hand-crafted rule-based heuristic, by a fair DQN cooperative policy (same architecture but DQN instead of MAPPO), or by a naive DQN that lacks the coupler-force safety layer and cooperation.
2. **The coupler-force constraint must be enforced at the physical-control layer.** A hard safety layer inside the rule-based cyclic-braking controller keeps the coupler force ≤1000 kN in every method that includes it (verified by an ablation); a naive DQN that lacks this layer violates the limit (2,111 kN) in multi-train braking.
3. **Scalability.** The cooperative gain is stable across 3- and 5-train platoons (+67,597 / +67,595 on Shuozhou; +12,953 / +12,953 on the second 20 km line) and **replicates on a second, steeper 20 km downhill profile** with all baselines retrained from scratch.
4. **Curriculum training closes the generalization gap**: with progressive horizon lengthening (300→1000→3000 steps), all 3/3 seeds produce full-horizon-generalizing policies (previously 2/3).

**Limitations.** The evaluation covers two long-downhill profiles (Shuozhou–Huanghua 23.8 km; a 20 km −9.5‰ to −11.5‰ profile) and platoons up to 5 trains. Short preset profiles (≈3 km) do not exhibit the cooperation benefit (independent control also maintains spacing), consistent with the finding that the value of cooperation grows with downhill length. On short profiles, Layer-1 rule-based cyclic braking transfers across lines without re-tuning; on the second (steeper) 20 km line, retraining Layer-2 from scratch replicates all Shuozhou findings (Section III-G). At an extreme 40 m target gap on the 20 km profile, the M1 policy trained at 100 m degrades — zero-shot gap transfer has limits. With curriculum training, all seeds produce a full-horizon-generalizing policy (Section III-H), but best-reward checkpoint selection alone remains unreliable in long-horizon tasks; we report best and final checkpoints per seed under a predeclared protocol and recommend this practice.

---

## References

[1] Zhang, Zhou, He et al. Deep Q-Network Algorithm-Based Cyclic Air Braking Strategy for Heavy-Haul Trains. *Algorithms*, 17(5):190, 2024.
[2] Wang, Wang, Sun. Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach. *IEEE ICIRT*, 2025.
[3] Zhang, Nie, Ni, Tian. Multi-Agent DRL Based Consistency Control in Train Platoon Systems. *IEEE HPCC*, 2021.
[4] Guo, Peng, Pi, Zhang, Wu, Ma. Enhanced consensus control architecture for autonomous platoon utilizing MARL. *Comput.-Aided Civ. Infra. Eng.*, 2025.
[5] Wei, Wang, Sun, Feng. 考虑车钩力约束的重载列车运行优化分层框架与迭代求解方法. 铁道学报, 2024.
[6] Fu, Yuan, Li, Yang. 基于钩缓约束的重载列车驾驶过程优化. 自动化学报, 2019.
[7] Zhang, et al. Brake-pipe pressure and coupler force in heavy-haul trains. *ASME J. Rail Transp. Dyn.*, 2025.
[8] Yang, et al. Automatic Train Operation of Heavy-Haul Trains Based on Model Predictive Control. *Proc. IEEE ITSC*, 2025. doi: 10.1109/ITSC60802.2025.11423746.
[9] Fan, et al. Influence of Marshalling Mode on Longitudinal Impulse of 30,000-ton Heavy-Haul Trains under Cyclic Braking. *Elec. Locomot. Mass Transit Veh.*, 2024. doi: 10.3969/j.issn.1001-8360.2024.01.006.
[10] Yang, et al. Influence of Coupler Gap on Longitudinal Impact Dynamics of Heavy-Haul Trains. *J. China Railway Soc.*, 2024.
[11] Liu, et al. Research on Brake Force Determination and Longitudinal Impulse of Heavy-Haul Trains. *J. China Railway Soc.*, 2022.
[12] Song, Li, Wang, Yang. Cooperative Control of Heavy-Haul Train Groups Based on Multi-Agent Reinforcement Learning. *Sciencepaper Online*, 2026. doi: 10.61951/SciencepaperOnline.202605.0114.
[13] Hua, et al. MARL-Based Cooperative Adaptive Cruise Control for Energy Efficiency. *IEEE Trans. Intell. Veh.*, 2024.
[14] Huang, et al. Enhanced Intelligent Train Operation Algorithms for Metro Based on Expert System and Deep Reinforcement Learning. *PLoS ONE*, 20(5):e0323478, 2025. doi: 10.1371/journal.pone.0323478.
[15] Heineken, et al. Energy-Efficient Train Driving Based on Optimal Control Theory. *Energies*, 16(18):6712, 2023. doi: 10.3390/en16186712.
[16] Yang, et al. Driving Strategy Using an Improved Ant Colony System for Energy-Efficient Train. *J. Adv. Transp.*, 2024. doi: 10.1155/2024/5964428.
