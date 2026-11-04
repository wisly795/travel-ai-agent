-- 每次啟動都會執行，所以每一句都要能重複執行。

ALTER TABLE quotes ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'web';

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    history JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 客人每問一次就是一筆，記錄用的模型、花費與回答。
CREATE TABLE IF NOT EXISTS ai_turns (
    id SERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id),
    user_message TEXT NOT NULL,
    reply TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- AI 每次呼叫工具都留紀錄，方便查錯。
CREATE TABLE IF NOT EXISTS ai_tool_calls (
    id SERIAL PRIMARY KEY,
    turn_id INTEGER NOT NULL REFERENCES ai_turns(id),
    tool TEXT NOT NULL,
    input JSONB NOT NULL,
    output JSONB NOT NULL,
    is_error BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS handoffs (
    id SERIAL PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id),
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '待處理',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RAG：旅遊規定一條一筆，embedding 是 384 維的向量。
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_chunks (
    id SERIAL PRIMARY KEY,
    doc TEXT NOT NULL,
    article TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL
);

-- HNSW 索引：資料量大時用近似搜尋加速，餘弦距離。
CREATE INDEX IF NOT EXISTS idx_policy_embedding ON policy_chunks USING hnsw (embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 報價狀態：已報價 → 成交 / 取消；每次變更都留紀錄
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT '已報價';

CREATE TABLE IF NOT EXISTS quote_events (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER NOT NULL REFERENCES quotes(id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 每張成交報價同步到 ERP 的結果
CREATE TABLE IF NOT EXISTS erp_syncs (
    quote_id INTEGER PRIMARY KEY REFERENCES quotes(id),
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    erp_order_no TEXT,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 採購：向供應商訂房。供應商與報價都是模擬資料。
CREATE TABLE IF NOT EXISTS suppliers (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    rating NUMERIC(2, 1) NOT NULL,
    note TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_offers (
    id SERIAL PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    hotel_id INTEGER NOT NULL REFERENCES hotels(id),
    price_per_room_night INTEGER NOT NULL CHECK (price_per_room_night > 0),
    rooms_available INTEGER NOT NULL CHECK (rooms_available >= 0),
    free_cancel_days INTEGER NOT NULL,  -- 出發前幾天以前可免費取消；0 代表不能免費取消
    cancel_fee_percent INTEGER NOT NULL,
    UNIQUE (supplier_id, hotel_id)
);

INSERT INTO suppliers (name, rating, note) VALUES
    ('飯店直訂', 4.8, '直接向飯店訂房，價格較高但條件最彈性'),
    ('東亞旅宿批發', 4.1, '批發價最低，但房量少且訂了不能免費取消'),
    ('海島訂房網', 4.4, '價格居中，房量中等')
ON CONFLICT (name) DO NOTHING;

-- 每間飯店在三個管道各有一筆報價：直訂 85 折、批發 75 折、訂房網 8 折
INSERT INTO supplier_offers (supplier_id, hotel_id, price_per_room_night, rooms_available, free_cancel_days, cancel_fee_percent)
SELECT s.id, h.id,
       (h.price_per_night * c.factor)::int,
       c.rooms, c.free_days, c.fee
FROM hotels h
CROSS JOIN (VALUES ('飯店直訂', 0.85, 20, 14, 30),
                   ('東亞旅宿批發', 0.75, 6, 0, 100),
                   ('海島訂房網', 0.80, 10, 7, 50)) AS c(name, factor, rooms, free_days, fee)
JOIN suppliers s ON s.name = c.name
ON CONFLICT (supplier_id, hotel_id) DO NOTHING;

-- 請購單：報價成交後自動產生，預算是報價裡的住宿費
CREATE TABLE IF NOT EXISTS purchase_requests (
    id SERIAL PRIMARY KEY,
    quote_id INTEGER UNIQUE NOT NULL REFERENCES quotes(id),
    hotel_id INTEGER NOT NULL REFERENCES hotels(id),
    rooms INTEGER NOT NULL,
    nights INTEGER NOT NULL,
    budget INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT '待比價',
    ai_analysis TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 採購單：AI 只能建立草稿，核准後才會送給供應商
CREATE TABLE IF NOT EXISTS purchase_orders (
    id SERIAL PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES purchase_requests(id),
    offer_id INTEGER NOT NULL REFERENCES supplier_offers(id),
    amount INTEGER NOT NULL,
    over_budget BOOLEAN NOT NULL,
    approver_role TEXT NOT NULL,          -- 業務 或 主管
    ai_reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '待核准', -- 待核准、已退回、已下單、下單失敗
    reject_reason TEXT,
    confirmation_no TEXT,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ
);

-- 通知中心：n8n 自動化流程把通知寫進來，業務在後台查看
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL,          -- 新報價、每日報表、採購待核准、同步失敗
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    dedupe_key TEXT UNIQUE,      -- 同一件事只通知一次
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 第二期 H1：出發日期（舊資料沒有，允許空值）
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS departure_date DATE;
ALTER TABLE purchase_requests ADD COLUMN IF NOT EXISTS departure_date DATE;

-- 第二期 H2：帳號、登入工作階段、登入紀錄、操作者
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('業務', '主管', '管理員')),
    password_hash TEXT NOT NULL,            -- PBKDF2 加鹽雜湊，不存原始密碼
    is_active BOOLEAN NOT NULL DEFAULT true,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,            -- 只存工作階段的雜湊
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS login_events (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    reason TEXT NOT NULL,
    ip TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE quote_events ADD COLUMN IF NOT EXISTS changed_by TEXT NOT NULL DEFAULT '';
ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS decided_by TEXT;

-- 第二期 H4：合作夥伴 API（官網串接）
CREATE TABLE IF NOT EXISTS partners (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    key_prefix TEXT NOT NULL,               -- 只留前幾碼方便辨識
    key_hash TEXT UNIQUE NOT NULL,          -- API 金鑰只存雜湊
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 30 CHECK (rate_limit_per_minute BETWEEN 1 AND 600),
    is_active BOOLEAN NOT NULL DEFAULT true,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS partner_calls (
    id SERIAL PRIMARY KEY,
    partner_id INTEGER NOT NULL REFERENCES partners(id),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_partner_calls_recent ON partner_calls(partner_id, created_at);

ALTER TABLE quotes ADD COLUMN IF NOT EXISTS partner_id INTEGER REFERENCES partners(id);

-- 第二期 H6：AI 自動評測
CREATE TABLE IF NOT EXISTS eval_runs (
    id SERIAL PRIMARY KEY,
    label TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '執行中',
    passed INTEGER,
    total INTEGER,
    cost_usd NUMERIC(10, 6),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS eval_results (
    id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES eval_runs(id),
    case_id TEXT NOT NULL,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    failures JSONB NOT NULL,
    reply TEXT NOT NULL,
    tools JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_turns_created ON ai_turns(created_at);
CREATE INDEX IF NOT EXISTS idx_ai_tool_calls_turn ON ai_tool_calls(turn_id);

-- 多 Agent 協作：對話用哪種模式、每次經過哪些 Agent、每個工具是哪位專員呼叫的
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'single';
ALTER TABLE ai_turns ADD COLUMN IF NOT EXISTS agent_path JSONB;
ALTER TABLE ai_tool_calls ADD COLUMN IF NOT EXISTS agent TEXT;

-- 政府開放資料（交通部觀光署）：整理後的內容放 data，hash 用來判斷有沒有變；官方下架的標 active = false
CREATE TABLE IF NOT EXISTS od_attractions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT '',
    data JSONB NOT NULL,
    hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS od_hotels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL DEFAULT '',
    data JSONB NOT NULL,
    hash TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_od_attractions_city ON od_attractions(city) WHERE active;
CREATE INDEX IF NOT EXISTS idx_od_hotels_city ON od_hotels(city) WHERE active;
-- 每次匯入一筆：什麼時候、誰觸發、官方資料時間、新增／更新／不變／下架幾筆、失敗原因
CREATE TABLE IF NOT EXISTS od_imports (
    id SERIAL PRIMARY KEY,
    dataset TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '執行中',
    source_time TEXT,
    total INTEGER, inserted INTEGER, updated INTEGER, unchanged INTEGER, removed INTEGER,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

-- 爬蟲：模擬供應商網站的住宿、價格歷史（只有變動才寫一筆）、每次爬取紀錄
CREATE TABLE IF NOT EXISTS crawled_hotels (
    supplier_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    stars INTEGER NOT NULL DEFAULT 0,
    url TEXT NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS crawled_prices (
    id SERIAL PRIMARY KEY,
    supplier_id TEXT NOT NULL REFERENCES crawled_hotels(supplier_id),
    room TEXT NOT NULL,
    price INTEGER,
    promo BOOLEAN NOT NULL DEFAULT false,
    price_date TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_crawled_prices_hotel ON crawled_prices(supplier_id, room, id DESC);
CREATE TABLE IF NOT EXISTS crawl_runs (
    id SERIAL PRIMARY KEY,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '執行中',
    pages INTEGER, hotels INTEGER, changes INTEGER, alerts INTEGER, requests INTEGER, retries INTEGER,
    errors JSONB NOT NULL DEFAULT '[]',
    seconds NUMERIC(8, 1),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);
