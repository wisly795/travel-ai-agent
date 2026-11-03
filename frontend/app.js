const $ = (id) => document.getElementById(id);
const money = (value) => `NT$ ${Number(value).toLocaleString("zh-TW")}`;
let selectedPackage = null;
let conversationId = null;

const TABS = ["chat", "customer", "policy", "staff"];
const TOOL_LABELS = {
  list_destinations: "查目的地",
  search_packages: "查行程",
  list_hotels: "查飯店",
  calculate_quote: "計算報價",
  create_quote: "建立報價單",
  search_policy: "查規定",
  calculate_refund: "計算退費",
  request_human: "轉專人",
};
const SOURCE_LABELS = { web: "網頁", ai: "AI 客服", partner: "官網串接" };

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? "輸入資料有誤，請檢查後再試" : data.detail;
    throw new Error(detail || "系統發生錯誤");
  }
  return data;
}

function showMessage(text) {
  const message = $("message");
  message.textContent = text;
  message.hidden = !text;
}

function setTab(name) {
  TABS.forEach((tab) => {
    $(tab).hidden = tab !== name;
    $(`tab-${tab}`).classList.toggle("active", tab === name);
  });
  showMessage("");
}

function addText(parent, tag, text) {
  const element = document.createElement(tag);
  element.textContent = text;
  parent.append(element);
  return element;
}

// ---------- AI 客服 ----------

function addBubble(role, text) {
  const bubble = addText($("chat-log"), "div", text);
  bubble.className = `bubble ${role}`;
  bubble.scrollIntoView({ block: "nearest" });
  return bubble;
}

function newConversation() {
  conversationId = null;
  $("chat-log").replaceChildren();
  addBubble("ai", "您好，我是 AI 客服。可以告訴我想去哪裡、幾個人、每人預算，我幫您查行程和報價。");
  $("chat-examples").hidden = false;
}

async function sendChat(text) {
  const input = $("chat-input");
  const button = $("chat-form").querySelector("button");
  addBubble("user", text);
  $("chat-examples").hidden = true;
  input.value = "";
  input.disabled = button.disabled = true;
  const waiting = addBubble("ai waiting", "查詢中…");

  try {
    const data = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, message: text }),
    });
    conversationId = data.conversation_id;
    waiting.className = "bubble ai";
    waiting.textContent = data.reply;
    if (data.tools_used.length) {
      const labels = [...new Set(data.tools_used.map((name) => TOOL_LABELS[name] || name))];
      addText(waiting, "small", `使用工具：${labels.join("、")}`);
    }
  } catch (error) {
    waiting.className = "bubble error";
    waiting.textContent = error.message;
  } finally {
    input.disabled = button.disabled = false;
    input.focus();
    waiting.scrollIntoView({ block: "nearest" });
  }
}

async function loadChatStatus() {
  const status = await api("/api/chat/status");
  $("chat-status").textContent = status.enabled
    ? `由 Claude（${status.model}）回答，價格一律由系統計算。`
    : "AI 客服尚未啟用（還沒設定 API 金鑰），可以先用「查行程」。";
  return status.enabled;
}

// ---------- 查行程 ----------

async function loadDestinations() {
  const destinations = await api("/api/destinations");
  const select = $("destination");
  select.replaceChildren(new Option("全部", ""));
  destinations.forEach((name) => select.add(new Option(name, name)));
}

async function searchPackages(event) {
  event.preventDefault();
  showMessage("");
  $("quote-form").hidden = true;
  $("result").hidden = true;

  const params = new URLSearchParams({ people: $("people").value });
  if ($("destination").value) params.set("destination", $("destination").value);
  if ($("max-price").value) params.set("max_price", $("max-price").value);

  try {
    const packages = await api(`/api/packages?${params}`);
    const list = $("packages");
    list.replaceChildren();
    if (!packages.length) {
      addText(list, "p", "沒有符合條件的行程，請調整預算或人數。");
      return;
    }
    packages.forEach((item) => {
      const card = addText(list, "article", "");
      card.className = "card";
      addText(card, "h3", item.name);
      addText(card, "p", `${item.destination}｜${item.days} 天｜剩 ${item.seats_left} 位`);
      addText(card, "p", item.description);
      addText(card, "strong", `${money(item.price_per_person)} / 人`);
      const button = addText(card, "button", "選擇");
      button.type = "button";
      button.addEventListener("click", () => choosePackage(item));
    });
  } catch (error) {
    showMessage(error.message);
  }
}

async function choosePackage(item) {
  selectedPackage = item;
  $("selected-package").textContent = item.name;
  try {
    const hotels = await api(`/api/hotels?destination=${encodeURIComponent(item.destination)}`);
    const select = $("hotel");
    select.replaceChildren();
    hotels.forEach((hotel) => {
      const label = `${hotel.name}（${hotel.room_type}，每晚 ${money(hotel.price_per_night)}）`;
      select.add(new Option(label, hotel.id));
    });
    // 出發日期只能選明天到一年內（後端也會再檢查一次）
    const day = 24 * 60 * 60 * 1000;
    const iso = (offset) => new Date(Date.now() + offset).toLocaleDateString("sv-SE", { timeZone: "Asia/Taipei" });
    $("departure-date").min = iso(day);
    $("departure-date").max = iso(365 * day);
    $("quote-form").hidden = false;
    $("quote-form").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    showMessage(error.message);
  }
}

async function createQuote(event) {
  event.preventDefault();
  showMessage("");
  try {
    const quote = await api("/api/quotes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_name: $("customer-name").value,
        package_id: selectedPackage.id,
        hotel_id: Number($("hotel").value),
        people: Number($("people").value),
        departure_date: $("departure-date").value,
      }),
    });
    const result = $("result");
    result.replaceChildren();
    addText(result, "h2", `報價單 #${quote.id}`);
    addText(result, "p", `${quote.customer_name}｜${quote.package}｜${quote.hotel}`);
    addText(result, "p", `${quote.people} 人，${quote.rooms} 間房，${quote.nights} 晚`);
    if (quote.departure_date) addText(result, "p", `出發 ${quote.departure_date}，回程 ${quote.return_date}`);
    addText(result, "strong", `總價 ${money(quote.total_price)}`);
    addText(result, "p", "模擬資料，非真實報價");
    result.hidden = false;
  } catch (error) {
    showMessage(error.message);
  }
}

// ---------- 旅遊規定 ----------

async function loadPolicies() {
  const docs = await api("/api/policies");
  const list = $("policy-list");
  list.replaceChildren();
  docs.forEach((doc) => {
    const panel = addText(list, "details", "");
    panel.className = "panel";
    addText(panel, "summary", `${doc.doc}（${doc.articles.length} 條）`);
    doc.articles.forEach((item) => {
      addText(panel, "h3", `${item.article} ${item.title}`);
      addText(panel, "p", item.content).className = "policy-text";
    });
  });
}

async function searchPolicies(event) {
  event.preventDefault();
  const box = $("policy-results");
  box.replaceChildren();
  try {
    const results = await api(`/api/policies/search?q=${encodeURIComponent($("policy-input").value)}`);
    if (!results.length) {
      addText(box, "p", "規定文件中找不到相關內容。");
      return;
    }
    results.forEach((item) => {
      const card = addText(box, "div", "");
      card.className = "policy-hit";
      addText(card, "strong", item.source);
      addText(card, "small", `相似度 ${item.score}`);
      addText(card, "p", item.content).className = "policy-text";
    });
  } catch (error) {
    addText(box, "p", error.message).className = "message";
  }
}

// ---------- 業務後台 ----------

// 登入後拿到的工作階段，關掉分頁就失效；瀏覽器不允許儲存時就只放在記憶體
let session = null;
const SESSION_KEY = "travel-session";
try { session = JSON.parse(sessionStorage.getItem(SESSION_KEY)); } catch { session = null; }

function saveSession(value) {
  session = value;
  try {
    if (value) sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch { /* 無法儲存時只放在記憶體 */ }
}

function authHeaders() {
  return session ? { Authorization: `Bearer ${session.token}` } : {};
}

async function staffApi(path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  try {
    return await api(path, { ...options, headers });
  } catch (error) {
    if (/請先登入|登入已過期/.test(error.message)) showLoggedOut();
    throw error;
  }
}

function showLoggedOut() {
  saveSession(null);
  $("staff-result").hidden = true;
  $("staff-form").hidden = false;
}

function addButton(cell, label, onClick, className = "small-btn") {
  const button = addText(cell, "button", label);
  button.type = "button";
  button.className = className;
  button.addEventListener("click", onClick);
  return button;
}

// 固定用台灣時間顯示，不受使用者電腦或伺服器時區影響
const timeText = (value) => new Date(value).toLocaleString("zh-TW", { hour12: false, timeZone: "Asia/Taipei" });

async function staffAction(work) {
  showMessage("");
  try {
    await work();
    await refreshStaff();
  } catch (error) {
    showMessage(error.message);
  }
}

async function loadUsage() {
  const usage = await staffApi("/api/admin/usage");
  const box = $("usage");
  box.replaceChildren();
  [["今日 AI 對話", `${usage.turns} / ${usage.turn_limit} 次`],
    ["今日 AI 花費", `US$ ${Number(usage.cost_usd).toFixed(4)} / ${usage.cost_limit_usd}`]]
    .forEach(([label, value]) => {
      const card = addText(box, "div", "");
      card.className = "stat";
      addText(card, "small", label);
      addText(card, "strong", value);
    });
}

async function loadQuoteTable() {
  const quotes = await staffApi("/api/quotes");
  const rows = $("quote-rows");
  rows.replaceChildren();
  quotes.forEach((quote) => {
    const row = rows.insertRow();
    const erpText = quote.erp_status ? `${quote.erp_status}${quote.erp_order_no ? `（${quote.erp_order_no}）` : ""}` : "—";
    [quote.id, quote.customer_name, quote.package, quote.hotel, quote.people, quote.departure_date || "—",
      money(quote.total_price), SOURCE_LABELS[quote.source] || quote.source, quote.status, erpText]
      .forEach((value) => { row.insertCell().textContent = value; });
    const actions = row.insertCell();
    const setStatus = (status) => staffAction(() => staffApi(`/api/quotes/${quote.id}/status`, {
      method: "PATCH", body: JSON.stringify({ status }),
    }));
    if (quote.status === "已報價") addButton(actions, "成交", () => setStatus("成交"));
    if (quote.status !== "取消") addButton(actions, "取消", () => setStatus("取消"), "small-btn ghost");
  });
}

async function loadTurns() {
  const turns = await staffApi("/api/admin/turns");
  const list = $("turn-list");
  list.replaceChildren();
  if (!turns.length) addText(list, "p", "還沒有 AI 對話。");
  turns.forEach((turn) => {
    const item = addText(list, "details", "");
    item.className = "turn";
    const tools = turn.tools.map((t) => TOOL_LABELS[t.tool] || t.tool);
    addText(item, "summary",
      `#${turn.id}　${timeText(turn.created_at)}　客人：${turn.user_message}`);
    addText(item, "p", `AI：${turn.reply}`).className = "policy-text";
    addText(item, "small",
      `工具：${tools.join("、") || "無"}｜模型 ${turn.model}｜US$ ${Number(turn.cost_usd).toFixed(5)}`);
    turn.tools.forEach((t) => {
      const detail = addText(item, "pre", `${t.is_error ? "⚠ " : ""}${t.tool}\n輸入：${JSON.stringify(t.input)}\n結果：${JSON.stringify(t.output).slice(0, 600)}`);
      detail.className = "tool-log";
    });
  });
}

async function loadHandoffs() {
  const items = await staffApi("/api/handoffs");
  const rows = $("handoff-rows");
  rows.replaceChildren();
  items.forEach((item) => {
    const row = rows.insertRow();
    [item.id, item.reason, timeText(item.created_at), item.status]
      .forEach((value) => { row.insertCell().textContent = value; });
    const next = item.status === "待處理" ? "已處理" : "待處理";
    addButton(row.insertCell(), `標為${next}`, () => staffAction(() => staffApi(`/api/handoffs/${item.id}`, {
      method: "PATCH", body: JSON.stringify({ status: next }),
    })));
  });
}

async function loadErp() {
  const [health, syncs] = await Promise.all([staffApi("/api/erp/status"), staffApi("/api/erp/syncs")]);
  $("erp-health").textContent = health.status !== "ok" ? "ERP 連線：無法連線"
    : `ERP 連線：${health.fail_mode ? "維修中（模擬故障）" : "正常"}`;
  const rows = $("erp-rows");
  rows.replaceChildren();
  syncs.forEach((sync) => {
    const row = rows.insertRow();
    [`#${sync.quote_id}`, sync.customer_name, money(sync.total_price), sync.status,
      sync.erp_order_no || "—", sync.attempts, sync.last_error || ""]
      .forEach((value) => { row.insertCell().textContent = value; });
    const actions = row.insertCell();
    if (sync.status === "失敗") {
      addButton(actions, "重送", () => staffAction(() => staffApi(`/api/erp/syncs/${sync.quote_id}/retry`, { method: "POST" })));
    }
  });
}

async function decide(po, approve) {
  let reason = "";
  if (!approve) {
    reason = window.prompt("退回原因（必填）") || "";
    if (!reason.trim()) return;
  }
  if (po.approver_role === "主管" && session.user.role !== "主管") {
    showMessage("這張採購單需要主管核准或退回，請用主管帳號登入");
    return;
  }
  await staffAction(() => staffApi(`/api/purchase-orders/${po.po_id}/decision`, {
    method: "POST", body: JSON.stringify({ approve, reason }),
  }));
}

async function loadProcurement() {
  const items = await staffApi("/api/procurement");
  const list = $("procurement-list");
  list.replaceChildren();
  if (!items.length) addText(list, "p", "還沒有請購單。把報價改成「成交」就會產生。");
  items.forEach((item) => {
    const card = addText(list, "article", "");
    card.className = "pr-card";
    addText(card, "h3", `請購單 #${item.id}｜報價 #${item.quote_id} ${item.customer_name}｜${item.status}`);
    addText(card, "p", `${item.hotel}：${item.rooms} 間 × ${item.nights} 晚，住宿預算 ${money(item.budget)}`
      + `｜出發日 ${item.departure_date || "未填"}`);
    if (item.ai_analysis) addText(card, "p", `AI 比價：${item.ai_analysis}`).className = "policy-text ai-note";
    if (item.po_id) {
      const po = addText(card, "div", "");
      po.className = "po-box";
      addText(po, "strong", `採購單 #${item.po_id}：${item.supplier} ${money(item.amount)}｜${item.po_status}`);
      addText(po, "small", `${item.over_budget ? "超出預算，" : ""}需要${item.approver_role}核准`
        + (item.decided_by ? `｜處理人：${item.decided_by}` : "")
        + (item.confirmation_no ? `｜供應商確認編號 ${item.confirmation_no}` : "")
        + (item.reject_reason ? `｜退回原因：${item.reject_reason}` : "")
        + (item.last_error ? `｜錯誤：${item.last_error}` : ""));
      if (item.po_status === "待核准") {
        addButton(po, "核准並下單", () => decide(item, true));
        addButton(po, "退回", () => decide(item, false), "small-btn ghost");
      }
      if (item.po_status === "下單失敗") {
        addButton(po, "重送", () => staffAction(() => staffApi(`/api/purchase-orders/${item.po_id}/retry`, { method: "POST" })));
      }
    }
    if (item.status === "待比價") {
      const button = addButton(card, "AI 比價", async () => {
        button.disabled = true;
        button.textContent = "AI 比價中…";
        await staffAction(() => staffApi(`/api/procurement/${item.id}/analyze`, { method: "POST" }));
      });
    }
  });
}

async function loadNotifications() {
  const items = await staffApi("/api/notifications");
  const unread = items.filter((item) => !item.is_read).length;
  $("unread").textContent = unread ? `(${unread})` : "";
  const list = $("notification-list");
  list.replaceChildren();
  if (!items.length) addText(list, "p", "目前沒有通知。");
  items.forEach((item) => {
    const card = addText(list, "div", "");
    card.className = `notice${item.is_read ? "" : " unread"}`;
    addText(card, "small", `${item.kind}｜${timeText(item.created_at)}`);
    addText(card, "strong", item.title);
    addText(card, "p", item.body).className = "policy-text";
    if (!item.is_read) {
      addButton(card, "已讀", () => staffAction(() => staffApi("/api/notifications/read", {
        method: "POST", body: JSON.stringify({ id: item.id }),
      })), "small-btn ghost");
    }
  });
}

async function loadUsers() {
  const [users, events] = await Promise.all([staffApi("/api/admin/users"), staffApi("/api/admin/login-events")]);
  const rows = $("user-rows");
  rows.replaceChildren();
  users.forEach((user) => {
    const row = rows.insertRow();
    const state = !user.is_active ? "已停用" : user.locked ? "鎖定中" : "正常";
    [user.username, user.display_name, user.role, state, user.last_login_at ? timeText(user.last_login_at) : "—"]
      .forEach((value) => { row.insertCell().textContent = value; });
    const actions = row.insertCell();
    if (user.username === session.user.username) return;
    addButton(actions, user.is_active ? "停用" : "啟用", () => staffAction(() => staffApi(`/api/admin/users/${user.id}`, {
      method: "PATCH", body: JSON.stringify({ is_active: !user.is_active }),
    })), user.is_active ? "small-btn ghost" : "small-btn");
    addButton(actions, "重設密碼", () => {
      const password = window.prompt(`輸入 ${user.username} 的新密碼（至少 8 碼，英文加數字）`) || "";
      if (!password) return;
      staffAction(() => staffApi(`/api/admin/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ password }) }));
    });
  });
  const logRows = $("login-rows");
  logRows.replaceChildren();
  events.forEach((event) => {
    const row = logRows.insertRow();
    [timeText(event.created_at), event.username, event.success ? "成功" : "失敗", event.reason]
      .forEach((value) => { row.insertCell().textContent = value; });
  });
}

let evalTimer = null;

async function loadEvals() {
  const data = await staffApi("/api/admin/evals");
  const button = $("eval-run");
  button.hidden = session.user.role !== "管理員";
  button.disabled = data.running;
  button.textContent = data.running ? "評測執行中…" : "執行評測（約 2 分鐘）";
  const summary = $("eval-summary");
  summary.replaceChildren();
  const rows = $("eval-rows");
  rows.replaceChildren();
  if (data.latest) {
    const latest = data.latest;
    [["總分", `${latest.passed} / ${latest.total}`, `${Math.round((latest.passed / latest.total) * 100)}%｜${latest.model}`],
      ...latest.by_category.map((c) => [c.category, `${c.passed} / ${c.total}`, ""])]
      .forEach(([label, value, note]) => {
        const card = addText(summary, "div", "");
        card.className = "stat";
        addText(card, "small", label);
        addText(card, "strong", value);
        if (note) addText(card, "span", note).className = "stat-note";
      });
    latest.results.forEach((r) => {
      const row = rows.insertRow();
      // 不用表情符號：有些電腦沒有表情字型會顯示成方框
      [r.case_id, r.category, r.question, r.passed ? "通過" : "未通過", r.failures.join("；")]
        .forEach((value) => { row.insertCell().textContent = value; });
      row.cells[3].className = r.passed ? "pass" : "fail";
      row.title = `AI 回答：${r.reply}`;
    });
  } else {
    addText(summary, "p", "還沒有評測紀錄。");
  }
  const history = $("eval-history");
  history.replaceChildren();
  data.history.forEach((h) => {
    const row = history.insertRow();
    [timeText(h.started_at), h.label, h.model, h.status === "完成" ? `${h.passed} / ${h.total}` : h.status, `US$ ${h.cost_usd.toFixed(4)}`]
      .forEach((value) => { row.insertCell().textContent = value; });
  });
  // 執行中每 10 秒更新一次，跑完自動停止
  clearTimeout(evalTimer);
  if (data.running) evalTimer = setTimeout(() => loadEvals().catch(() => {}), 10000);
}

async function runEval() {
  await staffAction(() => staffApi("/api/admin/evals/run", { method: "POST" }));
}

async function loadPartners() {
  const data = await staffApi("/api/admin/partners");
  const rows = $("partner-rows");
  rows.replaceChildren();
  data.partners.forEach((p) => {
    const row = rows.insertRow();
    [p.name, `${p.key_prefix}…`, p.rate_limit_per_minute, p.calls_24h, p.limited_24h, p.quotes, p.is_active ? "啟用" : "停用"]
      .forEach((value) => { row.insertCell().textContent = value; });
    addButton(row.insertCell(), p.is_active ? "停用" : "啟用", () => staffAction(() => staffApi(`/api/admin/partners/${p.id}`, {
      method: "PATCH", body: JSON.stringify({ is_active: !p.is_active }),
    })), p.is_active ? "small-btn ghost" : "small-btn");
  });
  const calls = $("partner-calls");
  calls.replaceChildren();
  data.recent_calls.forEach((c) => {
    const row = calls.insertRow();
    [timeText(c.created_at), c.name, `${c.method} ${c.path}`, c.status].forEach((v) => { row.insertCell().textContent = v; });
  });
}

async function createPartner(event) {
  event.preventDefault();
  const box = $("partner-key");
  await staffAction(async () => {
    const created = await staffApi("/api/admin/partners", {
      method: "POST",
      body: JSON.stringify({ name: $("partner-name").value, rate_limit_per_minute: Number($("partner-limit").value) }),
    });
    box.replaceChildren();
    addText(box, "strong", `「${created.name}」的 API 金鑰（只顯示這一次，請立即交給對方並妥善保存）：`);
    addText(addText(box, "p", ""), "code", created.api_key);
    box.hidden = false;
    $("partner-form").reset();
  });
}

async function createUser(event) {
  event.preventDefault();
  await staffAction(async () => {
    await staffApi("/api/admin/users", {
      method: "POST",
      body: JSON.stringify({
        username: $("new-username").value, display_name: $("new-display").value,
        role: $("new-role").value, password: $("new-password").value,
      }),
    });
    $("user-form").reset();
  });
}

async function loadDashboard() {
  const data = await staffApi("/api/admin/dashboard?days=14");
  const s = data.summary;
  const kpis = $("kpis");
  kpis.replaceChildren();
  [
    ["近 30 天報價", `${s.quotes} 張`, `AI 客服 ${s.ai_quotes} 張`],
    ["成交", `${s.deals} 張`, `成交率 ${(s.conversion_rate * 100).toFixed(0)}%`],
    ["成交金額", money(s.deal_amount), "近 30 天"],
    ["AI 花費", `US$ ${s.ai_cost_usd.toFixed(2)}`, `${s.ai_turns} 次對話`],
    ["待處理", `${s.pending_approvals + s.erp_failed + s.open_handoffs} 件`,
      `待核准 ${s.pending_approvals}｜ERP 失敗 ${s.erp_failed}｜轉接 ${s.open_handoffs}`],
    ["AI 評測", data.eval ? `${data.eval.passed} / ${data.eval.total} 題` : "尚未執行",
      data.eval ? `${Math.round((data.eval.passed / data.eval.total) * 100)}%｜${timeText(data.eval.finished_at)}` : "到「AI 評測」分頁執行"],
  ].forEach(([label, value, note]) => {
    const card = addText(kpis, "div", "");
    card.className = "stat";
    addText(card, "small", label);
    addText(card, "strong", value);
    addText(card, "span", note).className = "stat-note";
  });
  const day = (row) => row.day.slice(5).replace("-", "/");
  Charts.columns($("chart-deals"), data.daily, { value: (r) => r.deal_amount, label: day, format: money, tipLabel: "成交金額" });
  Charts.columns($("chart-quotes"), data.daily, { value: (r) => r.quotes, label: day, format: (v) => `${v} 張`, tipLabel: "報價數" });
  Charts.bars($("chart-packages"), data.top_packages, { name: (r) => r.name, value: (r) => r.quotes, format: (v) => `${v} 張`, unit: "報價數" });
  const bySource = Object.fromEntries(data.sources.map((r) => [r.source, r.quotes]));
  Charts.share($("chart-sources"), [{ name: "網頁", value: bySource.web || 0 }, { name: "AI 客服", value: bySource.ai || 0 },
    { name: "官網串接", value: bySource.partner || 0 }]);
  Charts.columns($("chart-ai"), data.daily, { value: (r) => r.ai_cost_usd, label: day, format: (v) => `US$ ${v.toFixed(4)}`, tipLabel: "AI 花費" });
}

async function refreshStaff() {
  const isAdmin = session.user.role === "管理員";
  $("subtab-users").hidden = !isAdmin;
  $("whoami").textContent = `目前登入：${session.user.display_name}（${session.user.role}）`;
  await Promise.all([loadUsage(), loadDashboard(), loadEvals(), loadQuoteTable(), loadTurns(), loadHandoffs(), loadErp(), loadProcurement(),
    loadNotifications(), ...(isAdmin ? [loadUsers(), loadPartners()] : [])]);
}

async function showStaff() {
  try {
    await refreshStaff();
    $("staff-form").hidden = true;
    $("staff-result").hidden = false;
  } catch (error) {
    showMessage(error.message);
  }
}

async function loadQuotes(event) {
  event.preventDefault();
  showMessage("");
  try {
    const result = await api("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: $("login-username").value, password: $("login-password").value }),
    });
    saveSession(result);
    $("login-password").value = "";
    await showStaff();
  } catch (error) {
    showMessage(error.message);
  }
}

async function logout() {
  await api("/api/auth/logout", { method: "POST", headers: authHeaders() }).catch(() => {});
  showLoggedOut();
  showMessage("");
}

function setView(viewId) {
  document.querySelectorAll(".view").forEach((view) => { view.hidden = view.id !== viewId; });
  document.querySelectorAll(".subtab").forEach((tab) => tab.classList.toggle("active", tab.dataset.view === viewId));
}

async function exportCsv() {
  showMessage("");
  const response = await fetch("/api/quotes/export.csv", { headers: authHeaders() });
  if (!response.ok) {
    showMessage("下載失敗，請重新登入");
    return;
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = "quotes.csv";
  link.click();
  URL.revokeObjectURL(url);
}

TABS.forEach((tab) => $(`tab-${tab}`).addEventListener("click", () => setTab(tab)));
$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("chat-input").value.trim();
  if (text) sendChat(text);
});
$("chat-examples").addEventListener("click", (event) => {
  if (event.target.matches(".chip")) sendChat(event.target.textContent);
});
$("chat-new").addEventListener("click", newConversation);
$("search-form").addEventListener("submit", searchPackages);
$("policy-form").addEventListener("submit", searchPolicies);
$("quote-form").addEventListener("submit", createQuote);
$("staff-form").addEventListener("submit", loadQuotes);
$("export").addEventListener("click", exportCsv);
$("logout").addEventListener("click", logout);
$("user-form").addEventListener("submit", createUser);
$("partner-form").addEventListener("submit", createPartner);
$("eval-run").addEventListener("click", runEval);
if (session) showStaff();
document.querySelectorAll(".subtab").forEach((tab) => tab.addEventListener("click", () => setView(tab.dataset.view)));
$("read-all").addEventListener("click", () => staffAction(() => staffApi("/api/notifications/read", {
  method: "POST", body: JSON.stringify({}),
})));
$("erp-retry-all").addEventListener("click", () => staffAction(() => staffApi("/api/erp/retry-failed", { method: "POST" })));
$("erp-fail-on").addEventListener("click", () => staffAction(() => staffApi("/api/erp/fail-mode", {
  method: "POST", body: JSON.stringify({ on: true }),
})));
$("erp-fail-off").addEventListener("click", () => staffAction(() => staffApi("/api/erp/fail-mode", {
  method: "POST", body: JSON.stringify({ on: false }),
})));

newConversation();
loadDestinations().catch((error) => showMessage(error.message));
loadPolicies().catch((error) => showMessage(error.message));
loadChatStatus()
  .then((enabled) => setTab(enabled ? "chat" : "customer"))
  .catch(() => setTab("customer"));
