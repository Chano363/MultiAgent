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
| **Yu 2026** *Impact of recharge duration on the cyclic braking performance in a 20,000-ton heavy-haul train* | **循环制动 recharge 时长→制动距离/车钩力**（10.2‰ 制动距离增 6.981km，可直接对齐数据） | ✅ 已下载 | DOI: `10.1177/09544097261438870`<br>https://doi.org/10.1177/09544097261438870 |
| **He 2025** *Research on optimization and evaluation method of heavy-haul train cyclic braking manipulation* | **循环制动操纵优化**（车钩力误差 <64.6/129.2/193.8kN 概率68/95/99.7%；优化降车钩力 21-23.9%）（**开放获取**） | ✅ 已下载 | DOI: `10.1108/rs-11-2024-0048`<br>https://doi.org/10.1108/rs-11-2024-0048 |
| **Zhao 2026** *MPC with Electro-Pneumatic Coordination...on Long Steep Downhills* | **电空协调 MPC**（速度跟踪误差 2.67%、最大车钩力降 >8%） | ⚠️ 正式出版但需 IEEE 权限（document 号已确认，搜 IEEE 请用此链接） | IEEE: `https://ieeexplore.ieee.org/document/11559852/`<br>DOI: `10.1109/CCDC69976.2026.11559852` |
| **Lu 2025** *Cooperative NMPC for Multiple Locomotives...on Long Steep Downhill* | **多机车 NMPC 协同降车钩力**（对齐我们第2层"协同"） | ⚠️ 正式出版但需 IEEE 权限（document 号已确认） | IEEE: `https://ieeexplore.ieee.org/document/11216780/`<br>DOI: `10.1109/ICIRT66379.2025.11216780` |
| **Si 2025** *An Optimization Method of Heavy Haul Train Driving Strategy Based on Dueling DQN* | Dueling DQN 长大下坡（初始 50→平均 65.95 km/h） | ⚠️ 正式出版但需 IEEE 权限（document 号已确认） | IEEE: `https://ieeexplore.ieee.org/document/11216735/`<br>DOI: `10.1109/ICIRT66379.2025.11216735` |
| **Liu 2024** *Analysis of the influence of brake pipe pressure gradient on heavy haul combined train...*（VSD） | 朔黄线 20000吨，压梯度→制动力/车钩力关系 | ⚠️ 需 Taylor&Francis 权限（VSD 期刊，SSCI 收录） | DOI: `10.1080/00423114.2024.2409773`<br>https://doi.org/10.1080/00423114.2024.2409773 |
| **Chu 2025** *Parameters design for vertical section of a 30,000-ton heavy-haul railway alignment based on longitudinal dynamics* | 1+1+1/2+2/3+0 多编组纵向冲动对比（对齐多列群组） | ⚠️ 正式出版但需 IEEE 权限（document 号已确认） | IEEE: `https://ieeexplore.ieee.org/document/11311639/`<br>DOI: `10.1109/SmartIoT66867.2025.00039` |

### 知网中文文献（2026-08-16 检索补充，补充中文核心期刊来源）

| 文献 | 相关性 | 下载 | 链接 |
|:--|:--|:--|:--|
| **《编组方式对3万吨重载列车循环制动工况纵向冲动的影响》**（电力机车与城轨车辆 2024-04） | **3万吨循环制动纵向冲动，多编组对比**（对齐我们多列群组循环制动） | ⬜ | 万方：`https://d.wanfangdata.com.cn/periodical/dljcjs202404001` |
| **《重载组合列车纵向力优化的联合制动分析及研究》**（城市铁道研究 2023-02） | **制动不同步性→车钩力**（与我们"制动相位错开→车钩力放大"机制完全吻合） | ⬜ | 万方：`https://d.wanfangdata.com.cn/periodical/cstdxyxb202302032` |
| **《MT-2缓冲器循环制动车钩纵向力变化》**（北京工业大学学报） | **循环制动车钩力变化趋势**（可对齐车钩力时间曲线） | ⬜ | 北工大学报：`https://journal.bjut.edu.cn/bjgydxxb/cn/supplement/b082f16a-6f5f-497e-895d-513c902ad80e` |
| **《重载列车制动力判断标准及纵向冲动研究》**（维普） | **长大下坡道制动 + 纵向冲动**（对齐我们长大下坡场景） | ⬜ | 维普：`https://lib.cqvip.com/Qikan/Article/Detail?id=7108737226` |
| **《重载列车车钩缓冲装置纵向动力学精细化模型》**（中国铁道科学 2025-02，PDF 直链） | 车钩力精细化建模（对标我们车钩力模型） | ⬜ | 全文PDF：`https://cjournal.hep.com.cn/1001-4632/CN/PDF/10.3969/j.issn.1001-4632.2025.02.17` |
| **《2万吨重载列车牵引启动工况的纵向冲动分析》**（力学学报，开放） | 2万吨牵引启动车钩力 | ⬜ | 力学学报：`https://pubs.cstam.org.cn/article/doi/10.6052/1672-6553-2024-046` |
| **《基于纵向力优化的重载组合列车循环制动过程异步协同控制方法及系统》**（专利 CN202411969020） | **循环制动异步协同控制**（与我们第2层多列协同直接相关） | ⬜ | 专利全文：`https://www.xjishu.com/zhuanli/29/202411969020.html` |
| **《重载列车纵向动力学建模研究》**（博士论文，掌桥） | 车钩力/钩缓/空气制动建模（对标动力学模型） | ⬜ | 掌桥：`https://www.zhangqiaokeyan.com/academic-degree-domestic_mphd_thesis/02031787279.html` |
| **《朔黄铁路2万t重载组合列车纵向车钩力分析及应用研究》**（朔黄线实测） | 朔黄线 2万吨车钩力实测（可直接对齐） | ⬜ | 知网（百度文库转载：`https://wenku.baidu.com/view/767ac61128160b4e767f5acfa1c7aa00b52a9dd3.html`） |
| **《货车连挂方式对万吨重载列车循环制动过程纵向冲动影响分析》** | 万吨列车循环制动纵向冲动 | ⬜ | 百度文库：`https://wenku.baidu.com/view/d6f207b2834d2b160b4e767f5acfa1c7ab008299.html` |

**下载后要研读/确认的问题**（供人工参考）：
1. Li 2024 的 CBF 是否只处理"间距/速度约束"？如何处理"空气制动离散档位一经发出就持续传播"这个状态性+时滞系统？（决定 CBF 能否落地解决车钩力问题）
2. Wang 2025 如何处理长大下坡循环制动的车钩力？其空气制动等效模型能否迁移到本项目？
3. Zhao 2025 的"HOCBF 盾修正 RL 动作"架构，与项目"自动控制 = RL 控制器本身"定位是否冲突？
4. **He 2025 / Yu 2026**：其车钩力误差分布（64.6kN 68%）和制动距离趋势能否用于标定我们仿真器的车钩力/制动距离输出？
5. **Zhao 2026**：速度跟踪误差 2.67%、车钩力降 >8%，能否作为我们 MARL 性能的对照基准？

---

## 已归档（完成/关闭）

| # | 状态 | 任务 | 结论 / 说明 |
|:--|:--|:--|:--|
| （空） | | | |

---

## 备注

- **任何 git 提交/删除命令**均需人工确认（项目规则）

