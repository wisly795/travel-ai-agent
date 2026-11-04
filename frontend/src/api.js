// 呼叫後端 API 與共用的格式化工具

export const money = (value) => `NT$ ${Number(value).toLocaleString("zh-TW")}`;

// 固定用台灣時間顯示，不受使用者電腦或伺服器時區影響
export const timeText = (value) => new Date(value).toLocaleString("zh-TW", { hour12: false, timeZone: "Asia/Taipei" });

export const TOOL_LABELS = {
  list_destinations: "查目的地",
  search_packages: "查行程",
  list_hotels: "查飯店",
  calculate_quote: "計算報價",
  create_quote: "建立報價單",
  search_policy: "查規定",
  calculate_refund: "計算退費",
  request_human: "轉專人",
  search_local_info: "查景點／住宿",
};

export const SOURCE_LABELS = { web: "網頁", ai: "AI 客服", partner: "官網串接" };

export async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = Array.isArray(data.detail) ? "輸入資料有誤，請檢查後再試" : data.detail;
    throw new Error(detail || "系統發生錯誤");
  }
  return data;
}

export function postJson(path, body, headers = {}) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) });
}

// 登入後拿到的工作階段，關掉分頁就失效；瀏覽器不允許儲存時就只放在記憶體
const SESSION_KEY = "travel-session";

export function loadSession() {
  try {
    return JSON.parse(sessionStorage.getItem(SESSION_KEY));
  } catch {
    return null;
  }
}

export function storeSession(value) {
  try {
    if (value) sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch { /* 無法儲存時只放在記憶體 */ }
}

// 呼叫要登入的 API；登入過期時呼叫 onExpired（回到登入畫面）
export function makeStaffApi(session, onExpired) {
  return async (path, options = {}) => {
    const headers = { Authorization: `Bearer ${session.token}`, ...(options.headers || {}) };
    if (options.body) headers["Content-Type"] = "application/json";
    try {
      return await api(path, { ...options, headers });
    } catch (error) {
      if (/請先登入|登入已過期/.test(error.message)) onExpired();
      throw error;
    }
  };
}
