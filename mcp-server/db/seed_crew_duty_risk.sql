-- Demo fixture for crew_duty_risk_resolution on an existing sample database.
-- Keeps the roster action itself mocked; these statements only prepare C345 as
-- a qualified reserve candidate for the FL-1042 demo.

UPDATE crew
SET base = 'JFK'
WHERE crew_id = 'C345';

INSERT INTO duty_clock (crew_id, total_minutes, max_allowed)
SELECT id, 120, 720
FROM crew
WHERE crew_id = 'C345'
ON CONFLICT (crew_id) DO UPDATE
SET total_minutes = EXCLUDED.total_minutes,
    max_allowed = EXCLUDED.max_allowed;

INSERT INTO certification (crew_id, certification_type, expires_at)
SELECT id, 'TypeA', (CURRENT_DATE + INTERVAL '180 days')::date
FROM crew
WHERE crew_id = 'C345'
ON CONFLICT (crew_id) DO UPDATE
SET certification_type = EXCLUDED.certification_type,
    expires_at = EXCLUDED.expires_at;

INSERT INTO reserve (crew_id, available)
SELECT id, TRUE
FROM crew
WHERE crew_id = 'C345'
ON CONFLICT (crew_id) DO UPDATE
SET available = EXCLUDED.available;
