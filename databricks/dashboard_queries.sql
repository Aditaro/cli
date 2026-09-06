-- Warden dashboard: migration attempts vs. heals over time.
-- Assumes warden.migration_log exists, created and populated by the Warden core
-- CLI with columns (id BIGINT, migration_name STRING, status STRING,
-- checkpoint_id STRING, ts TIMESTAMP).
-- Status values: 'applied' (an attempt executed), 'healed' (rolled back via
-- Delta time travel), 'failed' (non-recoverable outcome).
SELECT
  DATE(ts) AS day,
  COUNT(*) AS total,
  SUM(CASE WHEN status = 'applied' THEN 1 ELSE 0 END) AS attempts,
  SUM(CASE WHEN status = 'healed'  THEN 1 ELSE 0 END) AS heals,
  SUM(CASE WHEN status = 'failed'  THEN 1 ELSE 0 END) AS failures
FROM warden.migration_log
GROUP BY DATE(ts)
ORDER BY day;