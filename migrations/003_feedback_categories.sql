-- Migration 003: Tiered feedback support
-- Adds category breakdown to user_feedback (e.g. ['inaccurate', 'too_long']).

ALTER TABLE user_feedback
  ADD COLUMN IF NOT EXISTS categories JSON;
