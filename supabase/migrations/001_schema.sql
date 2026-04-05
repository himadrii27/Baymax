-- Baymax Personal AI - Supabase Schema
-- Run this in your Supabase SQL Editor

-- Enable pgvector for Mem0 semantic memory
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────
-- Identity Profile (who you are)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS identity_profile (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  category TEXT CHECK (category IN ('personal', 'professional', 'health', 'preferences')),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────
-- Conversation History
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations (session_id, created_at DESC);

-- ─────────────────────────────────────────
-- Medications (what you take)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medications (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  dosage TEXT,
  schedule_times TEXT[],   -- e.g. ARRAY['08:00', '20:00']
  notes TEXT,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- ─────────────────────────────────────────
-- Medication Logs (every dose taken)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS medication_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  medication_id UUID REFERENCES medications(id) ON DELETE CASCADE,
  taken_at TIMESTAMPTZ DEFAULT now(),
  dose_taken TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_med_logs_med_time ON medication_logs (medication_id, taken_at DESC);

-- ─────────────────────────────────────────
-- Health Logs (BP, weight, mood, symptoms, sleep, exercise)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS health_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  log_type TEXT NOT NULL CHECK (log_type IN ('bp', 'weight', 'sleep', 'mood', 'symptom', 'exercise', 'checkin')),
  value JSONB NOT NULL,
  -- bp:      {"systolic": 120, "diastolic": 80}
  -- weight:  {"kg": 72.5}
  -- sleep:   {"hours": 7.5, "quality": 7}
  -- mood:    {"score": 7, "notes": "anxious"}
  -- symptom: {"name": "headache", "severity": 5}
  -- exercise:{"type": "walk", "minutes": 30}
  notes TEXT,
  logged_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_health_logs_type_time ON health_logs (log_type, logged_at DESC);

-- ─────────────────────────────────────────
-- Tasks
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'done')),
  due_date DATE,
  priority INT DEFAULT 3 CHECK (priority BETWEEN 1 AND 4),
  -- 1=urgent, 2=high, 3=normal, 4=low
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks (status, priority, due_date);

-- Auto-update updated_at on tasks
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────
-- Period Cycles
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS period_cycles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  start_date DATE NOT NULL,
  end_date DATE,                        -- null until period ends
  cycle_length INT,                     -- calculated: days from prev start to this start
  period_length INT,                    -- calculated: end_date - start_date
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_period_cycles_start ON period_cycles (start_date DESC);

-- ─────────────────────────────────────────
-- Period Daily Logs (symptoms per day)
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS period_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  log_date DATE NOT NULL DEFAULT CURRENT_DATE,
  cycle_id UUID REFERENCES period_cycles(id) ON DELETE CASCADE,
  flow TEXT CHECK (flow IN ('spotting', 'light', 'medium', 'heavy', 'none')),
  symptoms TEXT[],
  -- e.g. ARRAY['cramps', 'bloating', 'headache', 'mood_swings', 'fatigue',
  --            'cravings', 'breast_tenderness', 'back_pain', 'nausea', 'acne']
  mood TEXT,                            -- free text: "irritable", "sad", "anxious"
  pain_level INT CHECK (pain_level BETWEEN 1 AND 10),
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_period_logs_date ON period_logs (log_date DESC);
