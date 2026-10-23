"use strict";
const $ = (s) => document.querySelector(s);
const escapeHTML = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let state = null, filter = "all", view = "tasks", selected = null, loading = false, busy = false, toastTimer;
let engine = "all", pageNumber = 1;
const planDrafts = new Map();
const planLabels = {off:"未预约",armed:"等待下一窗口恢复",sending:"正在确认发送",sent:"已发送一次，预约已关闭",cancelled:"已取消预约",needs_review:"需要重新确认预约"};
const waitingStates = new Set(["paused", "pause_intent", "resume_intent"]);
const labels = {watching:"纳入监测", pause_intent:"开始暂停", paused:"已确认暂停", resume_intent:"提交续做", running:"已续做", needs_review:"需要核对", disabled:"已撤销控制", held:"保持任务", supervisor_paused:"暂停自动控制", supervisor_enabled:"启用自动控制"};
function timeText(stamp, full = false) {
  if (!stamp) return "—";
  return new Date(stamp * 1000).toLocaleString("zh-CN", full ? {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false} : {hour:"2-digit",minute:"2-digit",hour12:false});
}
function ago(stamp) {
  if (!stamp) return "尚未检查";
  const seconds = Math.max(0, Math.round(Date.now()/1000-stamp));
  return seconds < 10 ? "刚刚同步" : seconds < 60 ? `${seconds} 秒前同步` : `${Math.floor(seconds/60)} 分钟前同步`;
}
const subscriptionLabels = {free:"Free",go:"Go",plus:"Plus",pro:"Pro",team:"Team",business:"Business",enterprise:"Enterprise",edu:"Edu"};
function renderUsage(disconnected = false) {
  const usage = state?.usage || {}, account = usage.account;
  const plan = account?.plan_type?.toLowerCase() || "unknown";
  const label = Object.hasOwn(subscriptionLabels, plan) ? subscriptionLabels[plan] : (plan === "unknown" ? "待识别" : account.plan_type);
  const section = $(".account-section");
  const stale = disconnected || usage.stale || !usage.observed_at || Date.now()/1000 - usage.observed_at > 90;
  section.classList.toggle("stale", stale);
  $("#planBadge").textContent=label;
  $("#planBadge").className="plan-badge " + (Object.hasOwn(subscriptionLabels, plan) ? plan : "unknown");
  $("#quotaCaption").textContent=account ? `${account.type === "chatgpt" ? "ChatGPT" : account.type} · ${label === "待识别" ? "订阅待识别" : label + " 账号"}` : "账号信息暂未提供";
  [["fiveHour","five_hour"],["weekly","weekly"]].forEach(([prefix,key])=>{
    const w = usage.windows?.[key];
    const value = typeof w?.remaining === "number" && Number.isFinite(w.remaining) && w.remaining >= 0 && w.remaining <= 100 ? w.remaining : null;
    const block=$("#"+prefix+"Quota"), progress=$("#"+prefix+"Progress");
    block.classList.toggle("unknown",value === null);
    block.classList.toggle("low",value !== null && value <= 10);
    block.classList.toggle("warning",value !== null && value > 10 && value <= 20);
    $("#"+prefix+"Remaining").textContent=value === null ? "未提供" : `${Number(value.toFixed(1))}%`;
    progress.value=value ?? 0;
    progress.setAttribute("aria-valuetext",value === null ? "服务未提供此额度" : `剩余 ${value}%${stale ? "，上次记录" : ""}`);
    const reset=$("#"+prefix+"Reset"), countdown=$("#"+prefix+"Countdown");
    if (value !== null && Number.isFinite(w?.reset)) {
      reset.dateTime=new Date(w.reset*1000).toISOString();
      reset.textContent="下次刷新 " + new Date(w.reset*1000).toLocaleString("zh-CN",{timeZone:"Asia/Dubai",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false});
      reset.title="服务返回的刷新时间 · Asia/Dubai";
      const minutes=Math.ceil((w.reset-Date.now()/1000)/60);
      countdown.textContent=stale ? "上次记录，等待重新核验" : minutes <= 0 ? "已到刷新时间，等待核验" : minutes >= 1440 ? `${Math.floor(minutes/1440)} 天 ${Math.floor(minutes%1440/60)} 小时后` : minutes >= 60 ? `${Math.floor(minutes/60)} 小时 ${minutes%60} 分后` : `${minutes} 分钟后`;
    } else {
      reset.removeAttribute("datetime");reset.textContent="刷新时间未提供";countdown.textContent="以账号实际限额为准";
    }
  });
  $("#usageFreshness").textContent=stale ? "额度待同步 · 显示上次记录" : "服务实时限额 · 迪拜时间";
  const name=account?.name || account?.email?.split("@")[0] || "未识别账号";
  $("#accountName").textContent=name;
  $("#accountEmail").textContent=account?.email || "登录信息暂未提供";
  $("#accountEmail").title=account?.email || "";
  $("#accountId").textContent=account?.id || "接口暂未提供";
  $("#copyAccountId").disabled=!account?.id;
  $("#avatarInitials").textContent=account ? name.trim().split(/\s+/).map(s=>Array.from(s)[0]).slice(0,2).join("").toUpperCase() || "?" : "?";
  const image=$("#accountAvatarImage"), src=account?.avatar_url;
  $("#accountAvatar").setAttribute("aria-label",src ? `${name}的头像` : `${name}的姓名首字母头像`);
  if (src && src.startsWith("https://")) {
    if (image.getAttribute("src") !== src) {image.src=src;image.hidden=false;}
  } else {image.hidden=true;image.removeAttribute("src");}
}
function allowed(t) { return t.auto_resume && !t.manual_hold && t.state !== "disabled"; }
function scheduled(t) { return ["armed","sending"].includes(t.plan?.state); }
function signal(t) {
  if (t.connection_error) return {kind:"attention",label:"连接待恢复"};
  if (t.state === "needs_review" || t.plan?.state === "needs_review") return {kind:"attention",label:"需要检查"};
  if (waitingStates.has(t.state)) return {kind:"waiting",label:t.state === "pause_intent" ? "确认暂停中" : t.state === "resume_intent" ? "确认续做中" : t.recovery_first_seen ? "复核恢复条件" : "等待恢复"};
  if (t.runtime?.activeFlags?.length) return {kind:"attention",label:"等待你处理"};
  if (t.runtime?.type === "active") return {kind:"active",label:"执行中"};
  if (t.auto_pending) return {kind:"waiting",label:"正在连接"};
  if (t.runtime?.type === "idle") return {kind:"neutral",label:"等待指令"};
  if (t.runtime?.type === "notLoaded") return {kind:"neutral",label:"未打开"};
  if (t.runtime?.type === "systemError") return {kind:"attention",label:"回合出错"};
  return {kind:"neutral",label:t.can_control === false ? "状态待同步" : "状态待核对"};
}
function badge(t) { const s = signal(t); return `<span class="badge ${s.kind}"><span class="small-dot"></span>${s.label}</span>`; }
function eventLabel(e) {
  if (Object.hasOwn(e.detail, "automatic_control_allowed")) return e.detail.automatic_control_allowed ? "允许自动控制" : "保持任务";
  const plans={plan_armed:"预约下一窗口执行",plan_sending:"提交预约指令",plan_sent:"预约指令已发送",immediate_pending:"提交立刻执行",immediate_sent:"立刻执行已确认发送",immediate_failed:"立刻执行未发送",immediate_unknown:"立刻执行结果待核对",plan_cancelled:"取消预约",plan_needs_review:"预约需要确认"};
  return plans[e.state] || labels[e.state] || e.state || "状态更新";
}
function eventNote(e) { return e.detail.reason || (e.detail.pause_source === "quota" ? "已登记额度中断，等待符合恢复条件" : e.detail.source === "local_ui" ? "来自本机控制界面" : e.previous_state ? `${labels[e.previous_state] || e.previous_state} → ${labels[e.state] || e.state}` : "控制状态已保存"); }
function toast(message) { $("#toast").textContent=message; $("#toast").hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$("#toast").hidden=true,4500); }
function setView(next) {
  view=next;
  document.querySelectorAll(".nav").forEach(el=>el.classList.toggle("active",el.dataset.view===view));
  ["tasks","events","rules"].forEach(name=>$("#"+name+"View").hidden=name!==view);
  const titles={tasks:["任务控制","让任务接着完成。","在合适的时候暂停，在准备就绪后继续。"],events:["操作记录","发生过的，都有记录。","从暂停到续做，核对每一次真实操作。"],rules:["运行规则","边界清楚，接续有序。","你保留控制权，管家负责按规则执行。"]};
  $("#crumb").textContent=titles[view][0]; $("#pageTitle").textContent=titles[view][1]; $("#pageDescription").textContent=titles[view][2];
}
function renderEvents() {
  if (!state) return;
  const events=state.events;
  $("#recentEvents").innerHTML=events.slice(0,5).map(e=>`<div class="activity-item"><span class="event-mark">${e.state === "running" ? "↗" : e.state === "paused" ? "Ⅱ" : "·"}</span><div><strong>${escapeHTML(eventLabel(e))}</strong><p>${escapeHTML(e.name)}</p><time>${timeText(e.created,true)}</time></div></div>`).join("") || '<p class="empty">还没有控制操作记录</p>';
  const query=$("#eventSearch").value.trim().toLowerCase();
  const list=events.filter(e=>`${e.name} ${eventLabel(e)} ${eventNote(e)}`.toLowerCase().includes(query));
  $("#eventRows").innerHTML=list.map(e=>`<tr><td class="event-time">${timeText(e.created,true)}</td><td>${escapeHTML(e.name)}</td><td>${escapeHTML(eventLabel(e))}</td><td>${escapeHTML(eventNote(e))}</td></tr>`).join("") || '<tr><td colspan="4" class="empty">没有匹配的操作记录</td></tr>';
}
function executionStage(t) {
  const stage=t.execution_stage;
  const text=stage?.text || (t.can_control === false ? "当前仅同步目录，执行阶段暂不可读" : "暂未读取到执行进展");
  const label=!stage ? "暂不可读" : stage.phase === "waiting" ? "等待进展" : stage.phase === "result" ? "最近结果" : t.runtime?.type === "active" ? "本轮进展" : "最近进展";
  const stamp=stage?.updated_at ? ` · ${timeText(stage.updated_at,true)}` : "";
  return `<div class="execution-stage ${stage ? "" : "unavailable"}"><div class="stage-heading"><span>当前执行阶段</span><small>${escapeHTML(label + stamp)}</small></div><p title="${escapeHTML(text)}">${escapeHTML(text)}</p></div>`;
}
function automaticControl(t) {
  return `<div class="auto-control"><span>自动控制</span><div><button class="switch ${allowed(t)?"on":""}" role="switch" aria-checked="${Boolean(allowed(t))}" aria-label="${escapeHTML(t.name)}：允许自动控制" title="${escapeHTML(t.capability_note || "按额度暂停并自动续接")}" data-toggle="${escapeHTML(t.id)}" ${busy || t.can_control === false || t.auto_pending?"disabled":""}></button><small>${t.can_control === false?"不可用":t.auto_pending?"连接中":allowed(t)?"已开启":"已关闭"}</small></div></div>`;
}
function immediatePending(t) {return ["pending","checking","sending"].includes(t.immediate?.state);}
function immediateReceipt(t) {
  const r=t.immediate;if(!r)return "";
  const labels={pending:"待发送",checking:"正在检查",sending:"正在确认发送",sent:"已确认发送",failed:"未发送",unknown:"发送结果待核对"};
  return `<div class="immediate-receipt ${r.state === "sent"?"success":""}" role="status"><strong>${escapeHTML(labels[r.state] || r.state)}</strong>${r.message?`<span>${escapeHTML(r.message)}</span>`:""}${r.turn_id?`<small>回合 ${escapeHTML(r.turn_id.slice(0,8))}</small>`:""}<small title="${escapeHTML(r.id)}">发送标识 ${escapeHTML(r.id.slice(0,8))}</small></div>`;
}
function renderTasks() {
  if (!state) return;
  const query=$("#search").value.trim().toLowerCase();
  const list=state.tasks.filter(t=>`${t.name} ${t.id}`.toLowerCase().includes(query) && (engine === "all" || (t.category || "codex") === engine) && (filter === "all" || filter === "waiting" && (signal(t).kind === "waiting" || scheduled(t)) || filter === "scheduled" && scheduled(t) || filter === "attention" && signal(t).kind === "attention"));
  const pages=Math.max(1,Math.ceil(list.length/20));pageNumber=Math.min(pageNumber,pages);
  const visible=list.slice((pageNumber-1)*20,pageNumber*20);
  const focused=document.activeElement?.dataset?.toggle;
  const editing=document.activeElement?.dataset?.planInput;
  const selection=editing ? [document.activeElement.selectionStart,document.activeElement.selectionEnd] : null;
  $("#taskRows").innerHTML=visible.map(t=>{const p=t.plan || {state:"off",prompt:"继续任务",revision:0},draft=planDrafts.get(t.key),prompt=draft?.text ?? p.prompt ?? "继续任务";return `<tr><td><div class="task-name-cell"><span class="task-icon">${t.category === "chatgpt" ? "◉" : t.goal ? "◎" : "▤"}</span><div><span class="task-name" title="${escapeHTML(t.name)}">${escapeHTML(t.name)}</span><span class="task-sub">${escapeHTML(t.source_label || "Codex")} / ${escapeHTML(t.id.slice(0,8))}</span>${executionStage(t)}</div></div></td><td class="status-cell">${badge(t)}${automaticControl(t)}</td><td class="plan-cell">${t.can_control === false ? `<span class="plan-unavailable">仅显示目录</span>` : `<div class="plan-top"><button class="switch ${scheduled(t)?"on":""}" role="switch" aria-checked="${scheduled(t)}" aria-label="${escapeHTML(t.name)}：额度恢复后执行一次" data-plan-toggle="${escapeHTML(t.key)}" ${busy || p.state === "sending"?"disabled":""}></button><span class="plan-status ${p.state === "needs_review"?"attention":""}">${escapeHTML(planLabels[p.state] || p.state)}</span></div><div class="plan-editor"><textarea rows="2" maxlength="8000" data-plan-input="${escapeHTML(t.key)}" aria-label="${escapeHTML(t.name)}：恢复后执行的指令" ${busy || p.state === "sending"?"disabled":""}>${escapeHTML(prompt)}</textarea><button class="plan-save" data-plan-save="${escapeHTML(t.key)}" ${busy || p.state === "sending"?"disabled":""}>${scheduled(t)?"保存指令":"保存并预约"}</button><button class="plan-execute" data-execute-now="${escapeHTML(t.key)}" aria-label="${escapeHTML(t.name)}：立刻执行输入框中的指令" title="发送当前输入框的指令，不等待额度刷新" ${busy || immediatePending(t) || p.state === "sending" || t.runtime?.type === "active" || t.runtime?.activeFlags?.length?"disabled":""}>立刻执行</button></div>${immediateReceipt(t)}${p.reason?`<p class="plan-reason">${escapeHTML(p.reason)}</p>`:""}${p.state === "needs_review"?`<button class="plan-cancel" data-plan-cancel="${escapeHTML(t.key)}">取消此预约</button>`:""}`}</td><td><button class="detail-button" data-detail="${escapeHTML(t.id)}" aria-label="查看${escapeHTML(t.name)}详情">↗</button></td></tr>`;}).join("") || '<tr><td colspan="4" class="empty">没有匹配的聊天</td></tr>';
  document.querySelectorAll("[data-toggle]").forEach(el=>el.addEventListener("click",()=>toggleTask(el.dataset.toggle)));
  document.querySelectorAll("[data-detail]").forEach(el=>el.addEventListener("click",()=>openDetail(el.dataset.detail)));
  document.querySelectorAll("[data-plan-toggle]").forEach(el=>el.addEventListener("click",()=>submitPlan(el.dataset.planToggle,true)));
  document.querySelectorAll("[data-plan-cancel]").forEach(el=>el.addEventListener("click",()=>submitPlan(el.dataset.planCancel,"cancel")));
  document.querySelectorAll("[data-execute-now]").forEach(el=>el.addEventListener("click",()=>executeNow(el.dataset.executeNow)));
  document.querySelectorAll("[data-plan-save]").forEach(el=>el.addEventListener("click",()=>submitPlan(el.dataset.planSave,false)));
  document.querySelectorAll("[data-plan-input]").forEach(el=>el.addEventListener("input",()=>{const t=state.tasks.find(t=>t.key===el.dataset.planInput);const old=planDrafts.get(t.key);planDrafts.set(t.key,{text:el.value,revision:old?.revision ?? t.plan?.revision ?? 0});}));
  if (focused) [...document.querySelectorAll("[data-toggle]")].find(el=>el.dataset.toggle===focused)?.focus({preventScroll:true});
  if(editing){const el=[...document.querySelectorAll("[data-plan-input]")].find(el=>el.dataset.planInput===editing);el?.focus({preventScroll:true});if(el&&selection)el.setSelectionRange(...selection);}
  $("#listFooter").textContent=`共 ${list.length} / ${state.tasks.length} 个聊天 · 每页 20 个`;
  $("#pageNumber").textContent=`${pageNumber} / ${pages}`;$("#previousPage").disabled=pageNumber<=1;$("#nextPage").disabled=pageNumber>=pages;
}
function renderDetail() {
  if (!selected || !state) return;
  const t=state.tasks.find(t=>t.id===selected); if (!t) { $("#taskDialog").close(); return; }
  $("#detailTitle").textContent=t.name;
  $("#detailBody").innerHTML=`<div class="detail-line"><span>当前状态</span>${badge(t)}</div>${executionStage(t)}<div class="detail-line"><span>任务类型</span><span>${t.goal ? "Goal 目标任务" : "普通聊天任务"}</span></div><div class="detail-line"><span>自动控制</span><span>${allowed(t)?"允许":"手动保持"}</span></div><div class="detail-line"><span>上次暂停</span><span>${timeText(t.paused_at,true)}</span></div><div class="detail-line"><span>上次续做</span><span>${timeText(t.resumed_at,true)}</span></div><div class="detail-line"><span>任务 ID</span><code>${escapeHTML(t.id)}</code></div>${t.reason || t.connection_error ? `<p class="detail-reason">${escapeHTML(t.reason || "暂时无法连接此聊天，管家将等待重连；其他任务继续检查。")}</p>`:""}`;
  $("#detailControl").textContent=allowed(t)?"保持此任务":"恢复自动控制";
  $("#detailControl").disabled=busy;
  $("#detailControl").disabled=busy || t.can_control === false;
}
function render() {
  if (!state) return;
  $("#navCount").textContent=state.tasks.length; $("#taskCount").textContent=state.tasks.length;
  $("#statTotal").textContent=state.tasks.length;
  $("#statActive").textContent=state.tasks.filter(t=>signal(t).kind==="active").length;
  $("#statWaiting").textContent=state.tasks.filter(t=>signal(t).kind==="waiting" || scheduled(t)).length;
  $("#statAttention").textContent=state.tasks.filter(t=>signal(t).kind==="attention").length;
  const status=$("#mainStatus"); status.className="status-pill"+(state.healthy ? state.control_paused?" paused":"" : " offline");
  status.lastElementChild.textContent=state.control_enabled ? "自动控制已启用" : !state.running ? "后台未运行" : !state.healthy ? "检查状态待恢复" : "自动控制已暂停";
  $("#globalControl").textContent=!state.running ? "启动后台服务" : state.control_paused ? "启用自动控制" : "暂停自动控制";
  $("#globalControl").disabled=busy;
  $("#freshness").textContent=ago(state.observed_at);
  $("#catalogHint").textContent=state.catalog?.local_error ? "本机目录待重连，显示已知聊天" : "Codex 目录随后台更新";
  $("#cloudCatalogNote").textContent=state.catalog?.cloud_observed_at ? `ChatGPT 近期目录快照 ${timeText(state.catalog.cloud_observed_at,true)} · 不自动执行` : "ChatGPT 本次仅显示目录";
  $("#serviceMeta").textContent=state.running ? `后台运行中 · 最近检查 ${timeText(state.observed_at)}` : "后台服务未运行";
  $("#connectionAlert").hidden=state.healthy;
  $("#connectionText").textContent=!state.running ? "后台服务未运行。启动后，管家会重新核对任务状态。" : "后台尚未提供有效的新检查结果，自动续做会等待可靠状态。";
  const p=state.policy;
  $("#policySummary").textContent=`剩余 ≤${p.pause}% 时暂停；恢复至 ≥${p.resume}% 后，再次复查原任务与使用许可。`;
  $("#ruleList").innerHTML=[["暂停阈值",`≤ ${p.pause}%`],["恢复阈值",`≥ ${p.resume}%`],["恢复连续确认",`至少 ${p.confirm_seconds} 秒`],["常规内部检查",`${state.poll_seconds} 秒`],["恢复提交", "一次发送，确认到达"],["账号与额度", "跟随当前登录账号"]].map(([label,value])=>`<div class="rule-row"><span>${label}</span><strong>${value}</strong></div>`).join("");
  renderTasks(); renderEvents(); renderDetail(); renderUsage();
}
async function refresh() {
  if (loading) return; loading=true;
  try {
    const response=await fetch("/api/state",{cache:"no-store"});
    if (!response.ok) throw new Error(response.status===401?"连接已更新，请重新连接控制界面。":"暂时无法连接本机界面服务。");
    state=await response.json();
    // Older UI processes cannot reload Python modules. Move their tabs to
    // the current server when they serve the new static application.
    if(!Object.hasOwn(state,"catalog") && ["8766","8768"].includes(location.port)){location.replace("http://127.0.0.1:8769/");return;}
    render();
  } catch (error) { $("#connectionAlert").hidden=false; $("#connectionText").textContent=error.message; $("#mainStatus").className="status-pill offline"; $("#mainStatus").lastElementChild.textContent="界面连接中断"; $("#globalControl").disabled=true; renderUsage(true); }
  finally { loading=false; }
}
async function action(payload) {
  if (busy) return; busy=true; render();
  try {
    const response=await fetch("/api/action",{method:"POST",headers:{"Content-Type":"application/json","X-Guardian-UI":"1"},body:JSON.stringify(payload)});
    const result=await response.json(); if (!response.ok) throw new Error(result.error || "操作未完成"); toast(result.message);
  } catch(error) { toast(error.message); }
  finally { busy=false; await refresh(); render(); }
}
function toggleTask(id) { const t=state?.tasks.find(t=>t.id===id); if (t) action({action:"set_auto",key:t.key,enabled:!allowed(t),revision:t.revision}); }
async function submitPlan(key,toggle) {const t=state?.tasks.find(t=>t.key===key);if(!t)return;const draft=planDrafts.get(key),enabled=toggle === "cancel"?false:toggle?!scheduled(t):true,prompt=enabled?(draft?.text ?? t.plan?.prompt ?? "继续任务"):(t.plan?.prompt || "继续任务");await action({action:"set_plan",key,enabled,prompt,revision:enabled?(draft?.revision ?? t.plan?.revision ?? 0):(t.plan?.revision ?? 0)});const current=state?.tasks.find(t=>t.key===key);if(current?.plan?.prompt===prompt.trim()){planDrafts.delete(key);renderTasks();}}
function executeNow(key) {
  const t=state?.tasks.find(t=>t.key===key);if(!t || t.can_control === false || immediatePending(t))return;
  const prompt=planDrafts.get(key)?.text ?? t.plan?.prompt ?? "继续任务";
  action({action:"execute_now",key,prompt,revision:t.revision,request_id:crypto.randomUUID()});
}
function openDetail(id) { selected=id; renderDetail(); $("#taskDialog").showModal(); }
document.querySelectorAll(".nav").forEach(el=>el.addEventListener("click",()=>setView(el.dataset.view)));
document.querySelectorAll(".filter").forEach(el=>el.addEventListener("click",()=>{filter=el.dataset.filter;pageNumber=1;document.querySelectorAll(".filter").forEach(b=>b.classList.toggle("active",b===el));renderTasks();}));
document.querySelectorAll(".engine-filter").forEach(el=>el.addEventListener("click",()=>{engine=el.dataset.engine;pageNumber=1;document.querySelectorAll(".engine-filter").forEach(b=>b.classList.toggle("active",b===el));renderTasks();}));
$("#previousPage").addEventListener("click",()=>{pageNumber=Math.max(1,pageNumber-1);renderTasks();});$("#nextPage").addEventListener("click",()=>{pageNumber++;renderTasks();});
$("#search").addEventListener("input",()=>{pageNumber=1;renderTasks();}); $("#eventSearch").addEventListener("input",renderEvents);
$("#refresh").addEventListener("click",refresh); $("#reconnect").addEventListener("click",()=>location.reload());
$("#allEvents").addEventListener("click",()=>setView("events")); $("#viewRules").addEventListener("click",()=>setView("rules"));
$("#globalControl").addEventListener("click",()=>state && action({action:!state.running?"start":state.control_paused?"enable":"pause",revision:state.control_revision}));
$("#closeDialog").addEventListener("click",()=>$("#taskDialog").close()); $("#detailControl").addEventListener("click",()=>toggleTask(selected));
$("#copyTask").addEventListener("click",async()=>{try{await navigator.clipboard.writeText(selected);toast("任务 ID 已复制");}catch{toast("复制失败，请在任务详情中手动选择 ID");}});
$("#copyAccountId").addEventListener("click",async()=>{const id=state?.usage?.account?.id;if(!id)return;try{await navigator.clipboard.writeText(id);toast("账号 ID 已复制");}catch{toast("复制失败，请手动选择下方账号 ID");}});
$("#accountAvatarImage").addEventListener("error",()=>{$("#accountAvatarImage").hidden=true;});
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
refresh(); setInterval(()=>{if(!document.hidden)refresh();},5000);
