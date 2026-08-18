-- PipeCore reporting store (ClickHouse).
-- High-ingest flow records exported by the data-plane nodes, plus rollups
-- that power the dashboard's by-protocol / application / pipe / IP / customer views.

CREATE DATABASE IF NOT EXISTS pipecore;

-- Raw flow records (one row per flow per accounting window).
CREATE TABLE IF NOT EXISTS pipecore.flows
(
    ts              DateTime,
    subscriber_ref  LowCardinality(String),
    src_ip          IPv4,
    dst_ip          IPv4,
    application     LowCardinality(String),
    protocol        LowCardinality(String),
    pipe_id         UInt32,
    bytes_down      UInt64,
    bytes_up        UInt64,
    packets         UInt64,
    rtt_ms          Float32
)
ENGINE = MergeTree
PARTITION BY toYYYYMMDD(ts)
ORDER BY (ts, subscriber_ref, application)
TTL ts + INTERVAL 90 DAY;          -- retention; tune to disk / compliance

-- 1-minute rollup for fast dashboards (materialized on insert).
CREATE TABLE IF NOT EXISTS pipecore.flows_1m
(
    minute          DateTime,
    application     LowCardinality(String),
    protocol        LowCardinality(String),
    pipe_id         UInt32,
    bytes           UInt64,
    flows           UInt64
)
ENGINE = SummingMergeTree
PARTITION BY toYYYYMMDD(minute)
ORDER BY (minute, application, protocol, pipe_id)
TTL minute + INTERVAL 365 DAY;

CREATE MATERIALIZED VIEW IF NOT EXISTS pipecore.flows_1m_mv
TO pipecore.flows_1m AS
SELECT
    toStartOfMinute(ts)              AS minute,
    application,
    protocol,
    pipe_id,
    sum(bytes_down + bytes_up)       AS bytes,
    count()                          AS flows
FROM pipecore.flows
GROUP BY minute, application, protocol, pipe_id;
