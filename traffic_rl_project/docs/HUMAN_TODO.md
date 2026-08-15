# 人工待办清单（Human TODO）

> 本文档专门记录**需要人工参与**的任务（AI 无法独立完成的部分，如论文下载、外部资源获取、方向决策、环境操作等）。
> - 已完成项用 ✅ 标记**保留不删除**（工作留痕）
> - 新任务**追加**到表格末尾
> - 需 AI 执行的任务见 `PROJECT_PIPELINE.md`（任务总览），不在此列

---

## 进行中

| # | 状态 | 任务 | 说明 / 来源 |
|:--|:--|:--|:--|
| H1 | 🔄 | **手动下载论文**（CBF 与车钩力方向） | 见下方"论文下载清单"，DOI/链接已给出，需人工浏览器下载 |

---

## 论文下载清单（H1）

> 出版社反爬，开放获取以外的论文需**浏览器手动下载**，放入 `docs/papers/`，命名 `作者+年份+主题.pdf`。

| 论文 | 主题 | 状态 | 下载链接 / DOI |
|:--|:--|:--|:--|
| **Li, Tong, Giua 2024** *Safe Optimal Train Formation Control in Virtual Coupling Using Control Barrier Functions* | **CBF/CLF + QP 列车编队安全控制**（论文目标方案理论基础） | ⬜ 未下载 | IEEE: `https://ieeexplore.ieee.org/document/10711420`<br>DOI: `10.1109/CASE59546.2024.10711420` |
| **Wang, Wang, Sun 2025** *Operation Optimization of Heavy Haul Train Considering Longitudinal Impulse Suppression: a DQN Approach* | 重载列车长大下坡循环制动 + 纵向冲动（DQN） | ⬜ 未下载 | IEEE: `https://ieeexplore.ieee.org/document/11216684`<br>DOI: `10.1109/ICIRT66379.2025.11216684` |
| **Zhao, Sun, Xu 等 2025** *Safe RL Control of High-Speed Maglev Train Levitation...* | **HOCBF 安全层修正 RL 动作**（架构可直接借鉴） | ⬜ 未下载 | IEEE: `https://ieeexplore.ieee.org/document/11308942`<br>DOI: `10.1109/CIYCEE67631.2025.11308942` |

**下载后要研读/确认的问题**（供人工参考）：
1. Li 2024 的 CBF 是否只处理"间距/速度约束"？如何处理"空气制动离散档位一经发出就持续传播"这个状态性+时滞系统？（决定 CBF 能否落地解决车钩力问题）
2. Wang 2025 如何处理长大下坡循环制动的车钩力？其空气制动等效模型能否迁移到本项目？
3. Zhao 2025 的"HOCBF 盾修正 RL 动作"架构，与项目"自动控制 = RL 控制器本身"定位是否冲突？

---

## 已归档（完成/关闭）

| # | 状态 | 任务 | 结论 / 说明 |
|:--|:--|:--|:--|
| （空） | | | |

---

## 备注

- **任何 git 提交/删除命令**均需人工确认（项目规则）

