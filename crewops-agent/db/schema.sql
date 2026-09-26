-- SQL schema for CrewOps database

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Crew table
CREATE TABLE crew (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    crew_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    base TEXT,
    rank TEXT
);

-- Flight table
CREATE TABLE flight (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flight_id TEXT UNIQUE NOT NULL,
    origin TEXT,
    destination TEXT,
    scheduled_time TIMESTAMP,
    status TEXT,
    delay_minutes INTEGER DEFAULT 0
);

-- Roster association (crew assigned to flight)
CREATE TABLE flight_roster (
    flight_id UUID REFERENCES flight(id) ON DELETE CASCADE,
    crew_id UUID REFERENCES crew(id) ON DELETE CASCADE,
    PRIMARY KEY (flight_id, crew_id)
);

-- Duty clock table (tracking accrued duty minutes per crew)
CREATE TABLE duty_clock (
    crew_id UUID PRIMARY KEY REFERENCES crew(id) ON DELETE CASCADE,
    total_minutes INTEGER NOT NULL,
    max_allowed INTEGER NOT NULL
);

-- Certification table (crew certification expiry dates)
CREATE TABLE certification (
    crew_id UUID PRIMARY KEY REFERENCES crew(id) ON DELETE CASCADE,
    certification_type TEXT,
    expires_at DATE
);

-- Reserve pool (available crew not currently assigned)
CREATE TABLE reserve (
    crew_id UUID PRIMARY KEY REFERENCES crew(id) ON DELETE CASCADE,
    available BOOLEAN DEFAULT TRUE
);

-- Rules table (example rule definitions)
CREATE TABLE rules (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    value TEXT
);

-- Risk signals (placeholder)
CREATE TABLE risk_signal (
    id SERIAL PRIMARY KEY,
    flight_id UUID REFERENCES flight(id) ON DELETE CASCADE,
    signal_type TEXT,
    severity INTEGER
);

-- Sample data insertion (minimal)
INSERT INTO crew (crew_id, name, base, rank) VALUES
    ('C102', 'Alice Smith', 'JFK', 'Captain'),
    ('C231', 'Bob Jones', 'LAX', 'First Officer'),
    ('C345', 'Carol Lee', 'ORD', 'Captain');

INSERT INTO flight (flight_id, origin, destination, scheduled_time, status, delay_minutes) VALUES
    ('FL-1042', 'JFK', 'LAX', NOW() + INTERVAL '2 hours', 'Scheduled', 240),
    ('FL-1050', 'LAX', 'ORD', NOW() + INTERVAL '4 hours', 'Scheduled', 0);

-- Assign crew to flight FL-1042
INSERT INTO flight_roster (flight_id, crew_id)
SELECT f.id, c.id FROM flight f, crew c WHERE f.flight_id = 'FL-1042' AND c.crew_id IN ('C102', 'C231');

-- Duty clocks (minutes accrued, max allowed 720 minutes = 12 hours)
INSERT INTO duty_clock (crew_id, total_minutes, max_allowed)
SELECT id, 600, 720 FROM crew WHERE crew_id = 'C102';
INSERT INTO duty_clock (crew_id, total_minutes, max_allowed)
SELECT id, 300, 720 FROM crew WHERE crew_id = 'C231';

-- Certifications (expiry dates)
INSERT INTO certification (crew_id, certification_type, expires_at)
SELECT id, 'TypeA', (NOW() + INTERVAL '180 days')::date FROM crew WHERE crew_id = 'C102';
INSERT INTO certification (crew_id, certification_type, expires_at)
SELECT id, 'TypeA', (NOW() + INTERVAL '30 days')::date FROM crew WHERE crew_id = 'C231';

-- Reserves (none for now)
INSERT INTO reserve (crew_id, available)
SELECT id, FALSE FROM crew WHERE crew_id IN ('C102', 'C231');

-- Simple rule (max duty per day)
INSERT INTO rules (name, description, value) VALUES ('max_daily_duty', 'Maximum allowed duty minutes per 24h period', '720');
