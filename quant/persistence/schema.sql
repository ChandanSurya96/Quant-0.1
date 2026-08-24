-- SQLite Schema: quant_state_v1.db
-- Version: 1

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_runs (
    run_id TEXT PRIMARY KEY,
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('RESEARCH', 'PAPER', 'LIVE')),
    strategy_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('RUNNING', 'SUCCESS', 'FAILED', 'ABORTED')),
    error_message TEXT,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT PRIMARY KEY,
    asset_class TEXT NOT NULL CHECK(asset_class IN ('EQUITY', 'BOND', 'CURRENCY', 'COMMODITY')),
    currency TEXT NOT NULL DEFAULT 'USD',
    multiplier REAL NOT NULL DEFAULT 1.0,
    tick_size REAL NOT NULL DEFAULT 0.01,
    is_active INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT
);

CREATE TABLE IF NOT EXISTS target_portfolios (
    portfolio_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    rebalance_horizon INTEGER NOT NULL,
    weights_json TEXT NOT NULL,
    nav_reference REAL,
    metadata_json TEXT,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS risk_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    approved INTEGER NOT NULL CHECK(approved IN (0, 1)),
    adjusted_weights_json TEXT NOT NULL,
    reason TEXT,
    metadata_json TEXT,
    FOREIGN KEY(portfolio_id) REFERENCES target_portfolios(portfolio_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    client_order_id TEXT UNIQUE,
    run_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    order_type TEXT NOT NULL CHECK(order_type IN ('MARKET', 'LIMIT', 'TWAP', 'VWAP')),
    quantity REAL NOT NULL,
    limit_price REAL,
    status TEXT NOT NULL CHECK(status IN ('CREATED', 'APPROVED', 'SUBMITTED', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED', 'REJECTED')),
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('RESEARCH', 'PAPER', 'LIVE')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(symbol) REFERENCES instruments(symbol)
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id TEXT PRIMARY KEY,
    broker_execution_id TEXT UNIQUE,
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    quantity REAL NOT NULL,
    fill_price REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0.0,
    filled_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
    FOREIGN KEY(symbol) REFERENCES instruments(symbol)
);

CREATE TABLE IF NOT EXISTS physical_holdings (
    symbol TEXT NOT NULL,
    portfolio_id TEXT NOT NULL DEFAULT 'default',
    shares REAL NOT NULL,
    cost_basis REAL NOT NULL,
    last_price REAL NOT NULL,
    market_value REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(symbol, portfolio_id),
    FOREIGN KEY(symbol) REFERENCES instruments(symbol)
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('RESEARCH', 'PAPER', 'LIVE')),
    strategy_id TEXT NOT NULL,
    nav REAL NOT NULL,
    cash REAL NOT NULL,
    gross_exposure REAL NOT NULL,
    net_exposure REAL NOT NULL,
    realized_pnl REAL DEFAULT 0.0,
    unrealized_pnl REAL DEFAULT 0.0,
    realized_weights_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    reconciliation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('RESEARCH', 'PAPER', 'LIVE')),
    status TEXT NOT NULL CHECK(status IN ('MATCHED', 'MISMATCHED', 'UNKNOWN', 'ERROR')),
    issues_count INTEGER NOT NULL,
    summary_json TEXT,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reconciliation_issues (
    issue_id TEXT PRIMARY KEY,
    reconciliation_id TEXT NOT NULL,
    issue_type TEXT NOT NULL,
    symbol TEXT,
    order_id TEXT,
    fill_id TEXT,
    internal_value REAL,
    broker_value REAL,
    discrepancy REAL,
    message TEXT NOT NULL,
    FOREIGN KEY(reconciliation_id) REFERENCES reconciliation_runs(reconciliation_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS paper_run_ledger (
    run_id TEXT PRIMARY KEY,
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('RESEARCH', 'PAPER', 'LIVE')),
    strategy_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    data_timestamp TEXT,
    target_portfolio_id TEXT,
    risk_decision_id TEXT,
    order_batch_id TEXT,
    orders_count INTEGER NOT NULL DEFAULT 0,
    fills_count INTEGER NOT NULL DEFAULT 0,
    gross_exposure REAL NOT NULL DEFAULT 0.0,
    net_exposure REAL NOT NULL DEFAULT 0.0,
    nav REAL NOT NULL DEFAULT 0.0,
    cash REAL NOT NULL DEFAULT 0.0,
    drawdown REAL NOT NULL DEFAULT 0.0,
    transaction_costs REAL NOT NULL DEFAULT 0.0,
    borrow_costs REAL NOT NULL DEFAULT 0.0,
    pre_reconciliation_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    post_reconciliation_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    status TEXT NOT NULL CHECK(status IN ('STARTED', 'DATA_FAILED', 'VALIDATION_FAILED', 'RISK_REJECTED', 'RECONCILIATION_FAILED', 'EXECUTED', 'COMPLETED', 'RECOVERY_REQUIRED')),
    error_message TEXT,
    metadata_json TEXT,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS p85_burnin_ledger (
    sequence_num INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    run_id TEXT NOT NULL,
    order_batch_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    quantity REAL NOT NULL,
    order_type TEXT NOT NULL,
    requested_price REAL,
    executed_price REAL,
    broker_order_id TEXT NOT NULL,
    broker_execution_id TEXT NOT NULL,
    commission REAL NOT NULL DEFAULT 0.0,
    slippage REAL DEFAULT 0.0,
    approval_token_id TEXT NOT NULL,
    risk_decision_id TEXT NOT NULL,
    pre_reconciliation_status TEXT NOT NULL,
    post_reconciliation_status TEXT NOT NULL,
    final_order_status TEXT NOT NULL,
    success INTEGER NOT NULL CHECK(success IN (0, 1)),
    failure_reason TEXT,
    metadata_json TEXT,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS p9_autonomous_ledger (
    run_id TEXT PRIMARY KEY,
    trading_date TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    order_batch_id TEXT,
    target_portfolio_id TEXT,
    risk_decision_id TEXT,
    approval_token_id TEXT,
    orders_count INTEGER NOT NULL DEFAULT 0,
    fills_count INTEGER NOT NULL DEFAULT 0,
    gross_exposure REAL NOT NULL DEFAULT 0.0,
    net_exposure REAL NOT NULL DEFAULT 0.0,
    nav REAL NOT NULL DEFAULT 0.0,
    cash REAL NOT NULL DEFAULT 0.0,
    pre_reconciliation_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    post_reconciliation_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    status TEXT NOT NULL CHECK(status IN ('STARTED', 'APPROVED', 'REJECTED', 'EXECUTED', 'COMPLETED', 'BLOCKED', 'RECOVERY_REQUIRED')),
    rejection_reason TEXT,
    metadata_json TEXT,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS p91_canary_ledger (
    sequence_num INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    run_id TEXT NOT NULL,
    canary_run_id TEXT NOT NULL,
    order_batch_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
    quantity REAL NOT NULL,
    order_type TEXT NOT NULL,
    requested_price REAL,
    executed_price REAL,
    broker_order_id TEXT NOT NULL,
    broker_execution_id TEXT NOT NULL,
    commission REAL NOT NULL DEFAULT 0.0,
    slippage REAL DEFAULT 0.0,
    approval_token_id TEXT NOT NULL,
    risk_decision_id TEXT NOT NULL,
    pre_reconciliation_status TEXT NOT NULL,
    post_reconciliation_status TEXT NOT NULL,
    final_order_status TEXT NOT NULL,
    success INTEGER NOT NULL CHECK(success IN (0, 1)),
    failure_reason TEXT,
    metadata_json TEXT,
    FOREIGN KEY(run_id) REFERENCES system_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON system_runs(status);
CREATE INDEX IF NOT EXISTS idx_target_portfolios_run ON target_portfolios(run_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_run ON orders(run_id);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_time ON portfolio_snapshots(timestamp);
CREATE INDEX IF NOT EXISTS idx_reconciliation_run ON reconciliation_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_paper_ledger_status ON paper_run_ledger(status);
CREATE INDEX IF NOT EXISTS idx_burnin_ledger_success ON p85_burnin_ledger(success);
CREATE INDEX IF NOT EXISTS idx_autonomous_date ON p9_autonomous_ledger(trading_date);
CREATE INDEX IF NOT EXISTS idx_autonomous_status ON p9_autonomous_ledger(status);
CREATE INDEX IF NOT EXISTS idx_canary_ledger_success ON p91_canary_ledger(success);
