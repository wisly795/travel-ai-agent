// 前端元件測試（不需要後端）：用假的 fetch 回應，檢查畫面邏輯
import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { compact, niceMax, Columns, Share } from "./charts/Charts.jsx";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import Chat from "./Chat.jsx";
import TourDetail from "./site/TourDetail.jsx";
import Tours from "./site/Tours.jsx";

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

const TOUR = { id: 1, name: "海島放鬆 4 日", destination: "沖繩", days: 4, seats_left: 18, description: "水族館", price_per_person: 22000 };

describe("精選行程", () => {
  it("依網址上的條件查詢，顯示行程卡片與連結", async () => {
    let asked = "";
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      if (String(url).startsWith("/api/packages")) asked = String(url);
      return { ok: true, json: async () => (String(url).startsWith("/api/packages") ? [TOUR] : ["沖繩"]) };
    });
    const { container } = render(
      <MemoryRouter initialEntries={["/tours?destination=沖繩&people=4"]}><Routes><Route path="/tours" element={<Tours />} /></Routes></MemoryRouter>,
    );
    await screen.findByText("海島放鬆 4 日");
    expect(decodeURIComponent(asked)).toContain("destination=沖繩");
    expect(asked).toContain("people=4");
    expect(container.querySelector("a.s-card").getAttribute("href")).toBe("/tours/1");
    expect(screen.getByText("日本・沖繩")).toBeTruthy();
  });
});

describe("行程詳細頁", () => {
  it("選飯店、改人數就重新試算，價格來自後端", async () => {
    const previews = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url, options) => {
      const path = String(url);
      if (path.startsWith("/api/quotes/preview")) {
        const body = JSON.parse(options.body);
        previews.push(body);
        return { ok: true, json: async () => ({ people: body.people, rooms: 1, nights: 3, package_fee: 22000 * body.people,
          hotel_fee: 9600, total_price: 22000 * body.people + 9600 }) };
      }
      const data = path.startsWith("/api/packages") ? [TOUR]
        : path.startsWith("/api/hotels") ? [{ id: 1, name: "海風飯店", room_type: "雙人房", price_per_night: 3200 }]
          : path.startsWith("/api/supplier-prices") ? { hotels: [] } : {};
      return { ok: true, json: async () => data };
    });
    render(
      <MemoryRouter initialEntries={["/tours/1"]}>
        <Routes><Route element={<Outlet context={{ openChat: () => {} }} />}><Route path="/tours/:id" element={<TourDetail />} /></Route></Routes>
      </MemoryRouter>,
    );
    await screen.findByText("NT$ 53,600");
    fireEvent.change(screen.getByLabelText("人數"), { target: { value: "1" } });
    await screen.findByText("NT$ 31,600");
    expect(previews.at(-1)).toMatchObject({ package_id: 1, hotel_id: 1, people: 1 });
  });
});
