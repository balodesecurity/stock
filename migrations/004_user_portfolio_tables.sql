-- 004: Replace flat portfolios table with proper user → portfolio → stocks hierarchy
--
-- Run: sqlite3 /home/amitbalode/personnel/derived_metrics_analysis.db < migrations/004_user_portfolio_tables.sql

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    email      TEXT    UNIQUE NOT NULL,
    name       TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_portfolios (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL DEFAULT 'My Portfolio',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, name)
);

CREATE TABLE IF NOT EXISTS user_portfolio_stocks (
    portfolio_id INTEGER NOT NULL REFERENCES user_portfolios(id) ON DELETE CASCADE,
    company_code TEXT    NOT NULL,
    added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (portfolio_id, company_code)
);

-- Migrate existing email-keyed rows from portfolios (emails contain '@')
INSERT OR IGNORE INTO users (email)
    SELECT DISTINCT portfolio_name FROM portfolios
    WHERE portfolio_name LIKE '%@%';

INSERT OR IGNORE INTO user_portfolios (user_id, name)
    SELECT id, 'My Portfolio' FROM users;

INSERT OR IGNORE INTO user_portfolio_stocks (portfolio_id, company_code)
    SELECT up.id, p.company_code
    FROM portfolios p
    JOIN users u ON u.email = p.portfolio_name
    JOIN user_portfolios up ON up.user_id = u.id AND up.name = 'My Portfolio';

DROP TABLE IF EXISTS portfolios;
