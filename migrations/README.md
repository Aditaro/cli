# Warden demo migration

This migration adds a Delta `CHECK` constraint to `warden.demo_users`, limiting `plan` to `free`, `pro`, or `enterprise`; the seeded synthetic data is intentionally expected to include at least one row whose `plan` is outside that set (for example, `legacy`), so `001_validate.sql` returns that offender and Warden heals by restoring the table to its pre-migration Delta version while explaining that the recorded plan-normalization intent conflicted with existing data.
