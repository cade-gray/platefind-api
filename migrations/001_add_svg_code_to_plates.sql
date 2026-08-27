-- Adds a column to hold the hand-authored SVG markup for each plate's design.
-- Nullable: a plate row exists before its design has been drawn.
ALTER TABLE plates ADD COLUMN IF NOT EXISTS svg_code TEXT;
