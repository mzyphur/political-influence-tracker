# Draft: Public-redistribution clarification — Australian Electoral Commission GIS data

**Status:** Draft for the project lead to review, sign, and send.
Saved in the repository so the request and any reply are auditable.

**Project context:** The Australian Political Influence Transparency
project ingests the AEC's federal electorate boundary geometry as a
display layer for its public map. The project's per-source licence
audit at [`docs/source_licences.md`](../source_licences.md) records
that AEC GIS data is published under the AEC's separate **Limited
End-user Licence**:

> "non-exclusive, non-transferable licence" to "load, display, print
> and reproduce views obtained from the Data" and to "develop
> Derivative Product from the Data."

The project's direct-page review confirmed that the licence DOES
permit derivative products with the documented attribution string
("© Commonwealth of Australia (Australian Electoral Commission)
[year]") and DOES permit licensees to "distribute the Data or the
Derivative Product to End-users" and "sublicense the Licensee's
rights outlined in this clause, subject to the terms of this
Licence." This is friendlier than the project's earlier search-only
verification round had suggested.

Before the project's first public release we'd appreciate written
confirmation from the AEC clarifying whether the project's specific
use sits within the "Derivative Product" permission. The project:

1. Renders the boundary polygons as a runtime map layer to the
   public app's users (the polygons are served as GeoJSON / vector
   tiles from a private server the project operates).
2. Re-projects the boundaries from the AEC's published shapefile CRS
   to GeoJSON / PostGIS SRID 4326 with optional simplification for
   interactive responsiveness.
3. Clips a display-only overlay against AIMS Coastline 50K (display-
   only; the official AEC boundary geometry is unchanged in
   storage). NOTE: the AIMS layer is itself a separate
   redistribution issue — the project is substituting Natural Earth
   coastline before public release because AIMS lists the licence as
   "Not Specified".
4. Carries the verbatim attribution string under "© Commonwealth of
   Australia (Australian Electoral Commission) [year]" with a link
   to https://www.aec.gov.au/electorates/gis/licence.htm.

We treat this combined treatment as a Derivative Product within the
licence's permission. We'd appreciate AEC confirmation of either
that interpretation, or any specific conditions the AEC would like
us to add.

## Suggested addressee

- AEC GIS Section / AEC Electorate Mapping
  Australian Electoral Commission
  Locked Bag 4007, Canberra ACT 2601

## Suggested wording

> Dear Sir / Madam,
>
> I am the lead on the Australian Political Influence Transparency
> project, a public-interest source-backed transparency tool that
> publishes a reproducible link from disclosed federal political
> records back to the original public source documents.
>
> The project ingests the AEC's federal electorate boundary
> shapefile and serves it as a runtime map layer in the project's
> public app. Specifically:
>
> - We download the official current national federal electorate
>   ESRI shapefile from
>   `https://www.aec.gov.au/electorates/gis/...`;
> - We re-project the geometry from GDA94 to EPSG:4326 (GeoJSON /
>   PostGIS) and serve it as vector tiles from a server the project
>   operates;
> - The public app renders those tiles with the verbatim attribution
>   "© Commonwealth of Australia (Australian Electoral Commission)
>   [year]", linked to the AEC GIS licence page;
> - The AEC's official boundary geometry is unchanged in storage
>   (the only display-time variation is a coastline clip layered on
>   top, sourced separately).
>
> We treat this combined treatment as a Derivative Product within
> the AEC's GIS End-user Licence permission. Could the AEC please
> confirm:
>
> 1. Whether the AEC considers our re-projected, vector-tiled,
>    publicly-served treatment of the boundary geometry a
>    Derivative Product within the meaning of the End-user Licence;
> 2. Whether the AEC's standard attribution string suffices, or
>    whether the AEC would like an additional or different
>    attribution form;
> 3. Whether the AEC has any other conditions the project should
>    apply before public launch (we explicitly preserve the warranty
>    disclaimer the licence states; we do not assert AEC endorsement
>    in any UI surface; and we link the original AEC source
>    documents alongside the rendered map).
>
> Our reproducibility policy is at `docs/reproducibility.md` in the
> project repository, and the per-source licence audit is at
> `docs/source_licences.md`. We would welcome any conditions the
> AEC considers appropriate.
>
> Yours faithfully,
>
> [Project lead]

## Action item for the project lead

1. Sign the letter, send via the AEC's standard correspondence
   channel.
2. Save the reply under `docs/letters/replies/` once received,
   with the licence-status update applied to
   `docs/source_licences.md`.
