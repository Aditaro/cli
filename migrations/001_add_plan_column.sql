-- The demo table already has a `plan` column. This migration establishes the
-- business rule that values stored in it must be one of Warden's supported plans.
ALTER TABLE warden.demo_users
  ADD CONSTRAINT demo_users_valid_plan
  CHECK (plan IN ('free', 'pro', 'enterprise'));
