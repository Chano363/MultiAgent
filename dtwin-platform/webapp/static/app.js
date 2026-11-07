/* 数字孪生平台前端 —— 单页视图 + 原生 fetch + canvas 绘图（无第三方依赖） */
(function () {
  "use strict";

  const VIEW_META = {
    algorithms: { title: "算法管理", sub: "已注册算法、参数与发送入口" },
    runtime: { title: "仿真运行", sub: "执行器状态、任务队列与曲线" },
    records: { title: "数据记录", sub: "仿真 CSV、指标 JSON 与摘要" },
    analysis: { title: "分析服务", sub: "已完成任务的指标对比" },
  };

  const state = {
    view: "home",
    overview: null,
    runs: [],
    selectedId: null,
    selectedJob: null,
    records: [],
    recordFilter: "all",
    analysis: null,
    pollTimer: null,
  };

  // ---------------------------------------------------------------- 工具
  const el = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function fmt(v, d) {
    if (v === null || v === undefined || Number.isNaN(v)) return "-";
    if (typeof v === "number") return v.toFixed(d === undefined ? 1 : d);
    return String(v);
  }

  async function api(path, options) {
    const res = await fetch(path, Object.assign({ headers: { "Content-Type": "application/json" } }, options || {}));
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || ("请求失败 " + res.status));
    return data;
  }

  let toastTimer = null;
  function toast(msg, isError) {
    const box = el("toast");
    box.textContent = msg;
    box.classList.toggle("error", !!isError);
    box.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => box.classList.remove("show"), 3200);
  }

  // ---------------------------------------------------------------- 框架
  function renderNav() {
    const domains = (state.overview ? state.overview.domains : Object.keys(VIEW_META).map((k) => ({ key: k, label: VIEW_META[k].title })))
      .filter((d) => VIEW_META[d.key]);
    el("nav").innerHTML = domains.map((d, i) => `
      <button data-action="view" data-view="${d.key}" class="${state.view === d.key ? "active" : ""}">
        <i class="dot"></i><span>${esc(d.label)}</span><span class="idx">0${i + 1}</span>
      </button>`).join("");
  }

  function setView(view) {
    state.view = view;
    const meta = VIEW_META[view];
    const isHome = view === "home";
    el("topbar").classList.toggle("home", isHome);
    if (meta) {
      el("view-title").textContent = meta.title;
      el("view-sub").textContent = meta.sub;
    }
    ["home", "algorithms", "runtime", "records", "analysis"].forEach((v) => {
      el("view-" + v).classList.toggle("active", v === view);
    });
    renderNav();

    if (view === "records") loadRecords();
    if (view === "analysis") loadAnalysis();
    if (view === "runtime") { refreshRuns(); startPolling(); } else { stopPolling(); }
  }

  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(refreshRuns, 1500);
  }
  function stopPolling() {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }

  // ---------------------------------------------------------------- 首页 / 框架数据
  async function loadOverview() {
    const data = await api("/api/overview");
    state.overview = data;
    renderNav();
    renderEnvBadge();
    el("foot-algos").textContent = data.algorithm_count;
    el("foot-backends").textContent = data.backends.filter((b) => b.available).length + " / " + data.backends.length;
    el("foot-runs").textContent = data.stats.total;
  }

  function renderEnvBadge() {
    if (!state.overview) return;
    const live = state.overview.backends.filter((b) => b.available && b.kind === "live");
    const badge = el("env-badge");
    if (live.length) {
      badge.className = "badge badge-ok";
      badge.textContent = "联合仿真环境已接入";
    } else {
      badge.className = "badge badge-warn";
      badge.textContent = "联合仿真未接入 · 离线回放";
    }
  }

  // ---------------------------------------------------------------- 算法管理
  function renderAlgorithms() {
    const algos = state.overview ? state.overview.algorithms : [];
    const backends = state.overview ? state.overview.backends : [];
    const canSend = backends.some((b) => b.available);

    const html = `
      <div class="card card-pad" style="margin-bottom:18px">
        <div class="section-title"><span>算法插件库（${algos.length}）</span><span class="line"></span></div>
        <p class="note">
          每个算法只实现 <span class="mono">act(obs) → action</span>，读不到仿真器。
          空气制动、列间安全包络、电-空仲裁在算法输出之后由保护层钳制，换算法时这些约束仍然生效。
        </p>
      </div>
      <div class="alg-grid">
        ${algos.map((a) => `
          <div class="card alg-card">
            <div class="alg-head">
              <div><h3>${esc(a.display_name)}</h3><div class="alg-key">${esc(a.key)}</div></div>
              <span class="chip">${esc(a.category)}</span>
            </div>
            <p class="alg-desc">${esc(a.description)}</p>
            <div class="param-list">
              ${Object.keys(a.params || {}).map((k) => `<span class="param">${esc(k)}: ${esc(a.params[k])}</span>`).join("")}
            </div>
            <div class="alg-foot">
              <button class="btn btn-primary" data-action="send" data-algo="${esc(a.key)}" ${canSend ? "" : "disabled"}>发送到仿真运行</button>
              <span class="state">${canSend ? "选择执行器后开始运行" : "无可用执行器"}</span>
            </div>
          </div>`).join("")}
      </div>`;
    el("view-algorithms").innerHTML = html;
  }

  function openSendModal(algorithmKey) {
    if (!state.overview) return;
    const algo = state.overview.algorithms.find((a) => a.key === algorithmKey);
    if (!algo) return;
    const backends = state.overview.backends;
    const defSteps = 1200;
    const modal = el("modal");
    modal.innerHTML = `
      <div class="modal-card">
        <h3>发送算法到仿真运行</h3>
        <p class="m-sub">算法：<b>${esc(algo.display_name)}</b> <span class="mono">(${esc(algo.key)})</span></p>
        <div class="field">
          <label>目标执行器</label>
          <select id="send-backend">
            ${backends.map((b) => `<option value="${esc(b.key)}" ${b.available ? "" : "disabled"}>${esc(b.label)}${b.available ? "" : "（未接入）"}</option>`).join("")}
          </select>
          <div class="hint-line">${esc((backends.find((b) => b.available) || {}).note || "当前无可用执行器")}</div>
        </div>
        <div class="field">
          <label>运行步数</label>
          <input id="send-steps" type="number" min="60" max="3600" step="60" value="${defSteps}">
          <div class="hint-line">控制周期 1 s；离线回放的最大步数受归档数据集长度限制。</div>
        </div>
        <div class="field">
          <label>车钩物理模型</label>
          <select id="send-coupler">
            <option value="linear">linear · 纯线性弹簧 γ=500 kN/m（论文假设）</option>
            <option value="mt2">mt2 · MT-2 迟滞车钩（真实物理）</option>
            <option value="zero">zero · 车钩阻抗置零（消融对照）</option>
          </select>
        </div>
        <div class="field">
          <label>空气制动监督</label>
          <select id="send-brake">
            <option value="atp">atp · ATP 硬限速（超速 1 km/h 触发）</option>
            <option value="cyclic">cyclic · 循环制动（文献[22]）</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" data-action="close-modal">取消</button>
          <button class="btn btn-primary" data-action="confirm-send" data-algo="${esc(algo.key)}">发送并运行</button>
        </div>
      </div>`;
    modal.classList.remove("hidden");
  }

  function closeModal() {
    el("modal").classList.add("hidden");
    el("modal").innerHTML = "";
  }

  async function confirmSend(algorithmKey) {
    const backend = el("send-backend").value;
    const steps = parseInt(el("send-steps").value, 10) || 1200;
    const coupler = el("send-coupler").value;
    const brake = el("send-brake").value;
    try {
      const res = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({
          algorithm: algorithmKey,
          backend: backend,
          options: { steps: steps, coupler_model: coupler, brake_supervisor: brake },
        }),
      });
      closeModal();
      toast("已发送：" + res.job.algorithm_name + " → " + res.job.backend_label);
      state.selectedId = res.job.id;
      state.selectedJob = res.job;
      state.runs = [res.job].concat(state.runs);
      setView("runtime");
      renderRuntime();
    } catch (err) {
      toast(err.message, true);
    }
  }

  // ---------------------------------------------------------------- 仿真运行
  async function refreshRuns() {
    try {
      const data = await api("/api/runs");
      state.runs = data.runs || [];
      if (state.view === "runtime") {
        renderRuntime(true);
        const latest = state.runs.find((r) => r.id === state.selectedId);
        const cur = state.selectedJob;
        const changed = latest && (!cur || latest.status !== cur.status
          || Math.round((latest.progress || 0) * 100) !== Math.round((cur.progress || 0) * 100));
        if (state.selectedId && changed) loadJobDetail(state.selectedId);
      }
      if (state.overview) el("foot-runs").textContent = state.runs.length;
    } catch (err) {
      // 轮询失败静默处理，避免打扰操作
    }
  }

  function renderRuntime(listOnly) {
    if (!state.overview) return;
    const backends = state.overview.backends;
    const offline = backends.find((b) => b.kind === "placeholder");
    const prevScroll = (el("view-runtime").querySelector(".run-list") || {}).scrollTop || 0;
    const prevDetail = (el("view-runtime").querySelector("#run-detail") || {}).innerHTML || "";
    const banner = `
      <div class="banner">
        <div><b>联合仿真环境还没接上。</b>
        ${offline ? "现在用「" + esc(offline.label) + "」在归档轨迹上跑所选算法，不做物理推进。" : ""}
        环境接上后只换执行器，算法和保护层代码不用动。</div>
      </div>`;

    const backendCards = `
      <div class="backend-grid">
        ${backends.map((b) => `
          <div class="card backend ${b.available ? "" : "unavail"}">
            <div class="b-head"><h4>${esc(b.label)}</h4>
              <span class="pill ${b.available ? "completed" : "queued"}">${b.available ? "可用" : "未接入"}</span></div>
            <p>${esc(b.description)}</p>
            <div class="b-note">${esc(b.note)}</div>
          </div>`).join("")}
      </div>`;

    const rows = state.runs;
    const listHtml = rows.length ? rows.map((r) => `
      <div class="run-item ${state.selectedId === r.id ? "active" : ""}" data-action="select-run" data-id="${r.id}">
        <div class="r-top">
          <span class="r-name">${esc(r.algorithm_name)}</span>
          <span class="pill ${r.status}">${esc(r.status_text)}</span>
        </div>
        <div class="r-id">${esc(r.id)}</div>
        <div class="r-meta"><span>${esc(r.backend_label)}</span><span>${esc(r.created_at)}</span>
          <span>${r.config && r.config.coupler_model ? esc(r.config.coupler_model) : ""}</span></div>
        <div class="progress ${r.status === "completed" ? "done" : ""}"><i style="width:${Math.round((r.progress || 0) * 100)}%"></i></div>
      </div>`).join("") : `<div class="empty">还没有任务。到「算法管理」发送一个算法。</div>`;

    el("view-runtime").innerHTML = banner + backendCards + `
      <div class="run-layout">
        <div class="card"><div class="card-pad" style="padding-bottom:6px">
          <div class="section-title"><span>运行任务（${rows.length}）</span><span class="line"></span>
            <button class="btn btn-ghost" data-action="refresh-runs">刷新</button></div>
        </div><div class="run-list">${listHtml}</div></div>
        <div class="card detail" id="run-detail">${state.selectedJob ? "" : `<div class="detail-empty">选择左侧任务查看进度、指标与曲线</div>`}</div>
      </div>`;

    const list = el("view-runtime").querySelector(".run-list");
    if (list) list.scrollTop = prevScroll;
    const detail = el("run-detail");
    if (detail && listOnly && prevDetail) {
      detail.innerHTML = prevDetail;
      // innerHTML 恢复会清空 canvas 位图，这里按当前任务重新绘制曲线
      const canvas = el("run-chart");
      if (canvas && state.selectedJob && state.selectedJob.series && state.selectedJob.series.t) {
        drawChart(canvas, state.selectedJob.series);
      }
    }
    if (state.selectedJob && !listOnly) renderJobDetail(state.selectedJob);
  }

  async function loadJobDetail(jobId) {
    try {
      const job = await api("/api/runs/" + jobId);
      state.selectedJob = job;
      if (state.view === "runtime") renderJobDetail(job);
    } catch (err) {
      // 任务被清理时忽略
    }
  }

  function renderJobDetail(job) {
    const box = el("run-detail");
    if (!box) return;
    const m = job.metrics || {};
    const errAvg = m.track_err_avg_kmh;
    const overMax = m.overspeed_max_kmh;
    const metricItems = [
      ["步数", m.steps],
      ["仿真时长", m.t_end_s ? fmt(m.t_end_s, 1) + " s" : "-"],
      ["运行里程", m.dist_km ? fmt(m.dist_km, 2) + " km" : "-"],
      ["平均求解", m.solve_ms_mean ? fmt(m.solve_ms_mean, 3) + " ms" : "-"],
      ["跟踪误差均值", errAvg !== undefined ? fmt(errAvg, 2) + " km/h" : "-"],
      ["最大超速", overMax !== undefined ? fmt(overMax, 2) + " km/h" : "-"],
      ["车钩力峰值", Array.isArray(m.fc_peak_kN) ? m.fc_peak_kN.join(" / ") + " kN" : "-"],
      ["最小头车间距", m.gap_min_m !== undefined ? fmt(m.gap_min_m, 0) + " m" : "-"],
    ];

    const cfg = job.config || {};
    box.innerHTML = `
      <div class="r-top" style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
        <div><h3>${esc(job.algorithm_name)}</h3>
          <div class="d-sub">${esc(job.id)} · ${esc(job.backend_label)}</div></div>
        <span class="pill ${job.status}">${esc(job.status_text)}</span>
      </div>
      <div class="progress ${job.status === "completed" ? "done" : ""}" style="margin-top:12px"><i style="width:${Math.round((job.progress || 0) * 100)}%"></i></div>
      <div class="d-sub" style="margin-top:8px">${esc(job.stage)}${job.message ? " · " + esc(job.message) : ""}</div>
      <div class="d-sub" style="margin-top:4px">车钩 ${esc(cfg.coupler_model || "-")} · 制动监督 ${esc(cfg.brake_supervisor || "-")} · 控制周期 ${esc(cfg.dt_mpc || "-")} s · 创建 ${esc(job.created_at)}</div>
      <div class="metrics">
        ${metricItems.map((it) => `<div class="metric"><div class="m-label">${esc(it[0])}</div><div class="m-value">${esc(it[1])}</div></div>`).join("")}
      </div>
      <div class="chart-box"><canvas id="run-chart"></canvas></div>
      <div class="legend">
        <span><i data-line="sup"></i>监督限速 v_sup</span>
        <span><i data-line="ref"></i>参考速度 v_ref</span>
        <span><i data-line="lead"></i>头车</span>
        <span><i data-line="follow"></i>跟随车</span>
        <span><i data-line="tail"></i>尾车</span>
      </div>
      <div class="log">${esc((job.log || []).join("\n") || "无运行日志")}</div>`;

    const canvas = el("run-chart");
    if (canvas && job.series && job.series.t && job.series.t.length) drawChart(canvas, job.series);
    else if (canvas) drawEmpty(canvas, job.status === "running" ? "运行中，曲线还没写出来" : "没有曲线：离线回放只记录算法输出");
  }

  function drawEmpty(canvas, text) {
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 600, h = canvas.clientHeight || 260;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#6b7a90";
    ctx.font = "13px 'Microsoft YaHei', sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(text, w / 2, h / 2);
  }

  function drawChart(canvas, series) {
    const colors = { sup: "#a98a5c", ref: "#7c8794", lead: "#6aa6ff", follow: "#c4cedb", tail: "#8794a6" };
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 640;
    const h = canvas.clientHeight || 260;
    canvas.width = w * dpr; canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const pad = { l: 46, r: 14, t: 16, b: 28 };
    const iw = w - pad.l - pad.r;
    const ih = h - pad.t - pad.b;
    const t = series.t || [];
    const lines = [
      { key: "v_sup", color: colors.sup, dash: true },
      { key: "v_ref", color: colors.ref, dash: true },
      { key: "v_lead", color: colors.lead },
      { key: "v_follow", color: colors.follow },
      { key: "v_tail", color: colors.tail },
    ].filter((l) => Array.isArray(series[l.key]) && series[l.key].length);

    if (!t.length || !lines.length) { drawEmpty(canvas, "无曲线数据"); return; }

    const tMin = t[0], tMax = t[t.length - 1] || 1;
    let vMax = 1;
    lines.forEach((l) => series[l.key].forEach((v) => { if (v > vMax) vMax = v; }));
    vMax = Math.ceil(vMax / 10) * 10 + 5;

    const X = (x) => pad.l + (tMax === tMin ? 0.5 : (x - tMin) / (tMax - tMin)) * iw;
    const Y = (v) => pad.t + ih - (v / vMax) * ih;

    // 网格与刻度
    ctx.strokeStyle = "rgba(255,255,255,0.08)";
    ctx.fillStyle = "#6b7a90";
    ctx.lineWidth = 1;
    ctx.font = "11px Consolas, monospace";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const v = (vMax / 4) * i;
      const y = Y(v);
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillText(v.toFixed(0), pad.l - 8, y);
    }
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (let i = 0; i <= 4; i++) {
      const x = tMin + (tMax - tMin) * (i / 4);
      const px = X(x);
      ctx.beginPath(); ctx.moveTo(px, pad.t); ctx.lineTo(px, pad.t + ih); ctx.strokeStyle = "rgba(255,255,255,0.05)"; ctx.stroke();
      ctx.fillStyle = "#6b7a90";
      ctx.fillText((x / 60).toFixed(0) + "min", px, pad.t + ih + 8);
    }
    ctx.fillStyle = "#6b7a90";
    ctx.textAlign = "left";
    ctx.fillText("速度 km/h", 8, pad.t - 2);

    lines.forEach((l) => {
      const vals = series[l.key];
      ctx.beginPath();
      vals.forEach((v, i) => {
        const px = X(t[i] === undefined ? tMin : t[i]);
        const py = Y(v);
        if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
      });
      ctx.strokeStyle = l.color;
      ctx.lineWidth = l.dash ? 1.4 : 2;
      ctx.setLineDash(l.dash ? [6, 4] : []);
      ctx.stroke();
      ctx.setLineDash([]);
    });
  }

  // ---------------------------------------------------------------- 数据记录
  async function loadRecords() {
    try {
      const data = await api("/api/records");
      state.records = data.records || [];
      renderRecords();
    } catch (err) {
      toast(err.message, true);
    }
  }

  function renderRecords() {
    const filters = [{ key: "all", label: "全部" }, { key: "outputs_platform", label: "平台输出" },
      { key: "outputs_shuohuang", label: "朔黄线基线" }];
    const rows = state.records.filter((r) => state.recordFilter === "all" || r.domain === state.recordFilter);
    el("view-records").innerHTML = `
      <div class="card card-pad">
        <div class="section-title"><span>运行记录（${rows.length}）</span><span class="line"></span>
          <button class="btn btn-ghost" data-action="refresh-records">刷新</button></div>
        <div class="filters">
          ${filters.map((f) => `<button class="btn ${state.recordFilter === f.key ? "active" : ""}"
            data-action="filter-records" data-filter="${f.key}">${f.label}</button>`).join("")}
        </div>
        ${rows.length ? `
        <div class="table-wrap"><table>
          <thead><tr><th>文件</th><th>来源</th><th>类型</th><th class="num">大小</th><th>修改时间</th><th></th></tr></thead>
          <tbody>${rows.map((r) => `
            <tr><td class="mono">${esc(r.name)}</td>
              <td>${r.domain === "outputs_platform" ? "平台输出" : "朔黄线基线"}</td>
              <td><span class="param">${esc(r.kind)}</span></td>
              <td class="num">${fmt(r.size_kb, 1)} KB</td>
              <td class="mono">${esc(r.modified)}</td>
              <td><a class="btn btn-ghost" href="${esc(r.url)}">下载</a></td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty">没有可下载的记录文件</div>`}
      </div>`;
  }

  // ---------------------------------------------------------------- 分析服务
  async function loadAnalysis() {
    try {
      const data = await api("/api/analysis");
      state.analysis = data;
      renderAnalysis();
    } catch (err) {
      toast(err.message, true);
    }
  }

  function renderAnalysis() {
    const data = state.analysis || { rows: [], note: "" };
    const rows = data.rows || [];
    el("view-analysis").innerHTML = `
      <div class="card card-pad" style="margin-bottom:16px">
        <div class="section-title"><span>分析服务说明</span><span class="line"></span></div>
        <p style="margin:0;font-size:12.5px;line-height:1.7;color:var(--muted)">${esc(data.note)}</p>
      </div>
      <div class="card card-pad">
        <div class="section-title"><span>算法横向对比（${rows.length}）</span><span class="line"></span>
          <button class="btn btn-ghost" data-action="refresh-analysis">刷新</button></div>
        ${rows.length ? `
        <div class="table-wrap"><table>
          <thead><tr><th>算法</th><th>执行器</th><th class="num">步数</th><th class="num">时长 s</th>
            <th class="num">里程 km</th><th class="num">求解 ms</th><th class="num">跟踪误差 km/h</th>
            <th class="num">最大超速 km/h</th><th>车钩力峰值 kN</th></tr></thead>
          <tbody>${rows.map((r) => `
            <tr><td>${esc(r.algorithm_name)}</td><td>${esc(r.backend)}</td>
              <td class="num">${fmt(r.steps, 0)}</td><td class="num">${fmt(r.t_end_s, 1)}</td>
              <td class="num">${fmt(r.dist_km, 2)}</td><td class="num">${fmt(r.solve_ms_mean, 2)}</td>
              <td class="num">${fmt(r.track_err_avg_kmh, 2)}</td><td class="num">${fmt(r.overspeed_max_kmh, 2)}</td>
              <td class="mono">${Array.isArray(r.fc_peak_kN) ? r.fc_peak_kN.map((x) => fmt(x, 0)).join(" / ") : "-"}</td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty">还没有已完成的任务。先到「算法管理」发送一个算法。</div>`}
      </div>`;
  }

  // ---------------------------------------------------------------- 演示模式
  const DEMO = { active: false, steps: [], index: 0, timer: null, pollTimer: null, paused: false, deadline: 0, remaining: 0 };

  async function startDemo() {
    if (DEMO.active) return;
    DEMO.active = true;
    DEMO.index = 0;
    DEMO.steps = [];
    document.body.classList.add("demo-on");
    renderDemoBar("正在准备三组预置任务…");
    await waitDemoReady();
  }

  async function waitDemoReady() {
    clearTimeout(DEMO.pollTimer);
    try {
      const data = await api("/api/demo");
      if (!DEMO.active) return;
      if (!data.ready) {
        renderDemoBar("正在准备三组预置任务…");
        DEMO.pollTimer = setTimeout(waitDemoReady, 900);
        return;
      }
      DEMO.steps = data.steps || [];
      demoGo(0);
    } catch (err) {
      toast("演示模式启动失败：" + err.message, true);
      demoExit();
    }
  }

  async function demoGo(i) {
    clearTimeout(DEMO.timer);
    if (!DEMO.active) return;
    if (i >= DEMO.steps.length) {
      demoExit();
      toast("演示结束");
      return;
    }
    DEMO.index = i;
    const step = DEMO.steps[i];
    if (step.view === "runtime" && step.run_id) {
      state.selectedId = step.run_id;
      state.selectedJob = null;
      setView("runtime");
      await refreshRuns();
      await loadJobDetail(step.run_id);
      // 详情里的速度曲线在首屏下方，演示时自动滚到可见位置
      const chart = el("run-chart");
      if (chart) setTimeout(() => {
        if (DEMO.active) chart.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 150);
    } else {
      setView(step.view);
    }
    if (!DEMO.active) return;
    DEMO.paused = false;
    DEMO.deadline = Date.now() + step.seconds * 1000;
    DEMO.timer = setTimeout(() => demoGo(i + 1), step.seconds * 1000);
    renderDemoBar();
  }

  function demoPause() {
    if (!DEMO.active) return;
    if (DEMO.paused) {
      DEMO.paused = false;
      DEMO.deadline = Date.now() + DEMO.remaining;
      DEMO.timer = setTimeout(() => demoGo(DEMO.index + 1), DEMO.remaining);
    } else {
      DEMO.paused = true;
      DEMO.remaining = Math.max(0, DEMO.deadline - Date.now());
      clearTimeout(DEMO.timer);
    }
    renderDemoBar();
  }

  function demoExit() {
    DEMO.active = false;
    DEMO.paused = false;
    clearTimeout(DEMO.timer);
    clearTimeout(DEMO.pollTimer);
    DEMO.timer = null;
    DEMO.pollTimer = null;
    document.body.classList.remove("demo-on");
    const bar = el("demo-bar");
    bar.hidden = true;
    bar.innerHTML = "";
  }

  function renderDemoBar(preparing) {
    const bar = el("demo-bar");
    if (!DEMO.active) { bar.hidden = true; return; }
    bar.hidden = false;
    if (preparing) {
      bar.innerHTML = `<div class="demo-top"><span class="demo-idx">准备中</span><b>${esc(preparing)}</b></div>`;
      return;
    }
    const step = DEMO.steps[DEMO.index];
    if (!step) return;
    bar.innerHTML = `
      <div class="demo-top">
        <span class="demo-idx">${DEMO.index + 1} / ${DEMO.steps.length}</span>
        <b>${esc(step.label)}</b>
        <span class="demo-dots">${DEMO.steps.map((s, i) => `<i class="${i === DEMO.index ? "on" : i < DEMO.index ? "done" : ""}"></i>`).join("")}</span>
        <div class="demo-btns">
          <button class="btn btn-ghost" data-action="demo-pause">${DEMO.paused ? "继续" : "暂停"}</button>
          <button class="btn btn-ghost" data-action="demo-next">下一步</button>
          <button class="btn btn-ghost" data-action="demo-exit">退出</button>
        </div>
      </div>
      <p class="demo-note">${esc(step.note || "")}</p>`;
  }

  // ---------------------------------------------------------------- 事件
  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("[data-action]");
    if (!t) return;
    const action = t.dataset.action;

    if (action === "view") { if (DEMO.active) demoExit(); setView(t.dataset.view); }
    else if (action === "demo-start") startDemo();
    else if (action === "demo-exit") demoExit();
    else if (action === "demo-pause") demoPause();
    else if (action === "demo-next") { clearTimeout(DEMO.timer); demoGo(DEMO.index + 1); }
    else if (action === "send") openSendModal(t.dataset.algo);
    else if (action === "close-modal") closeModal();
    else if (action === "confirm-send") { t.disabled = true; confirmSend(t.dataset.algo); }
    else if (action === "select-run") { state.selectedId = t.dataset.id; state.selectedJob = null; setView("runtime"); loadJobDetail(t.dataset.id); renderRuntime(); }
    else if (action === "refresh-runs") refreshRuns();
    else if (action === "refresh-records") loadRecords();
    else if (action === "refresh-analysis") loadAnalysis();
    else if (action === "filter-records") { state.recordFilter = t.dataset.filter; renderRecords(); }
  });

  el("modal").addEventListener("click", (ev) => { if (ev.target.id === "modal") closeModal(); });
  document.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape") return;
    if (!el("modal").classList.contains("hidden")) { closeModal(); return; }
    if (DEMO.active) demoExit();
  });

  window.addEventListener("resize", () => {
    if (state.selectedJob && state.selectedJob.series && el("run-chart")) {
      drawChart(el("run-chart"), state.selectedJob.series);
    }
  });

  // ---------------------------------------------------------------- 启动
  function tickClock() {
    const d = new Date();
    const p = (n) => String(n).padStart(2, "0");
    el("clock").textContent = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }

  async function boot() {
    tickClock();
    setInterval(tickClock, 1000);
    try {
      await loadOverview();
      renderAlgorithms();
      setView("home");
    } catch (err) {
      toast("平台初始化失败：" + err.message, true);
    }
  }

  boot();
})();
