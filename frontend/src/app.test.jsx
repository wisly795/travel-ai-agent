// 前端元件測試（不需要後端）：用假的 fetch 回應，檢查畫面邏輯
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { compact, niceMax, Columns, Share } from "./charts/Charts.jsx";
import Chat from "./Chat.jsx";
import Customer from "./Customer.jsx";

// 測試環境（jsdom）沒有「捲動到元素」，補一個空的版本
Element.prototype.scrollIntoView = () => {};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

function mockFetch(routes) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const key = Object.keys(routes).find((path) => String(url).startsWith(path));
    const body = typeof routes[key] === "function" ? routes[key](url) : routes[key];
    return { ok: true, json: async () => body };
  });
}

describe("圖表工具", () => {
  it("刻度最大值往上取整", () => {
    expect(niceMax(0)).toBe(1);
    expect(niceMax(87)).toBe(90);
    expect(niceMax(1234)).toBe(2000);
  });
  it("大數字縮寫", () => {
    expect(compact(1500)).toBe("1.5K");
    expect(compact(2000000)).toBe("2M");
    expect(compact(12)).toBe("12");
  });
  it("直條圖每天一根，並附數據表格", () => {
    const rows = [{ d: "11/01", v: 3 }, { d: "11/02", v: 0 }, { d: "11/03", v: 5 }];
    const { container } = render(<Columns rows={rows} value={(r) => r.v} label={(r) => r.d} format={(v) => `${v} 張`} tipLabel="報價數" />);
    expect(container.querySelectorAll("path.bar")).toHaveLength(2); // 0 不畫柱子
    expect(container.querySelectorAll(".chart-table tbody tr")).toHaveLength(3);
  });
  it("比例條有圖例與百分比", () => {
    render(<Share parts={[{ name: "網頁", value: 3 }, { name: "AI 客服", value: 1 }]} />);
    expect(screen.getAllByText("網頁 3（75%）").length).toBeGreaterThan(0);
  });
});

describe("AI 客服", () => {
  it("多 Agent 模式送出 mode=multi，並顯示經過的 Agent 與工具", async () => {
    let sent = null;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      sent = JSON.parse(options.body);
      return { ok: true, json: async () => ({
        conversation_id: "c1", reply: "總價 NT$ 107,200",
        agents: [{ agent: "分流" }, { agent: "報價專員" }, { agent: "檢查員" }], tools_used: ["calculate_quote"],
      }) };
    });
    render(<Chat hidden={false} status={{ enabled: true, model: "claude-haiku-5-5" }} />);
    fireEvent.click(screen.getByLabelText(/多 Agent 協作/));
    fireEvent.change(screen.getByLabelText("輸入問題"), { target: { value: "4 人去沖繩多少錢" } });
    fireEvent.click(screen.getByText("送出"));
    await screen.findByText("總價 NT$ 107,200");
    expect(sent).toMatchObject({ message: "4 人去沖繩多少錢", mode: "multi", conversation_id: null });
    expect(screen.getByText("經過：分流 → 報價專員 → 檢查員")).toBeTruthy();
    expect(screen.getByText("使用工具：計算報價")).toBeTruthy();
  });

  it("錯誤訊息顯示在對話裡", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({ ok: false, json: async () => ({ detail: "今天的 AI 客服使用量已達上限" }) });
    render(<Chat hidden={false} status={{ enabled: true, model: "m" }} />);
    fireEvent.click(screen.getByText("京都有哪些行程？"));
    expect((await screen.findByText("今天的 AI 客服使用量已達上限")).className).toContain("error");
  });
});

describe("查行程", () => {
  it("查詢後顯示行程卡片，選擇後出現報價表單", async () => {
    mockFetch({
      "/api/destinations": ["沖繩"],
      "/api/packages": [{ id: 1, name: "海島放鬆 4 日", destination: "沖繩", days: 4, seats_left: 18, description: "水族館", price_per_person: 22000 }],
      "/api/hotels": [{ id: 1, name: "海風飯店", room_type: "雙人房", price_per_night: 3200 }],
    });
    const { container } = render(<Customer hidden={false} onError={() => {}} />);
    fireEvent.click(screen.getByText("查詢"));
    await screen.findByText("海島放鬆 4 日");
    expect(screen.getByText("NT$ 22,000 / 人")).toBeTruthy();
    expect(container.querySelector("#quote-form").hidden).toBe(true);
    fireEvent.click(screen.getByText("選擇"));
    await waitFor(() => expect(container.querySelector("#quote-form").hidden).toBe(false));
    expect(screen.getByText("海風飯店（雙人房，每晚 NT$ 3,200）")).toBeTruthy();
  });
});
