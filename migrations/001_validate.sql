-- Warden treats any returned row as a failed migration validation.
SELECT
  id,
  email,
  plan,
  created_at
FROM warden.demo_users
WHERE plan IS NULL
   OR plan NOT IN ('free', 'pro', 'enterprise')
ORDER BY id;
