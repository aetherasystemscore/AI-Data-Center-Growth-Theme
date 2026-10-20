-- AI Infrastructure Investment Intelligence (AI3) — Initial SQL Schema Migration (v1.0.0)
-- Generated for SQLite / PostgreSQL compatibility.
-- All 28 tables are managed via SQLAlchemy Declarative Base (database/models.py)
-- and can also be inspected or applied via this reference migration script.

CREATE TABLE IF NOT EXISTS exchanges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    country VARCHAR(60) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    timezone_str VARCHAR(40) DEFAULT 'Asia/Kolkata',
    access_notes TEXT
);

CREATE TABLE IF NOT EXISTS securities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(32) NOT NULL UNIQUE,
    yf_ticker VARCHAR(40) NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    isin VARCHAR(32) NOT NULL,
    exchange_code VARCHAR(20) NOT NULL,
    country VARCHAR(60) DEFAULT 'India',
    currency VARCHAR(10) DEFAULT 'INR',
    security_type VARCHAR(30) DEFAULT 'EQUITY',
    listing_date DATE,
    listing_status VARCHAR(30) DEFAULT 'ACTIVE',
    universe_tier VARCHAR(40) DEFAULT 'INVESTABLE_INDIA',
    is_investable BOOLEAN DEFAULT 1,
    high_risk_flag BOOLEAN DEFAULT 0,
    primary_category VARCHAR(60) NOT NULL,
    subcategory_tags VARCHAR(255) DEFAULT '',
    verification_notes TEXT,
    updated_at DATETIME
);
