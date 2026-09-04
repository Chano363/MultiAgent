# Learning-Based Multi-Agent Reinforcement Learning vs Model Predictive Control for Heavy-Haul Train Platoons on Long Downhill Sections

\*(ITSC 2026 draft — research reorientation. Previous "Hierarchical MARL + Cyclic Braking" single-core draft archived at `docs/archive/paper_v_cyclic_braking_2026-08-23/`. 本稿转向：以导师给出的 MPC 四大内在局限为主轴，用文献 + 本仓库实验论证"learning-based 分层 MARL（数据驱动，决策时无需显式环境动力学预测）在重载列车长大下坡循环制动群组场景下相对模型驱动 MPC 的结构性优势"——思路上的重大重构。) *

> 状态：骨架（Introduction / Related Work / Method / Comparison / Conclusion 已搭建），数值全部来自 `docs/records/DIAGNOSTICS.md` 2026-08-30/31 定稿数据，逐项可复现。待办：标题/署名、图表生成、Language polish。

***

## I. Introduction

Heavy-haul trains operating on long downhill sections (Shuozhou–Huanghua line, 23.8 km with sustained −10.9‰ gradient) must regulate speed through **cyclic air braking**: braking above an upper limit and releasing below a lower limit. The minute-scale "brake–release" cycles, combined with multi-body coupler dynamics, produce large in-train longitudinal (coupler) forces that must stay below the safety limit (1000 kN normal / 2250 kN emergency). When several such trains form a virtually-coupled platoon to raise line capacity, each unit must additionally keep a safe inter-train spacing while following the cyclic-braking rhythm. This couples **long-horizon, nonlinear, coupled, switched dynamics** (air-brake wave propagation, brake–release hysteresis, varying consist and grade) with a **safety-critical** spacing constraint.

**MPC is the incumbent, industrially applied method** for train operation and (more recently) virtual coupling: e.g., Yang et al. (ITSC 2025) use single-train MPC on the very same Shuozhou profile to minimize coupler impulse; Wang et al. (2026) apply Kalman-filtered MPC to cooperative heavy-haul virtual coupling; Song et al. (2026) derive a Tube-MPC for heavy-haul virtually-coupled train sets. It is therefore the natural baseline and the strongest reference point.

Yet we argue that MPC carries **four structural limitations** in precisely this regime, and that a *learning-based (data-driven), global-horizon* cooperative policy (multi-agent reinforcement learning, MARL) is the better fit. Throughout, "learning-based" is used in the RL sense: the policy is learned from interaction data and embeds **no explicit environment-dynamics predictor** in its per-step decision — unlike MPC, which re-solves with a model-based prediction each step. The four limitations (as framed by our advisor) are:

1. **Finite-horizon feasibility is fragile; terminal constraints are hard to design.** MPC solves a local receding-horizon optimization. For nonlinear coupled systems, a control-invariant *terminal set* must be imposed for recursive feasibility, but designing such a set is notoriously difficult (Derajić et al. 2025); when the horizon is too short to reach it, the QP/NLP becomes infeasible, and simply lengthening the horizon raises computation and (under non-convexity) degrades solver reliability (Surma & Jamshidnejad 2025). In our cyclic-braking platoon the relevant dynamics time-scale is *minutes*, far beyond a real-time-feasible horizon.
2. **Online solve cost scales with fidelity × horizon × platoon size; real-time is infeasible.** MPC must re-solve a (non)convex QP/NLP at every control step, embedding a high-fidelity prediction model of the multi-body air brake and coupler — a prediction model that itself runs slower than real time (a 150-wagon air-brake model is 6.7× slower than real time, needing eight cores to reach it, Wu et al. 2017). State estimation adds further burden: Kalman-filtered MPC maintains a 2nN-dimensional state with 8n³N³ matrix inversions per step (Wang et al. 2026), and NMPC's non-convexity makes online solving expensive enough to threaten real-time feasibility in safety-critical virtual coupling (Zhang et al. 2026). Our scaling study quantifies this (this work): per-step solve time grows \~184× from 17 ms (2 trains, 50-step horizon) to 3,169 ms (5 trains, 400 steps), while MARL inference stays constant at \~0.4 ms.
3. **It requires an extremely precise model.** SLSQP/MPC relies on an accurate forward model of coupler forces, brake-wave propagation and brake–release hysteresis; the multi-body coupler is exactly the part that is hardest to model precisely, and with model mismatch MPC has no buffer (our simplified MPC, no coupler model, overflowed the coupler limit).
4. **It does not generalize across trains and lines.** Each consist differs (mass, length, brake characteristics), and MPC must be re-tuned/re-identified per train and per section; it optimizes locally and does not transfer learned structure across operating conditions.

**Our thesis.** Learning-based (data-driven) hierarchical MARL is not a "less rigorous" alternative to MPC; it is structurally better suited here: it (i) learns a **global long-horizon** driving rhythm instead of a shrinking local window, (ii) **moves the optimization offline** — deployment is a single forward pass whose cost is essentially independent of platoon size (≈0.4 ms), (iii) **does not embed an explicit coupler/braking predictor in its per-step decision** (no online model-based prediction), whereas MPC must re-solve with a high-fidelity prediction model each step, and (iv) **generalizes** across randomized initial conditions, larger platoons, and unseen profiles.

We demonstrate this on the real Shuozhou profile with 10,000-tonne trains and a multi-train platoon. Under the *same* randomized-initialization protocol, our hierarchical MARL policy (M-MARL) holds spacing and coupler force and never collides (reward **+36,004**; 0 collisions), whereas a *fair* multi-train MPC with the full model, coupler constraint, and gap constraints **collapses**: speed stalls below the release limit for **71.6%** of run time, coupler force exceeds the limit (**1,178–1,431 kN**), and under randomized initial conditions the spacing goes negative (rear-end collision, 330 collision steps; reward **−258,831±116,023**). The collision pattern maps directly onto MPC's short-rolling-window blind spot: its \~3.2 s horizon cannot foresee the minute-level brake–release rhythm.

**Contributions.** (C1) We formalize the four structural limitations of MPC for long-downhill cyclic-braking platoon control and map each to a MARL advantage; (C2) we provide a controlled head-to-head — same environment, same safety layer, randomized protocol — showing MPC's receding-horizon blind spot empirically collapses the run while MARL transfers; (C3) we show MARL's generalization (50 random initial conditions, 5-train platoons, a second 20-km profile) that model-driven MPC cannot offer for free.

***

## II. Related Work

**MPC is the industrial incumbent for train control and virtual coupling.** Yang et al. (ITSC 2025) — single-train multi-body MPC with cyclic air braking and coupler-impulse minimization on the Shuozhou profile; Wang et al. (2026) — improved MPC + Kalman filtering for heavy-haul virtual coupling (inter-train gap error ≤20 m); Song et al. (2026) — Tube-MPC for heavy-haul virtually-coupled train sets, explicitly constructing *terminal controllers and terminal constraint sets* to certify stability; Lu et al. (ICIRT 2025) — NMPC for multiple locomotives of a single train. These confirm MPC is both the practical standard and the object of active research for this regime.

**MPC's known theoretical fragility (Lim 1).** Stability/recursive feasibility of MPC rests on a control-invariant terminal set; designing one is "particularly difficult, especially in dynamic environments" (Derajić et al., 2025), and short horizons can make the NLP infeasible while longer horizons raise cost and, under non-convexity, hurt solver reliability (Surma & Jamshidnejad, 2025). Aggregate Line results confirm: virtual-coupling surveys classify MPC's main limitation as its finite-horizon/optimization burden relative to real-time coupling requirements (Wu et al., 2023).

**Online-solve cost is MPC's acknowledged bottleneck (Lim 2), and the field patches it rather than fixing it intrinsically.** The air-brake/coupler prediction model MPC must embed is itself slower than real time (a 150-wagon air-brake simulation runs 6.7× slower than real time and needs eight cores to reach it, Wu et al., 2017); Kalman-filtered MPC for virtual coupling maintains a 2nN-dimensional state with 8n³N³ matrix inversions per step (Wang et al., 2026); and NMPC's non-convex optimization is costly enough to challenge real-time feasibility in safety-critical virtual coupling, motivating Koopman/learning-based linearizations to accelerate it (Zhang et al., 2026). Surveys likewise list "high computational cost" among MPC's obvious disadvantages (Wu et al., 2023). The remedy is always a bolt-on (Koopman lifting, LMPC, robust/learning variants — e.g., Vaquero-Serrano et al., 2025) rather than the plain method being intrinsically real-time.

**Learning-based / RL turn (our approach).** Roadmaps for RL-based virtual coupling (Basile et al., 2022) and coordinated-operation MARL (Liu et al., 2025) show growing evidence that learning-based methods handle the constraint-satisfaction complexity that model-driven local optimization finds hard. Our hierarchical design (rule-based cyclic braking as a safety-embedded inner/control layer + MARL for the cooperative outer layer) is the learning-based alternative that directly targets the four MPC limitations.

***

## III. Problem Statement & System Model  \*(skeleton — reused from archived draft, to be re-condensed) \*

Heavy-haul platoon of $N$ trains, each a multi-body unit (1 loco + \~100 wagons ≈ 10,000 t) moving on a long downhill grade profile. Longitudinal dynamics per vehicle: traction − braking − Davis resistance ± grade − coupler forces; air braking propagates along the consist at finite wave speed (≈200 m/s → seconds of delay across a \~4 km train). Coupler forces from mass-spring-damper + gap dead-zone model. Control objective: keep each train speed in $\[v\_{\min}, v\_{\max}]$, keep inter-train gap $\geq$ safety threshold, keep coupler force $\leq 1000$ kN, over a crossed-minutes horizon. Linear MPC with a short horizon cannot see this horizon and cannot model the switched coupler/braking force exactly — the crux.

**Why air braking resists online optimization.** Air braking — the primary actuator on long downhill sections — carries four physical properties that jointly make it ill-suited to per-step continuous optimization (and to MPC's online prediction model):
1. **Discrete notches** (RELEASE/MIN/SERVICE/EMERGENCY) — not a continuous variable; exact optimization is mixed-integer.
2. **Charge/release hysteresis** — after a release the brake pipe must recharge before the next application (recharge time scales with the pressure reduction and train length, minutes on heavy-haul consists); the attainable brake force depends on the *history* of prior releases, coupling decisions across minutes.
3. **Finite brake-wave propagation** (≈200 m/s → seconds of delay across a ~4 km train) — head and tail brake asynchronously, the dominant source of in-train longitudinal (coupler) impulses; release waves add a second, slower transient.
4. **Segment-dependent degradation** — repeated cyclic applications reduce the realized braking effort (segment-to-segment C_β degradation ~30%, from in-service identification); within a segment the force evolves over time (temperature-dependent model, left unmodeled here for lack of measured temperature data).

Consequence: a model that predicts these faithfully is itself expensive to evaluate online (a 150-wagon air-brake model runs 6.7× slower than real time, Wu et al. 2017), and its switched/discrete structure makes the embedded optimization hard — feeding Lim 2 and Lim 3. Our design therefore does not ask the learned policy to "optimize" air braking: the discrete notch is triggered by the rule-based cyclic-braking inner layer, and the policy only decides the ED/AB split (electric braking carries the smoothly controllable share; air braking is reserved for when electric braking is insufficient), using observable air-brake state (release remaining, segment index) as input — *sensing* the hysteresis rather than predicting it. This is the model-side counterpart of Lim 2/Lim 3 and the design basis for the ED/AB split.

***

## IV. Proposed Method \*(skeleton — hierarchical MARL, condensed from archived draft) \*

We retain the hierarchical structure but re-frame it explicitly as the *learning-based* answer to the four MPC limitations:

- **Inner/control layer (rule-based, safety-embedded):** rule-based cyclic braking (brake > v\_high, release < v\_low) + a hard coupler-force/ATP safety layer. The rule layer is method-agnostic and applied identically to MPC and MARL (like-for-like comparison); it is not what replaces online optimization — the learned outer policy is (→ Lim 2), and the design spares MARL from needing an explicit coupler predictor (→ Lim 3).

- **Outer/cooperative layer (learned):** MAPPO, one agent per train, observes its own state plus the leader's, outputs a cooperative threshold offset — i.e., learns the *global, long-horizon* cooperative rhythm that MPC's local window cannot represent (→ Lim 1). Policy generalizes across initial conditions/platoons/sections (→ Lim 4).

Design mapping table (to be embedded):

| MPC limitation                                | MPC failure mode (evidence)                                                                                                                          | MARL advantage (in this work)                                                     |
| :-------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------- |
| 1. Finite horizon / terminal feasibility      | \~3.2 s window; can't see minute-level cyclic rhythm → 70.8% of run below release floor, gap −9 m, 330 collision steps (APC diagnostics, 2026-08-30) | learns global long-horizon rhythm; holds gap & coupler force                      |
| 2. Online solve cost (fidelity×horizon×scale) | per-step solve 17→3,169 ms as N=2→5 & horizon 50→400 steps (\~184×, this work); 56.5 ms/step in evaluation                                           | offline training + one forward pass; inference ≈0.4 ms, constant in scale         |
| 3. Requires precise model                     | simplified MPC (no coupler model) → coupler force 1,431 kN overflow                                                                                  | learning-based; no online dynamics predictor in per-step decisions                                 |
| 4. Weak generalization                        | per-train/per-line re-identification                                                                                                                 | generalizes across 50 random initial conditions, 5 platoons, second 20-km profile |

***

## V. Experiments \*(comparison — MPC vs MARL, data from 2026-08-30/31 thawed diagnostics) \*

**Protocol.** Same environment (Shuozhou main profile, 3000 steps), same SafetyLayer, randomized initial speeds 55–75 km/h, 5 seeds. Fair MPC = full multi-body model + coupler ≤1000 kN + gap constraint, block-horizon $B=4\times8\approx3.2$ s, SLSQP.

**Main comparison (fixed init, deterministic):**

| Method                    |    reward   | 低40% (stalled) | coupler peak (kN) | gap min (m) | collision steps |
| :------------------------ | :---------: | :------------: | :---------------: | :---------: | :-------------: |
| **M-MARL (ours, 5-seed)** | **+36,004** |       1.3      |      **659**      |    **92**   |      **0**      |
| No-C (independent, δ=0)   |    +9,791   |       \~1      |        543        |      —      |        69       |
| M-DQN-fair                |   −15,215   |       1.8      |        463        |     −116    |       157       |
| M-MPC-fair                |   −115,622  |    **71.6**    | **1178 (≥limit)** |     105     |        0        |
| Coast (reference)         |   +33,871   |        0       |        667        |     183     |        0        |

**MPC under randomized initial conditions (5 seeds):** reward **−258,831±116,023**, coupler **1,431±207 kN** (>limit), gap min **−9±94 m**, **329.6±384.2 collision steps**, only 4.2 cyclic-braking cycles, 56.5 ms/step solver time (vs μs–ms for the learned policy).

**Mapping to the four MPC limitations (the paper's core evidence):**

- Lim 1 — receding-horizon blinkering: the \~3.2 s window stalls the train (71.6–70.8% below release floor) and collapses spacing (−9 m, 330 collisions). MARL's global policy holds 0 collisions.

- Lim 2 — online-solve cost: per-step solve time scales \~184× (17→3,169 ms) as platoon size and horizon grow, and is 56.5 ms/step in the 3.2 s-horizon evaluation (this work); MARL inference stays at \~0.4 ms. High-fidelity air-brake prediction is itself slower than real time (Wu et al., 2017).

- Lim 3 — model precision: the fair MPC *has* the full coupler model yet still overflows the coupler limit (1,178–1,431 kN); the simplified MPC (no coupler model) overflows worse. MARL, needing no coupler predictor, stays at 659 kN.

- Lim 4 — generalization: M-MARL maintains +36,120 / 0 collisions on an out-of-domain 20 km profile and scales to 5-train platoons; MPC is a per-run local optimum with no transfer.

**Pressure / scenario ablations (supporting):** cooperative benefit grows monotonically as the target gap shrinks (+26,213 → +47,502), consistent with the spacing-limited regime being exactly where the learning-based cooperative layer matters.

***

## VI. Conclusion \*(skeleton) \*

We re-frame the heavy-haul cyclic-braking platoon problem as one where MPC's four structural limitations — finite-horizon/terminal feasibility, online-solve cost that scales with fidelity/horizon/scale, sensitivity to model error, and weak generalization — are not tuning issues but intrinsic properties, and where learning-based (data-driven) hierarchical MARL addresses each. Controlled experiments on the real Shuozhou profile show the fair MPC collapses under the minute-scale cyclic-braking rhythm (stall, coupler-force overflow, rear-end collision) while MARL holds spacing and coupler force and generalizes. **Limitations:** MARL does not provide the formal recursive-stability guarantee that tube/MPC methods can certify; for the nominal short-horizon case MPC remains competitive; deployment safety would require formal verification/ATP integration, and the RL statistical outlier (1/3 seeds of an earlier model) must be reported honestly. The learned policy is trained in a model-based simulator, so its performance inherits simulator fidelity (a sim-to-real gap shared by model-driven MPC); our claims are scoped to the simulated regime.

***

## References \*(verified; expand to IEEE style in .tex) \*

- Yang et al., "Automatic Train Operation of Heavy-Haul Trains Based on Model Predictive Control," IEEE ITSC 2025 (in-repo; single-train MPC, Shuozhou, coupler impulse).

- H. Wang et al., "Research on Cooperative Operation Control Methods ... Based on Improved MPC," Railway Transport and Economy 48(2):88–98, 2026. doi:10.16668/j.cnki.issn.1003-1421.20250530003.

- Z. Song et al., "Cooperative control methods for virtually coupled heavy-haul trains based on traditional pneumatic braking (Tube-MPC)," Journal of Beijing Jiaotong University 50(2):116–131, 2026. doi:10.11860/j.issn.1673-0291.20250156.

- M. A. Vaquero-Serrano et al., "A learning model predictive control for virtual coupling in intelligent train control systems," Computer-Aided Civil and Infrastructure Engineering 40(31):6279–6304, 2025. doi:10.1111/mice.70155.

- F. Surma & A. Jamshidnejad, "Recursive Feasibility without Terminal Constraints via Parent-Child MPC Architecture," Systems & Control Letters, 2025 (arXiv:2507.10166).

- B. Derajić et al., "Residual Neural Terminal Constraint for MPC-based Collision Avoidance in Dynamic Environments," 2025 (arXiv:2508.03428).

- Lu et al., ICIRT 2025, multi-locomotive NMPC (in-repo).

- Q. Wu et al., "Railway Virtual Coupling: A Survey of Emerging Control Techniques," IEEE Trans. Intelligent Vehicles, 2023. doi:10.1109/TIV.2023.3260851.

- Q. Wu, C. Cole, M. Spiryagin, and Y. Wang, "Railway air brake model and parallel computing scheme," J. Computational and Nonlinear Dynamics 12(5):051012, 2017. doi:10.1115/1.4036421.

- Y. Zhang, L. Calogero, S. Li, A. Rizzo, and A. V. Proskurnikov, "Koopman-based NMPC for Virtually Coupled Train Control System," arXiv:2606.11858, 2026.

- G. Basile et al., "Roadmap and challenges for reinforcement learning control in railway virtual coupling," Discover Artificial Intelligence 2:27, 2022. doi:10.1007/s44163-022-00042-4.

- H. Liu et al., "Coordinated Operation Strategy Design for VCTS: A Multiagent Reinforcement Learning Approach," IEEE ITS Magazine 17(4), 2025. doi:10.1109/MITS.2024.3449803.

- Project records: `docs/records/DIAGNOSTICS.md` §2026-08-30/31 (MPC pressure & master comparison tables); `outputs/phys2_full_comparison_20260830.txt`, `outputs/mpc_pressure_5seed_20260830.txt`.

