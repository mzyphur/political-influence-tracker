CREATE UNIQUE INDEX IF NOT EXISTS electorate_boundary_unique_idx
    ON electorate_boundary (electorate_id, boundary_set);
