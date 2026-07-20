-- Migration: Add waiver acknowledgment columns to user table
-- Run once on the production database

ALTER TABLE user ADD COLUMN waiver_emergency_cohousing BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE user ADD COLUMN waiver_end_of_life_wishes VARCHAR(100);
ALTER TABLE user ADD COLUMN waiver_senior_ack BOOLEAN NOT NULL DEFAULT 0;
