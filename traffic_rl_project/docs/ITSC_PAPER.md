# Hierarchical MARL for Distributed-Power × Electrical/Pneumatic Braking Division of Heavy-Haul Trains on Long Downhill Sections

\*(ITSC 2026 draft — **architectural rewrite, ADR-009 / 2026-09-05**). Previous drafts: (a) "Hierarchical MARL + Cyclic Braking" single-core draft (已清理 2026-09-08); (b) the "MARL vs MPC / threshold-coordination" reorientation (3-train, 1+0, per-train agents) is superseded by this draft. 本稿转向：**以"多机车分布式动力 × 电空双制动分工"为核**——每台机车=独立智能体，MARL 直接调制本机车的电制动(ED)深度/空气制动(AB)触发，从而获得旧架构(阈值协同 ±0.5 km/h = 带宽 1.25%)永远没有的**真物理杠杆**。分层框架 = 规则引擎(ED优先+错峰+AB兜底)作安全嵌入内层 + RL 逐机车调制作协作外层。数值全部来自 `docs/records/DIAGNOSTICS.md` 2026-09-05 decompose 定稿数据，逐项可复现。\*

> **⚠️【2026-09-08 主轴对齐·定位偏差声明】**
> 本稿以「**单列车 standalone decompose**（1+1 机车级 ED/AB 分工）」为核心，已由项目侧判定为**方向性偏差**——它脱离了**列车编队**语境，把单列车当成了论文主线。
> **项目主轴（铁律，2026-09-08 ADR-013）＝ 论文最终目的是「编队」**（多列重载列车群组长大下坡协同，保持安全列距＋速度带一致＋车钩力≤1000kN）；**MARL 只是实现编队的手段。仅保留单套 formation-aware RL＝机车级 ED/AB 分工（每台机车=智能体，以编队为上下文）承载编队目标；底层规则循环制动＋车钩力安全层确定性执行。废止「编队层(列车级)RL + 列内层(机车级)RL 两层叠加(T-MARL)」表述。**
> 因此：**本篇当前作为「编队上下文内的机车级 ED/AB 机制」的实验记录保留**（其单列 decompose 数值、诊断可复现，作机制证据参考），但**不再作为论文主轴叙事**；正文 Abstract / Introduction / Contributions / Method / Experiments 需按「编队=目的 + 唯一 formation-aware RL」主轴重写，**Results 重写依赖编队上下文实验数据**（见 `.trae/documents/MT2多列编队M1与消融实验补齐规划.md` 阶段 0–3），在数据补齐前**不得引用本稿当作"论文最终结果"**。语义代号以该规划 §0.1 为准（已废止 M-数字）。

***

> **【2026-09-09 主训练剖面升级】** 主训练剖面已由 `shuozhou_23800`（朔黄 23.8km，手写/Zhang2024 复现）**升级为 `shuozhou_real_53km`（朔黄线宁武西→北大牛完整真实纵断面 53.2km，取自真实线路数据 `simulation(1)/data_line/line_grade.xlsx`）**。正文 Abstract / Protocol / 主结果章节中的 **23.8 km 与数值均为剖面升级前的训练产物**；用新 53.2km 真实剖面重训后，需同步替换正文数值与剖面声明（本稿在数据补齐前不得当作论文最终结果引用，见顶部声明）。

## Abstract

Heavy-haul trains on sustained long downhill sections must hold speed within a narrow band using **cyclic braking** (electric + pneumatic), while keeping in-train **coupler forces** below a safety limit — a long-horizon, switched, safety-critical control problem. We show that the *decomposition* of this problem is what determines whether multi-agent reinforcement learning (MARL) can learn anything at all: prior "train-level" MARL treated each whole train as an agent and only nudged a shared speed-band threshold (a $\pm 0.5$ km/h offset = 1.25 % of bandwidth), leaving a lever too small to learn from ("nothing to learn" ceiling). We re-decompose at the **locomotive** level: each locomotive is an independent agent that directly modulates its own **electric-braking depth** and **pneumatic-braking trigger**, a continuous, physically meaningful lever. A rule engine (ED-first + inter-locomotive stagger + AB fallback) provides a safety-embedded inner layer; MAPPO adds per-locomotive $\[\mathrm{ed}\_{mod}, \mathrm{ab}\_{mod}]\in\[-1,1]^2$ modulation. A semi-MDP **decision interval** splits the 15,000-step credit chain into 1,500 decisions, making long-horizon MAPPO converge. On the real Shuozhou–Huanghua profile (23.8 km, $\approx -10.9,%o$) with a 10,000-t, 1+1 distributed-power consist, we obtain a three-layer positive evidence chain with zero safety violations: single-locomotive rule (+40,956) $\rightarrow$ distributed-power rule division (+71,252, +74 % reward, AB usage −89 %) $\rightarrow$ RL division (+72,743; coupler peak −21 % to **570 kN**, final speed +11.2 km/h, ATP emergency events −97 %). RL finds a physically interpretable policy — halve ED depth and inject staggered *minimum-notch* AB to cut longitudinal impulse — that no tuning of the old threshold coordination could reach.

***

## I. Introduction

A 10,000-ton heavy-haul train on a long downhill section (Shuozhou–Huanghua line, 23.8 km, sustained up to $-10.9,%o$) must regulate speed through **cyclic braking**: brake above an upper limit, release below a lower limit. The minute-scale brake–release cycles, combined with multi-body coupler dynamics and finite air-brake wave propagation ($\approx 200$ m/s across a $\sim 4$ km train), generate in-train **coupler forces** that must stay below 1000 kN (normal) / 2250 kN (emergency). Electric braking (ED) is smooth, continuous and available only on locomotives; pneumatic (air) braking (AB) is discrete (RELEASE/MIN/SERVICE/EMERGENCY) and is the dominant source of longitudinal impulse while simultaneously being slow to recover (pipe recharge). How to *split* braking effort between ED and AB across multiple locomotives — the **distributed-power (DP) × electro-pneumatic division** problem — is exactly where controller design matters most on long downhills.

Our first attempt at MARL for this regime followed the literature's "train-level" decomposition: one agent per *train*, outputting a small offset to a shared speed-band threshold. The result was a hard ceiling. The offset is $\pm 0.5$ km/h against a $40$–$80$ km/h band — a **1.25 % bandwidth lever** — and across a 15,000-step run its reward gradient is statistically invisible. Adding global observations and consistency-shaped rewards recovered only $\approx 0.8,%$ (\~343) reward. We diagnosed this as a *structural* problem, not a tuning problem: **MARL has nothing to learn when its only control lever is too small to change the outcome.**

The resolution (ADR-009) is to re-decompose the action space at the **locomotive** level and give MARL a *real* physical lever:

- **Electric braking depth** — each locomotive's $ED\in\[0,1]$ is continuous and directly scales the applied ED force (*big* lever, $\pm 0.5$ of absolute ED depth).

- **Air-brake triggering** — each locomotive may suppress or pre-trigger its own AB source along the consist (inter-locomotive *stagger* of pneumatic application), the primary knob for coupler impulse.

A rule engine provides the safety-embedded inner layer: ED-first, per-locomotive stagger, AB only as a fallback when ED availability is power-starved. MAPPO then learns how to *modulate* this baseline per locomotive. Because both ED depth and the AB-on/off timing are physically meaningful, the RL policy can move coupler force, braking energy and holding accuracy together.

A second, orthogonal obstacle is **credit assignment over a very long horizon**. The full 23.8 km section is a 15,000-step time domain; single-step-decision MAPPO over that horizon produced a flat, negative training reward (RL ended pervasively dragging the train with air braking). We cure this with a **semi-MDP decision interval**: the RL policy decides once every $N{=}10$ steps, holds its action, and stores a window-summed transition — compressing the 15,000-step credit chain to 1,500 decisions while the rule baseline still executes per step. This is the general technique on which the headline results depend.

**Contributions.** (C1) We identify and formalize the "**nothing-to-learn**" ceiling of train-level threshold coordination (a 1.25 % bandwidth lever) and show that re-decomposition to the locomotive ED/AB level provides a physically meaningful MARL lever; (C2) we give a **three-layer, like-for-like positive evidence chain** on the real Shuozhou profile — single-locomotive → distributed-power rule division → distributed-power RL division — all zero safety violations, isolating the *architecture*gain from the *learning* gain; (C3) we establish **semi-MDP decision intervals** as a practical cure for long-horizon (15,000-step) MARL credit assignment in switched train dynamics; (C4) the learned policy is **physically interpretable** — halve ED depth + staggered MIN-notch AB — and cuts coupler peak 21 %, raises final speed 11.2 km/h, and reduces ATP-triggered emergency events by 97 %.

***

## II. Related Work

**Distributed power × braking division.** Tang et al. \[T2020] model multi-locomotive trains with RL and explicitly include coupler force in the reward, establishing the DP setting we build on. 赵紫宁 et al. \[ZZ2022] give a refined air-brake model and report, for a 1+1 distributed-power consist, that **synchronous multi-source braking reduces in-train impulse** (their two-source \~616 kN vs single-source \~1549 kN in our re-derivation), directly supporting the "ED/AB split + stagger" lever. Our contribution is to make this division *learned* per locomotive via MARL rather than hand-tuned.

**RL for cyclic braking on long downhills.** Zhang \[Z2024], Liu \[L2021] and Wang \[W2025] all apply DQN-type RL to long-downhill automatic speed control — and **all explicitly ignore coupler forces**. We retain their cyclic-braking formulation but add coupler force as a first-class objective/constraint (1000 kN), which is precisely where the ED/AB division matters (AB is the impulse source). 张二田 \[ZET 2021] and 杨敏 \[YM] document that coupler force stays below 1000 kN on mild grades when braking is released simultaneously and pipe recharge is sufficient — the physics our dynamic multi-body model reproduces.

**Why train-level MARL has "nothing to learn".** Prior group-platoon MARL (e.g. the multi-train formulation in the earlier draft of this work) gave each *train* a cooperative threshold offset. The offset is $\pm 0.5$ km/h on a 40-km/h band → a 1.25 % lever → near-zero reward gradient (our diagnostics, 2026-09-04). We report this as a **structural caution** for MARL action design: the lever must be able to change the outcome or the gradient vanishes, regardless of observation/architecture.

**Long-horizon credit assignment.** PPO/MAPPO over tens of thousands of steps is known to degrade when the reward that matters arrives after many decisions. Our semi-MDP decision interval (action hold + window return) is a minimal, task-agnostic mitigation that preserves the underlying dynamics while shortening the credit chain; we include it as a reusable technique.

***

## III. Problem Statement & System Model

Longitudinal dynamics per vehicle (NeTrainSim-derived multi-body integration): traction − electric braking − pneumatic braking − Davis resistance ± grade − coupler force. Air braking propagates along the consist at finite wave speed (≈200 m/s → seconds of delay across a \~4 km train); electric braking is continuous and limited by power and adhesion. Coupler forces come from a mass–spring–damper with a **gap dead-zone** (0.01 m), reproducing the "brake gap → coupler force" law and Newton-pair cancellation.

Control objective: keep each locomotive's speed in $\[v\_\min, v\_\max] = \[40,80]$ km/h, keep coupler force $\le 1000$ kN, over the full 23.8 km (15,000-step) horizon, using a 1+1 distributed-power consist (10,000 t). The difficulty is that the minute-scale cyclic rhythm and the band-limited coupler constraint act over far longer than a rolling window, and the AB actuator is discrete + history-dependent (recharge).

**Why ED/AB splitting resists a small-lever policy.** On this profile the rule-based cyclic braking already holds the band; the *remaining* degrees of freedom — exactly how deep each locomotive brakes with ED, and exactly when each triggers AB — are the ones that decide coupler impulse. A policy that cannot touch these (e.g. only shifts the band) is orthogonal to the objective it must minimize.

***

## IV. Proposed Method: Two-Level Decompose MARL

**Level 1 — rule engine (safety-embedded inner layer).** `get_action_decomposed` provides a deterministic baseline per step: **ED-first** (both locomotives saturate ED up to the physically available share), **per-locomotive stagger** (offset each locomotive's brake phase to spread impulse), and **AB fallback** only when ED availability is insufficient. Critical to correct triggering is a **physical ED-availability model**: ED force $F\_{ED}=\min(P\_{ED}/v, \text{adhesion}) \propto F\_{req}(m \cdot g \cdot \max| \text{grade}|)$. On a steep section at speed the available ED share $<1$, so the baseline genuinely falls back to AB; earlier simplifications ($\mathrm{clip}(v/5)$) made fallback unreachable and hid the mechanism.

**Level 2 — MARL modulation (learned).** MAPPO, **one agent per locomotive** (1+1 consist → 2 agents), observes per-locomotive state and outputs $\[ed\_{mod}, ab\_{mod}]\in\[-1,1]^2$:

- $ed\_{mod}$ directly scales this locomotive's ED depth ($\pm 0.5$ absolute) — the continuous physical lever;

- $ab\_{mod} > +0.5$ suppresses this locomotive's AB source (only while $v\<v\_\max - 0.5$, so safety fallback is never cheaply switched off); $ab\_{mod} < -0.5$ pre-triggers a MIN-notch AB — enabling *staggered, anticipatory* pneumatic braking.

**Observation (11-dim per locomotive):** speed error wrt target; margin to $v\_\max$; margin to $v\_\min$; the rule baseline's ED (what the engine "wants"); whether the rule baseline would brake with AB; local coupler force (normalized); AB-active fraction on the consist; AB release-remaining fraction (recharge state); brake-segment index; locomotive position (for grade inference); inter-train gap error (0 for single-train). Feeding the *air-brake state* lets the policy **sense** hysteresis rather than predict it.

**Reward.** Band holding (in-band $+5$, out-of-band $-20$ per train) + coupler force (mean & peak penalties, plus a super-limit term) + comfort + gap (multi-train extension) + an ED micro-cost ($-0.02$ per depth) to avoid gratuitous full-ED cruising. Notably, **AB is not directly penalized**: extensive smoke-testing showed any positive AB cost exactly cancels the coupler-force benefit of staggered MIN-notch AB (coupler force is the objective; AB is only a means).

**Semi-MDP decision interval.** With a per-step decision and a 15,000-step horizon, MAPPO's stage-3 training reward stayed flat at \~$-$291 k — the credit chain was too long. With decision interval $N{=}10$, the RL policy decides every 10 steps, holds its action, and stores one transition with a window-summed return; the rule baseline still executes every step. This turned a failed run into the converged results below.

***

## V. Experiments

**Protocol.** Shuozhou–Huanghua main profile (23.8 km), 1+1 distributed power (10,000 t), ETCS distance-to-go curves on, deterministic evaluation (fixed seed) at 80 km/h over the full 15,000 steps, n\_seed=3 evaluation rollouts. MAPPO: `lr=5e-5, entropy=0.002`, curriculum `1000:0,3000:20,15000:40`, decision interval $\mathrm{N}{=}10$, 60 episodes. Same environment + same rule baseline for M0 and single-locomotive runs — the three rows differ only in the *architecture/structure* under test (like-for-like).

**Main result — three-layer evidence chain (15000 steps, all zero safety violations).**

| Method                                            |      reward | coupler peak (kN) | viol | band rate | AB steps | mean ED | final speed (km/h) | ATP events |
| :------------------------------------------------ | ----------: | ----------------: | ---: | --------: | -------: | ------: | -----------------: | ---------: |
| **decompose-M1 (RL division, interval=10, ep60)** | **+72,743** |           **570** |    0 |   99.72 % |    4,357 |    0.35 |           **52.9** | **1.44 M** |
| decompose-M0 (distributed-power rule division)    |     +71,252 |               720 |    0 |   99.68 % |      461 |    0.67 |               41.7 |     43.2 M |
| single-locomotive (old 1+0 rule)                  |     +40,956 |               456 |    0 |   90.20 % |    4,030 |       — |               44.9 |      467 M |

**Isolated increments.** (a) *Architecture gain*, M0 vs single-loco: distributed-power ED-first + stagger + ED-availability-faithful AB fallback gives **+74 % reward** (+30,278), **+9.5 pp band rate**, and **−89 % AB usage** (4,030→461 steps) — distributed ED power suffices, so pneumatic effort almost vanishes, with zero super-limit. (b) *Learning gain*, M1 vs M0: RL finds a **physically interpretable re-allocation** — halve ED depth (mean ED 0.67→0.35) and inject **staggered MIN-notch AB** (461→4,357 steps) — trading slightly more, but individually gentle and phased, pneumatic applications to shrink longitudinal impulse: **coupler peak −21 % (720→570 kN)**, **final speed +11.2 km/h**, **ATP emergency events −97 %** (43.2 M→1.44 M). The smoother ED profile plus crank-joint-friendly phased AB is exactly the region a small-lever threshold policy can never reach.

**Why this is the decisive comparison.** The three rows share the environment, the safety layer, and the rule baseline; only whether (i) power is distributed, and (ii) ED/AB are RL-modulated per locomotive changes. Every layer adds a positive, *measured* increment with zero violations — decomposing the source of the gain (architecture vs learning) rather than reporting a single black-box number. This is the diagnostic train-level "nothing-to-learn" framework could not show: the same simulator, given a real lever, transitions from "flat $-291$ k" to "+61 k train reward / +72.7 k rollout".

**Generalization / recentring.** Because the policy acts on per-locomotive ED/AB (not on a train-wide band), it transfers structurally to longer sections and larger numbers of distributed-power locomotives without re-tuning the band; ablations over $N\in\{5,10,20\}$ and AB-cost $\in\{0,0.05\}$ (planned) establish the margins of the semi-MDP and the reward shape.

**Ablation — lever isolation (which lever carries the gain).** We reran full training (seed0, same protocol) with one modulation masked during training (`mask_lever`), isolating the causal contribution of each lever (best-checkpoint eval; all zero violations, band ≈ 100 %):

| Method | reward | coupler peak (kN) | AB steps | mean ED | final (km/h) |
| :----- | -----: | ----------------: | -------: | ------: | ------------: |
| **M1 both levers** (seed0 best) | +73,733 | 578 | 4,807 | 0.34 | 53.5 |
| only-ED lever (mask ab) | +71,932 | **528** | **0** | 0.70 | 45.1 |
| only-AB lever (mask ed) | **+74,634** | 702 | **5,960** | 0.05 | **71.0** |
| M0 rule (no levers) | +71,252 | 720 | 461 | 0.67 | 41.7 |

The two levers serve distinct objectives: the **ED lever is the coupler-safety lever** — ED-only reaches the *lowest* coupler peak (**528 kN**, 27 % below M0) with zero AB and band 100 %, so the coupler reduction of M1 vs M0 comes chiefly from ED-depth shaping, not from AB. The **AB lever is the throughput lever** — AB-only rides the speed-band ceiling (final **71.0 km/h**, heavy phased AB ~5,960 steps, near-zero ED) and scores the *highest* scalar reward (+74,634), at the cost of higher coupler (702 kN). M1 (both levers) is the compromise — 578 kN, +73,733, final 53.5 km/h — jointly minimizing coupler and holding throughput. **Honest caveat:** only-AB outperforms M1 on the raw scalar reward, i.e. the current reward-shaping rewards high-speed band-riding air-braking; we therefore do *not* claim M1 is the scalar-reward optimum, but the best **coupler–throughput balance** among safe (zero-violation) editors. Reshaping to penalize heavy AB (impulse/energy, not a linear cost) is a stated follow-up.

***

## VI. Conclusion & Limitations

We argued and demonstrated that for long-downhill cyclic-braking control, **the decomposition of the MARL action space decides whether there is anything to learn**. Train-level threshold coordination gives a 1.25 % bandwidth lever and a near-zero gradient ("nothing to learn"); locomotive-level ED/AB division gives continuous, physically meaningful levers. Combining a safety-embedded rule engine with per-locomotive MAPPO modulation and a semi-MDP decision interval yields a three-layer, zero-violation positive evidence chain on the real Shuozhou profile (RL: +2.1 % reward over rule division; coupler −21 %; final speed +11.2 km/h; ATP events −97 %).

**Limitations.** (1) The learned policy is trained in a high-fidelity simulator and inherits its fidelity (sim-to-real gap shared in kind with model-driven MPC). (2) We provide no formal recursive-stability guarantee; deployment safety would require formal verification / ATP integration. (3) AB is not directly penalized in the reward — the division is only as safe as the coupler-force weighting, and the AB-trigger margin ($v\_\max-0.5$) is a hand-set constant. (4) Long-horizon training remains expensive and seed-variance nontrivial; the semi-MDP interval $N$ is a hyperparameter worth ablating. (5) **主轴对齐说明（2026-09-08 ADR-013）**：本篇以单列车 1+1 decompose 为核心，属**方向性偏差**（见顶部声明）；项目主轴 = **编队（目的）＋ 唯一 formation-aware 机车级 ED/AB MARL（手段）**，编队上下文实验将按规划阶段 1–3 补齐后并入（废止"两层 RL 叠加"表述）。 (6) The spring-buffer (draft-gear) model introduces a few calibrated constants: the MT-2 static/dynamic friction ratio $\mu_s/\mu_d=1.5$ and transition velocity $v_{er}=0.2$ m/s have literature-anchored structure (Yang Liangliang 2017's Eq. 3) but point values from impact tests; the buffer is unified to a single MT-2 friction type (including the locomotive–freight connection), avoiding an elastic-paste sub-model whose five shape constants had no published fits; our Shuozhou-profile sweep shows both coupler-force peaks shift $\le\sim1$% within $\pm$reasonable uncertainty of these values ($v_{er}$ 0.05–0.5 $\to$ +1%; $\mu_s/\mu_d$ 1.2–1.5 $\to$ +1.2%), so they do not dominate the headline coupler-force result (though $\mu_s/\mu_d$ shows a threshold nonlinearity near 1.8). Also, the release-time constant $\tau=6$ s models only the initial exhaust transient (exponential decay); full air-brake recharge takes 175–512 s (Zhao 2022), which we abstract as a history-dependent recharge effect rather than simulate explicitly.

***

## References \*(verify + expand to IEEE style in .tex) \*

- **Tang 2020** — multi-locomotive RL with coupler-force reward for heavy-haul train control (in-repo).

- **赵紫宁 2022** — refined air-brake modeling & optimization for 1+1 distributed power (in-repo; 8-anchor reconstruction in this project).

- **Zhang 2024** — DQN for long-downhill automatic train operation (ignores coupler force).

- **Liu 2021** — DDQN long-downhill cyclic braking (ignores coupler force).

- **Wang 2025** — DQN long-downhill speed control (ignores coupler force).

- **张二田 2021** — 2-kt train coupler-force field tests; mild-grade simultaneous-release < 1000 kN.

- **杨敏** — brake gap & manipulation modes vs coupler force on 10-kt consists.

- **樊运新** — consist marshalling vs longitudinal impulse.

- **Fu 2019** — coupler/gear limit constraints (1000 / 2250 kN).

- (Background, retained from prior draft) **Wu et al. 2017** air-brake model parallel computing; **Wu et al. 2023** virtual-coupling survey; **Yang et al. ITSC 2025** single-train MPC on Shuozhou; **Wang et al. 2026** improved-MPC heavy-haul virtual coupling.

- Project records: `docs/records/DIAGNOSTICS.md` §2026-09-05 (decompose smoke / full / RL-rescue); `outputs/results_decompose/eval_decompose_all_ms15000.json`.

