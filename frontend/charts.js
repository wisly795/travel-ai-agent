// 儀表板的小型圖表：純 SVG／HTML，不依賴外部套件（安裝版離線也能顯示）。
// 規格：柱子最寬 24px、頂端 4px 圓角、細格線、文字用文字色（不用資料色）、滑過顯示提示、每張圖附數據表格。

const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  let tip = null;

  function svg(tag, attrs = {}, parent = null) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (parent) parent.append(node);
    return node;
  }

  function tooltip() {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "chart-tip";
      tip.hidden = true;
      document.body.append(tip);
    }
    return tip;
  }

  function bindTip(target, text) {
    target.addEventListener("pointermove", (event) => {
      const box = tooltip();
      box.textContent = text;
      box.hidden = false;
      box.style.left = `${Math.min(event.clientX + 12, window.innerWidth - box.offsetWidth - 8)}px`;
      box.style.top = `${event.clientY - 36}px`;
    });
    target.addEventListener("pointerleave", () => { tooltip().hidden = true; });
  }

  // 刻度取整數：0、一半、最大值往上取整
  function niceMax(value) {
    if (value <= 0) return 1;
    const power = 10 ** Math.floor(Math.log10(value));
    return Math.ceil(value / power) * power;
  }

  function compact(value) {
    if (value >= 1e6) return `${(value / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(1).replace(/\.0$/, "")}K`;
    return String(Math.round(value * 100) / 100);
  }

  function table(container, headers, rows) {
    const details = document.createElement("details");
    details.className = "chart-table";
    const summary = document.createElement("summary");
    summary.textContent = "看數據表格";
    details.append(summary);
    const t = document.createElement("table");
    const head = t.createTHead().insertRow();
    headers.forEach((h) => { const th = document.createElement("th"); th.textContent = h; head.append(th); });
    const body = t.createTBody();
    rows.forEach((r) => { const tr = body.insertRow(); r.forEach((v) => { tr.insertCell().textContent = v; }); });
    details.append(t);
    container.append(details);
  }

  // 直條圖：每天一根，單一數列（標題說明數列，不需要圖例）
  function columns(container, rows, { value, label, format, tipLabel }) {
    container.replaceChildren();
    const width = 640, height = 220, left = 44, right = 12, top = 16, bottom = 28;
    let max = niceMax(Math.max(...rows.map(value), 0));
    // 張數這類整數資料，中間刻度也要是整數（避免出現 2.5 張）
    if (rows.every((row) => Number.isInteger(value(row))) && max % 2) max += 1;
    const plotW = width - left - right, plotH = height - top - bottom;
    const band = plotW / rows.length;
    const barW = Math.min(24, band * 0.6);
    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img", "aria-label": tipLabel });
    [0, 0.5, 1].forEach((ratio) => {
      const y = top + plotH * (1 - ratio);
      svg("line", { x1: left, x2: width - right, y1: y, y2: y, class: ratio === 0 ? "axis" : "grid" }, root);
      svg("text", { x: left - 6, y: y + 4, class: "tick", "text-anchor": "end" }, root).textContent = compact(max * ratio);
    });
    rows.forEach((row, i) => {
      const v = value(row);
      const h = (v / max) * plotH;
      const x = left + band * i + (band - barW) / 2;
      const y = top + plotH - h;
      if (h > 0) {
        const r = Math.min(4, h, barW / 2);
        svg("path", {
          d: `M${x},${top + plotH} V${y + r} Q${x},${y} ${x + r},${y} H${x + barW - r} Q${x + barW},${y} ${x + barW},${y + r} V${top + plotH} Z`,
          class: "bar",
        }, root);
      }
      if (i % Math.ceil(rows.length / 7) === 0 || i === rows.length - 1) {
        svg("text", { x: x + barW / 2, y: height - 8, class: "tick", "text-anchor": "middle" }, root).textContent = label(row);
      }
      // 滑鼠感應區比柱子大（整個欄位）
      const hit = svg("rect", { x: left + band * i, y: top, width: band, height: plotH, class: "hit" }, root);
      bindTip(hit, `${label(row)}｜${tipLabel}：${format(v)}`);
    });
    container.append(root);
    table(container, ["日期", tipLabel], rows.map((row) => [label(row), format(value(row))]));
  }

  // 橫條圖：熱門行程，數值寫在條的尾端
  function bars(container, rows, { name, value, format, unit }) {
    container.replaceChildren();
    const max = Math.max(...rows.map(value), 1);
    const list = document.createElement("div");
    list.className = "hbars";
    rows.forEach((row) => {
      const line = document.createElement("div");
      line.className = "hbar-row";
      const label = document.createElement("span");
      label.className = "hbar-label";
      label.textContent = name(row);
      const track = document.createElement("span");
      track.className = "hbar-track";
      const bar = document.createElement("span");
      bar.className = "hbar";
      bar.style.width = `${(value(row) / max) * 100}%`;
      const val = document.createElement("span");
      val.className = "hbar-value";
      val.textContent = format(value(row));
      track.append(bar, val);
      line.append(label, track);
      bindTip(line, `${name(row)}：${format(value(row))}`);
      list.append(line);
    });
    if (!rows.length) list.textContent = "近 30 天沒有資料。";
    container.append(list);
    table(container, ["行程", unit], rows.map((row) => [name(row), format(value(row))]));
  }

  // 比例條：兩類以上，色塊之間留 2px 間隔，並附圖例（顏色不是唯一的辨識方式）
  function share(container, parts) {
    container.replaceChildren();
    const total = parts.reduce((sum, p) => sum + p.value, 0);
    const bar = document.createElement("div");
    bar.className = "share-bar";
    const legend = document.createElement("div");
    legend.className = "legend";
    parts.forEach((part, i) => {
      const pct = total ? Math.round((part.value / total) * 100) : 0;
      const seg = document.createElement("span");
      seg.className = `share-seg series-${i + 1}`;
      seg.style.flexGrow = part.value;
      if (part.value) bar.append(seg);
      bindTip(seg, `${part.name}：${part.value}（${pct}%）`);
      const key = document.createElement("span");
      key.className = "legend-item";
      const swatch = document.createElement("i");
      swatch.className = `swatch series-${i + 1}`;
      key.append(swatch, `${part.name} ${part.value}（${pct}%）`);
      legend.append(key);
    });
    if (!total) bar.textContent = "近 30 天沒有資料。";
    container.append(bar, legend);
    table(container, ["來源", "報價數", "比例"], parts.map((p) => [p.name, p.value, total ? `${Math.round((p.value / total) * 100)}%` : "0%"]));
  }

  return { columns, bars, share, compact };
})();
