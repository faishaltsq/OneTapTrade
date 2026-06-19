CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS bot_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL DEFAULT 'XAUUSD',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    mode TEXT NOT NULL DEFAULT 'SIGNAL_ONLY',
    timeframe_bias TEXT NOT NULL DEFAULT 'H4',
    timeframe_entry TEXT NOT NULL DEFAULT 'M15',
    risk_per_trade_percent NUMERIC NOT NULL DEFAULT 0.5,
    max_daily_drawdown_percent NUMERIC NOT NULL DEFAULT 2.0,
    max_spread_points INTEGER NOT NULL DEFAULT 35,
    min_confidence NUMERIC NOT NULL DEFAULT 0.65,
    min_risk_reward NUMERIC NOT NULL DEFAULT 1.5,
    risk_profile TEXT NOT NULL DEFAULT 'MEDIUM',
    max_open_positions INTEGER NOT NULL DEFAULT 1,
    is_paused BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE bot_settings
    ADD COLUMN IF NOT EXISTS risk_profile TEXT NOT NULL DEFAULT 'MEDIUM';

INSERT INTO bot_settings (symbol) VALUES ('XAUUSD')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS market_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bid NUMERIC,
    ask NUMERIC,
    spread_points INTEGER,
    close_price NUMERIC,
    technical JSONB,
    volume_profile JSONB,
    orderflow JSONB,
    raw_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_snapshots_symbol_created
    ON market_snapshots (symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    market_snapshot_id UUID REFERENCES market_snapshots(id),
    model_name TEXT,
    input_json JSONB,
    output_json JSONB,
    decision TEXT,
    confidence NUMERIC,
    entry_type TEXT,
    stop_loss NUMERIC,
    take_profit_1 NUMERIC,
    take_profit_2 NUMERIC,
    risk_reward_to_tp1 NUMERIC,
    ai_allows_execution BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_decisions_symbol_created
    ON ai_decisions (symbol, created_at DESC);

CREATE TABLE IF NOT EXISTS risk_checks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ai_decision_id UUID REFERENCES ai_decisions(id),
    approved BOOLEAN NOT NULL,
    reason TEXT,
    checks JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol TEXT NOT NULL,
    mt5_ticket BIGINT,
    ai_decision_id UUID REFERENCES ai_decisions(id),
    side TEXT NOT NULL,
    lot NUMERIC NOT NULL,
    entry_price NUMERIC,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    close_price NUMERIC,
    profit NUMERIC,
    status TEXT NOT NULL DEFAULT 'PENDING',
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_trades_symbol_status ON trades (symbol, status);

CREATE TABLE IF NOT EXISTS telegram_commands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chat_id TEXT NOT NULL,
    command TEXT NOT NULL,
    payload JSONB,
    result TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_telegram_commands_chat_created
    ON telegram_commands (chat_id, created_at DESC);

CREATE TABLE IF NOT EXISTS bot_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type TEXT NOT NULL,
    message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bot_events_type_created
    ON bot_events (event_type, created_at DESC);
