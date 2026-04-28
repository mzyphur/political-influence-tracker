CREATE TABLE IF NOT EXISTS display_land_mask (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    country_name TEXT NOT NULL,
    geometry_role TEXT NOT NULL,
    geom GEOMETRY(MultiPolygon, 4326),
    source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS display_land_mask_geom_idx
    ON display_land_mask USING gist (geom);

CREATE TABLE IF NOT EXISTS electorate_boundary_display_geometry (
    id BIGSERIAL PRIMARY KEY,
    electorate_boundary_id BIGINT NOT NULL REFERENCES electorate_boundary(id) ON DELETE CASCADE,
    geometry_role TEXT NOT NULL,
    geom GEOMETRY(MultiPolygon, 4326),
    clip_source_document_id BIGINT REFERENCES source_document(id),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (electorate_boundary_id, geometry_role)
);

CREATE INDEX IF NOT EXISTS electorate_boundary_display_geometry_geom_idx
    ON electorate_boundary_display_geometry USING gist (geom);
