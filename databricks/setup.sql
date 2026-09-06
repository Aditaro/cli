-- Warden demo migration target: a single Delta table of (clearly synthetic)
-- customer accounts. `plan` values intentionally include one offender
-- ('legacy') so 001_add_plan_column.sql fails validation and Warden can demo
-- its Delta time-travel heal on it.
CREATE TABLE IF NOT EXISTS warden.demo_users (
  id         BIGINT,
  email      STRING,
  plan       STRING,
  created_at TIMESTAMP
)
USING DELTA;