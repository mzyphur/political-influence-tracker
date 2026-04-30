# Source Licences and Public-Redistribution Status

Last updated: **2026-04-30**

This document records the licence status of every public data source the
project ingests, plus the verbatim attribution wording, redistribution
restrictions, and the project's redistribution status for each. Items
marked **needs-follow-up** must be reverified directly against the
publisher's licence page (not search-snippet excerpts) before any
public data redistribution.

The project's standing rule, also recorded in `CLAUDE.md` and
`docs/reproducibility.md`: use the conservative wording *"official
public <agency> snapshot; public redistribution / licence terms to be
recorded before public data redistribution"* until a source's licence
is verified directly. Local development is OK; **public
redistribution requires verified terms captured here**.

## Verification methodology (2026-04-30)

The status of each source below was sourced from a WebSearch-only
verification pass on the publisher's stated licence page. WebSearch
returns content excerpts, not full page text — so every claim below is
*"search-confirmed at the cited URL, requires direct page review
before publication"*. Before any public data release, a maintainer
must:

1. Open each cited URL.
2. Replace any quoted/paraphrased licence and attribution wording with
   the verbatim text from the live page.
3. Mark each entry's `Verified at` line with the new date.

A future automation could be a small shell script that re-fetches each
URL via `curl -s` and `diff`s the SHA256 of the licence section, but
that's a maintenance enhancement, not a precondition for a first
public release.

---

## AEC (Australian Electoral Commission) — website content

Covers the Transparency Register, Register of Entities, public
funding records, and the Electorate Finder result pages.

- **Licence:** Creative Commons Attribution 4.0 International
  (CC-BY 4.0), with exceptions for the Commonwealth Coat of Arms,
  AEC logos, and third-party content.
- **Required attribution:** "© Commonwealth of Australia (Australian
  Electoral Commission)" plus a CC-BY 4.0 attribution statement.
- **Redistribution status (this project):** ready (for the
  website-content portion only).
- **Notes:** Does NOT cover GIS spatial data — see the next entry for
  electorate-boundary GIS terms. Confirm that any specific
  Transparency Register download page does not carry a stricter
  clause.
- **Verified at:** https://www.aec.gov.au/footer/copyright.htm —
  search-confirmed 2026-04-30, requires direct page re-read before
  publication.

## AEC — GIS data (electorate boundaries, electorate-finder spatial layers)

- **Licence:** Limited End-user Licence (proprietary). Allows
  load/display/print/reproduce for personal use or use within your
  organisation only. Creating "Derivative Products" in which the data
  is altered, abridged, or supplemented is prohibited. Required
  notice: "© Commonwealth of Australia (Australian Electoral
  Commission) [year]".
- **Required attribution:** "© Commonwealth of Australia (Australian
  Electoral Commission) [year]".
- **Redistribution status (this project):** **needs-follow-up** before
  public redistribution.
- **Notes:** Hosting the AEC's electorate boundary geometry as part of
  this project's public map likely qualifies as creating a derivative
  product and may exceed the limited licence. Options: request
  written permission from AEC, substitute with a redistribution-
  friendly equivalent (e.g. ABS POA + ABS-published electorate
  geographies), or restrict the public site to point-in-polygon look-
  ups against AEC servers rather than redistributing the geometry.
- **Verified at:** https://www.aec.gov.au/electorates/gis/licence.htm
  and https://www.aec.gov.au/electorates/gis/GIS_Data_Download_Data_Licence.htm —
  search-confirmed 2026-04-30, requires direct page re-read before
  publication.

## APH (Parliament of Australia)

Covers MP/Senator contacts, House Register of Members' Interests,
Senate Register of Senators' Interests, Hansard, House Votes &
Proceedings, Senate Journals.

- **Licence:** Creative Commons Attribution-NonCommercial-NoDerivatives
  3.0 Australia (CC BY-NC-ND 3.0 AU).
- **Required attribution:** "© Commonwealth of Australia" with a link
  to the licence deed at
  https://creativecommons.org/licenses/by-nc-nd/3.0/au/
- **Redistribution status (this project):** **needs-follow-up /
  blocked** for derivative or commercial use.
- **Notes:** NC-ND restrictions are material. Republishing parsed
  registers of interests as JSON, or any modification of MP contact
  CSV, is a derivative work and is NOT permitted under this licence.
  If the project is non-commercial AND publishes verbatim files only,
  attribution may suffice. Any transformation, joining, or
  commercial-adjacent use needs a written exception from the
  Department of the House of Representatives or the Department of the
  Senate (whichever owns the source dataset).
- **Verified at:** https://www.aph.gov.au/Help/Disclaimer_Privacy_Copyright —
  search-confirmed 2026-04-30, requires direct page re-read.

## AIMS Australian Coastline 50K — coastline polygons (eAtlas / NESP MaC)

- **Licence:** Not confirmed in this verification round. The eAtlas
  catalogue listing has historically been recorded as "Not Specified"
  in this project. The data.gov.au record ("Australian Coastline 50K
  2024 NESP MaC 3.17, AIMS") exists but the explicit licence string
  was not surfaced in the search-only verification pass.
- **Required attribution:** Unknown. Tentative: "Australian Institute
  of Marine Science (AIMS) — Australian Coastline 50K, NESP Marine
  and Coastal Hub Project 3.17", pending confirmation.
- **Redistribution status (this project):** **needs-follow-up** before
  public redistribution. Treat as all-rights-reserved if the
  catalogue still lists "Not Specified".
- **Notes:** The project currently uses this layer only as a
  *display-clip* for the federal map (the official AEC boundary
  geometry is unchanged). Substitute with Natural Earth coastline at
  the same scale if the AIMS terms cannot be cleared.
- **Verified at:** https://eatlas.org.au/data/uuid/c0a9c98b-6ca5-4dfd-a96a-d54f30c5b614
  and https://www.data.gov.au/data/dataset/australian-coastline-50k-2024-nesp-mac-3-17-aims —
  search-only, 2026-04-30; needs direct page review.

## ABS (Australian Bureau of Statistics)

Currently used only for cited datasets (e.g. POA boundaries when the
postcode crosswalk path is wired); ABS Indicator and Data APIs are
also documented as ingestion targets in `docs/data_sources.md`.

- **Licence:** Creative Commons Attribution 4.0 International
  (CC BY 4.0), with exceptions for the Commonwealth Coat of Arms,
  ABS logo, trademarks, unit-record microdata, and third-party
  content.
- **Required attribution:** "Source: Australian Bureau of Statistics"
  or "Source: ABS" if unmodified; "Based on Australian Bureau of
  Statistics data" or "Based on ABS data" if modified or derived.
- **Redistribution status (this project):** ready.
- **Notes:** Pin the version year of the dataset (e.g. ASGS 2021 POA)
  in the citation. Standard CC-BY notice (link to licence) must
  accompany the data.
- **Verified at:** https://www.abs.gov.au/website-privacy-copyright-and-disclaimer —
  search-confirmed 2026-04-30.

## They Vote For You (TVFY / OpenAustralia) — divisions API

- **Licence:** Open Data Commons Open Database License (ODbL) —
  attribution + share-alike.
- **Required attribution:** Reference and hyperlink to
  https://theyvoteforyou.org.au/, plus a notice such as "This data is
  made available under the Open Database License:
  https://opendatacommons.org/licenses/odbl/1.0/".
- **Redistribution status (this project):** ready, with conditions.
- **Notes:** Share-alike is binding. Any database produced from TVFY
  data and published must itself be ODbL-licensed (or compatible).
  If the project's combined dataset mixes TVFY with non-share-alike
  sources, separate the TVFY-derived layer in the redistribution
  package or document the share-alike scope clearly.
- **Verified at:** https://theyvoteforyou.org.au/help/licencing —
  search-confirmed 2026-04-30.

## MapTiler — map tiles

- **Licence:** Proprietary commercial terms. Bulk/batch tile download
  and stitching are prohibited; resale, sublicence, and
  redistribution are prohibited without a written agreement.
- **Required attribution:** "© MapTiler" hyperlinked to
  https://www.maptiler.com/copyright/, always visible in the map UI
  (mobile may use a one-tap popup). On the Free Account tier the
  MapTiler logo must also be visible.
- **Redistribution status (this project):** ready for runtime use only;
  redistribution blocked.
- **Notes:** Tiles must be requested live from MapTiler servers per
  their terms — do NOT cache or rehost tiles. The frontend already
  carries the visible "© MapTiler © OpenStreetMap contributors"
  attribution.
- **Verified at:** https://www.maptiler.com/copyright/ and
  https://www.maptiler.com/terms/ — search-confirmed 2026-04-30.

## OpenStreetMap — base data behind MapTiler

- **Licence:** Open Database License (ODbL). Pre-2012-09-12 data also
  available under CC-BY-SA 2.0.
- **Required attribution:** "© OpenStreetMap contributors" with a
  hyperlink to https://www.openstreetmap.org/copyright. For databases
  derived from OSM, include the ODbL text or a link to it in a
  discoverable location (readme/metadata).
- **Redistribution status (this project):** ready, with share-alike
  conditions if redistributing OSM-derived data.
- **Notes:** Displaying MapTiler tiles inherits the OSM attribution
  requirement. If the project also extracts OSM features into its own
  database, the share-alike clause attaches.
- **Verified at:** https://www.openstreetmap.org/copyright —
  search-confirmed 2026-04-30.

## Natural Earth — fallback country/coastline boundaries

- **Licence:** Public domain. No permission required, attribution is
  "unnecessary" but suggested.
- **Required attribution:** None required. Suggested citation: "Made
  with Natural Earth. Free vector and raster map data @
  naturalearthdata.com."
- **Redistribution status (this project):** ready.
- **Notes:** Cleanest option for a redistributable boundary fallback.
  Pin the scale used (1:10m, 1:50m, or 1:110m).
- **Verified at:** https://www.naturalearthdata.com/about/terms-of-use/ —
  search-confirmed 2026-04-30.

## Australia Post — postcode locality CSV

Considered as a comprehensive seed source for postcode-electorate
crosswalk expansion; explicitly **NOT** ingested at this time.

- **Licence:** Limited, revocable, non-exclusive licence to download
  and use postcodes for non-commercial reference only. Commercial
  use requires a paid licence. Sub-licensing, sale, redistribution,
  or use to power any publicly available postcode lookup is expressly
  prohibited.
- **Required attribution:** Australia Post retains all property
  rights; reproduction without permission is prohibited.
- **Redistribution status (this project):** **blocked**.
- **Notes:** This source cannot be embedded in a publicly redistributed
  dataset or used to power a public postcode finder. Do **not** seed
  this project's postcode list from the free Australia Post CSV. Use
  ABS POA boundaries + the AEC's own postcode finder + community-
  curated CC0 lists (e.g. Matthew Proctor's Australian-postcodes
  CC0 dataset on GitHub) as alternative seed sources, and document
  the choice here before running the bulk fetch.
- **Verified at:** https://auspost.com.au/about-us/about-our-site/our-licensing-arrangements —
  search-confirmed 2026-04-30.

---

## Project-level redistribution implications

These are the load-bearing observations a maintainer must resolve
before any public data release:

1. **APH BY-NC-ND 3.0 AU is the biggest blocker.** Parsing the
   registers of interests into structured records is, on its face, a
   derivative work; surfacing them publicly with any commercial
   element conflicts with NC. Land an explicit written exception
   from the Department of the House and the Department of the Senate
   before publication, OR limit the public surface to verbatim PDFs
   plus links and remove the parsed records from the public API.
2. **AEC GIS data** is a Limited End-user Licence, not CC-BY. Public
   hosting of the polygon geometry as a redistributable artefact is
   likely outside the licence. The current project displays the
   polygons as a runtime layer rendered from a private server; this
   is closer to "use within your organisation" but still warrants a
   written confirmation from AEC before public launch.
3. **Australia Post** is non-commercial reference only and explicitly
   blocks public postcode lookups. Do NOT seed the postcode crosswalk
   from this source.
4. **AIMS Coastline 50K** licence string was not confirmed in this
   verification round. Read directly off the eAtlas / data.gov.au
   record and either capture the licence verbatim here or substitute
   with Natural Earth before any public release.
5. **WebSearch verification is not a substitute for direct page
   review.** Every entry above carries a 2026-04-30 search-confirm
   stamp; before publication, replace each `Verified at` line with a
   live-fetched timestamp + verbatim licence string.

The project's general public-redistribution policy continues to be
"conservative until verified". Local development and reproducibility
do not require these clearances; public data release does.
