-- 005: Remove user_portfolios table — one implicit portfolio per user, linked directly via user_id
--
-- Run: sqlite3 /home/amitbalode/personnel/derived_metrics_analysis.db < migrations/005_drop_user_portfolios_table.sql

CREATE TABLE user_portfolio_stocks_new (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_code TEXT    NOT NULL,
    added_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, company_code)
);

INSERT INTO user_portfolio_stocks_new (user_id, company_code, added_at)
    SELECT up.user_id, ups.company_code, ups.added_at
    FROM user_portfolio_stocks ups
    JOIN user_portfolios up ON up.id = ups.portfolio_id;

DROP TABLE user_portfolio_stocks;
DROP TABLE user_portfolios;

ALTER TABLE user_portfolio_stocks_new RENAME TO user_portfolio_stocks;
