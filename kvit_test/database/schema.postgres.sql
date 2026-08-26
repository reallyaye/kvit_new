-- PostgreSQL Schema for Production Deployment
-- Multi-RES, High-Concurrency Distributed Receipt Platform

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    applied_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id BIGSERIAL PRIMARY KEY,
    account_number VARCHAR(64) NOT NULL UNIQUE,
    customer_name VARCHAR(255),
    address TEXT,
    street VARCHAR(255),
    building VARCHAR(64),
    corpus VARCHAR(64),
    district VARCHAR(128),
    organization VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_accounts_account ON accounts(account_number);
CREATE INDEX IF NOT EXISTS idx_accounts_address ON accounts(address);

CREATE TABLE IF NOT EXISTS receipts (
    id BIGSERIAL PRIMARY KEY,
    account_number VARCHAR(64) NOT NULL,
    period VARCHAR(64) NOT NULL,
    pdf_file TEXT NOT NULL,
    file_hash VARCHAR(64),
    semantic_hash VARCHAR(64),
    content_hash VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'READY',
    access_token VARCHAR(64),
    address TEXT,
    CONSTRAINT uq_receipts_account_period UNIQUE (account_number, period)
);

CREATE INDEX IF NOT EXISTS idx_receipts_account_period ON receipts(account_number, period);
CREATE INDEX IF NOT EXISTS idx_receipts_account ON receipts(account_number);
CREATE INDEX IF NOT EXISTS idx_receipts_period ON receipts(period);
CREATE INDEX IF NOT EXISTS idx_receipts_address ON receipts(address);
CREATE INDEX IF NOT EXISTS idx_receipts_file_hash ON receipts(file_hash);
CREATE INDEX IF NOT EXISTS idx_receipts_semantic_hash ON receipts(semantic_hash);
CREATE INDEX IF NOT EXISTS idx_receipts_hash ON receipts(content_hash);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_token ON receipts(access_token);
CREATE INDEX IF NOT EXISTS idx_accounts_street_bld ON accounts(street, building);
CREATE INDEX IF NOT EXISTS idx_receipts_hash_acc ON receipts(content_hash, account_number);

CREATE TABLE IF NOT EXISTS app_sessions (
    token VARCHAR(64) PRIMARY KEY,
    expires_at DOUBLE PRECISION NOT NULL,
    created_at DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_expires ON app_sessions(expires_at);

CREATE TABLE IF NOT EXISTS security_blocks (
    ip VARCHAR(64) PRIMARY KEY,
    blocked_until DOUBLE PRECISION NOT NULL,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_blocks_until ON security_blocks(blocked_until);

CREATE TABLE IF NOT EXISTS telegram_users (
    telegram_id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    role VARCHAR(32) NOT NULL DEFAULT 'USER',
    requested_at DOUBLE PRECISION NOT NULL,
    reviewed_at DOUBLE PRECISION,
    reviewed_by BIGINT,
    comment TEXT
);

CREATE INDEX IF NOT EXISTS idx_tg_users_status ON telegram_users(status);

