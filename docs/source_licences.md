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

- **Licence (verbatim):** "The AEC has applied the Creative Commons
  Attribution 4.0 International Licence to all material on this website
  with the exception of: the Commonwealth Coat of Arms; AEC's logos;
  AEC's maps; and content supplied by third parties."
- **Required attribution (verbatim):** "© Commonwealth of Australia
  2017"
- **Redistribution status (this project):** ready (for the
  website-content portion only — see the next entry for GIS spatial
  data).
- **Notes:** "Use of material subject to the Licence must not assert
  or imply any connection with, or endorsement by, the AEC unless with
  express prior written permission." (verbatim).
- **Verified at:** https://www.aec.gov.au/footer/copyright.htm —
  directly fetched 2026-04-30 (WebFetch).

## AEC — GIS data (electorate boundaries, electorate-finder spatial layers)

- **Licence (verbatim — grant of licence):** "non-exclusive,
  non-transferable licence" to "load, display, print and reproduce
  views obtained from the Data" and to "develop Derivative Product
  from the Data."
- **Required attribution (verbatim):** "© Commonwealth of Australia
  (Australian Electoral Commission) 2026". For derivative products:
  "This product (XXXX) incorporates data that is: © Commonwealth of
  Australia (Australian Electoral Commission) 2026".
- **Redistribution status (this project):** **needs-follow-up** before
  public redistribution.
- **Notes:** Direct-page review confirms derivative products ARE
  permitted under the licence (with attribution), and licensees may
  "distribute the Data or the Derivative Product to End-users" and
  "sublicense the Licensee's rights outlined in this clause, subject
  to the terms of this Licence." This is friendlier than the prior
  search-only summary suggested. The page also disclaims warranty
  ("gives no warranty regarding the Data's accuracy, completeness,
  currency or suitability for any particular purpose"). Before public
  release a maintainer should still confirm that the project's
  specific use (live tile rendering of polygons + downloadable
  GeoJSON of the same polygons) sits within the "Derivative Product"
  permission.
- **Verified at:** https://www.aec.gov.au/electorates/gis/licence.htm
  and https://www.aec.gov.au/electorates/gis/GIS_Data_Download_Data_Licence.htm —
  directly fetched 2026-04-30 (WebFetch).

## APH (Parliament of Australia)

Covers MP/Senator contacts, House Register of Members' Interests,
Senate Register of Senators' Interests, Hansard, House Votes &
Proceedings, Senate Journals.

- **Licence (verbatim):** "CC BY-NC-ND 4.0 Deed | Attribution-
  NonCommercial-NoDerivs 4.0 International". (Note: the project's
  prior search-only verification listed this as 3.0 Australia; the
  direct-page fetch shows the current version on the APH site is
  the 4.0 International deed. Either way the NC-ND restrictions are
  the load-bearing constraint for this project.)
- **Required attribution (verbatim):** "General content from this
  website should be attributed as _Parliament of Australia website._"
- **Redistribution status (this project):** **needs-follow-up /
  blocked** for derivative or commercial use.
- **Notes:** Direct-page review confirms two binding restrictions:
  (1) "NoDerivs" means no modifications allowed; (2) material is
  restricted to "non-commercial purposes". The page also says users
  are "free to copy and communicate material on this website in its
  current form". Republishing parsed registers of interests as JSON,
  or any modification of MP contact CSV, is a derivative work and is
  NOT permitted under this licence. Any transformation, joining, or
  commercial-adjacent use needs a written exception from the
  Department of the House of Representatives or the Department of
  the Senate (whichever owns the source dataset).
- **Verified at:** https://www.aph.gov.au/Help/Disclaimer_Privacy_Copyright —
  directly fetched 2026-04-30 (WebFetch).

## AIMS Australian Coastline 50K — coastline polygons (eAtlas / NESP MaC)

- **Licence (verbatim, data.gov.au record):** "Licence Not Specified". Each individual resource (Source code GitHub, shapefile downloads — Full / Split / Simplified V1-1, ORCID IDs, PNG, supplementary HTML) is also explicitly tagged "License Not Specified" on the data.gov.au page. The dataset's "Additional Info" block restates: "Licence    Not Specified".
- **Required attribution (verbatim — page-stated provenance, NOT a formal licence-mandated attribution string):** Page metadata attributes the dataset as "Australian Coastline 50K 2024 (NESP MaC 3.17, AIMS)" with "Organisation: Australian Ocean Data Network" and "Contact Point: Australian Ocean Data Network m.hammerton@aims.gov.au". The dataset description names the originating project: "This dataset was created as part of the NESP MaC 3.17 northern Australian Reef mapping project." No formal attribution clause is published on the page because no licence is specified.
- **Redistribution status (this project):** **blocked**. Treat as all-rights-reserved per the project's standing rule that "Licence Not Specified" is conservatively read as no public-redistribution permission until clarified by AIMS / NESP. The eAtlas mirror (https://eatlas.org.au/data/uuid/c0a9c98b-6ca5-4dfd-a96a-d54f30c5b614) returned HTTP 403 on direct fetch on 2026-04-30 and could not be re-verified.
- **Notes:** The project currently uses this layer only as a *display-clip* for the federal map (the official AEC boundary geometry is unchanged). Because the data.gov.au record explicitly lists "Licence Not Specified" — which is a conservative-redistribution flag, not an open licence — substitute with Natural Earth coastline at the same scale (public domain, page-verified above) before public release. The page provides extensive provenance text (Sentinel-2 imagery 2022–2024, NDWI thresholding, 90% of polygons within 20 m of high-resolution imagery, EOT20 tide model) that supports citation but does not grant redistribution rights.
- **Verified at:** https://www.data.gov.au/data/dataset/australian-coastline-50k-2024-nesp-mac-3-17-aims, directly fetched on 2026-04-30 (curl-archived locally; verbatim text extracted from saved HTML). Companion page https://eatlas.org.au/data/uuid/c0a9c98b-6ca5-4dfd-a96a-d54f30c5b614 returned HTTP 403 on the same fetch attempt and remains unconfirmed.
- **Page-fetch status:** successful (data.gov.au); fetch failed HTTP 403 (eatlas.org.au companion page)

## ABS (Australian Bureau of Statistics)

Currently used only for cited datasets (e.g. POA boundaries when the
postcode crosswalk path is wired); ABS Indicator and Data APIs are
also documented as ingestion targets in `docs/data_sources.md`.

- **Licence (verbatim):** "All material presented on this website is
  provided under a Creative Commons Attribution 4.0 International
  licence".
- **Required attribution (verbatim):** "Material obtained from this
  website is to be attributed to this department." Direct-page
  review notes that the page directs users to consult ABS's
  "Attributing ABS material" and "How to cite ABS sources" pages for
  the specific unmodified-vs-modified attribution wording. Until a
  maintainer pulls those pages directly, use the prior search-
  confirmed wording: "Source: Australian Bureau of Statistics" /
  "Source: ABS" if unmodified; "Based on Australian Bureau of
  Statistics data" / "Based on ABS data" if modified or derived.
- **Redistribution status (this project):** ready.
- **Notes:** Excluded from the CC licence (verbatim list from the
  page): the Commonwealth Coat of Arms; the ABS logo; material
  protected by trademark; unit record data (microdata); third-party
  supplied content; sub-brands (DataLab, SEAD); Aboriginal and
  Torres Strait Islander brand artwork; Census branding and artwork;
  OSCA branding and artwork. Pin the version year of the dataset
  used (e.g. ASGS 2021 POA) in the citation.
- **Verified at:** https://www.abs.gov.au/website-privacy-copyright-and-disclaimer —
  directly fetched 2026-04-30 (WebFetch).

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

- **Licence (verbatim — Grant of License + No Commercial Derivative Work, from /terms/):** "The Services provided to the Customer, including third-party content, are licensed to the Customer, not sold. All worldwide intellectual property and proprietary rights therein and related thereto, including, without limitation, all patents, copyrights, trademarks, trade secrets, moral rights, sui generis rights and other right in databases, and all rights arising from or pertaining to the foregoing rights, are and will remain the exclusive property of MapTiler or respective third-party supplier(s). MapTiler reserves all rights not expressly granted." And: "You may not resell or redistribute, rent, lease, lend, sell or sublicense our Products or any part thereof without a written agreement from MapTiler." And: "Beyond what is specified in the Terms or agreed between you and MapTiler in a custom license, you may not produce commercial derivative works from MapTiler Services. This includes, but is not limited to, the training of machine learning algorithms for feature extraction or any other purpose; or to improve the accuracy of other satellite imagery via algorithmic processing or any other method. The production of derivative vector datasets for non-commercial purposes or for OpenStreetMap is permitted." And: "It is expressly prohibited to manipulate or modify map content, in the form of vectors, pixels or underlying metadata."
- **Required attribution (verbatim — from /copyright/ and /terms/):** From the copyright page: "Our maps must always visibly show attributtion: © MapTiler © OpenStreetMap contributors". From the Terms section 6 ("Map Data Attribution"): "When using Map Content, the Customer is required to add '© MapTiler' (with Free Account the MapTiler logo) when displaying maps. This should hyperlink to https://www.maptiler.com/copyright/" — and — "If the Map Data being used is based on OpenStreetMap data, the Customer is required to add '© OpenStreetMap' when displaying maps. This should hyperlink to: https://www.openstreetmap.org/copyright". On attribution visibility: "The attribution must always be visible and readable on any screen or medium. On small screens (mobile phones), the attribution may be available behind a contextual popup window displaying only the attribution itself - openable with one click/tap from a map."
- **Redistribution status (this project):** ready for runtime use only; redistribution blocked.
- **Notes:** Tiles must be requested live from MapTiler servers per their terms — do NOT cache or rehost tiles. The frontend already carries the visible "© MapTiler © OpenStreetMap contributors" attribution. The /copyright/ page also identifies many country-specific upstream sources (e.g. UK OS Crown copyright, swisstopo, ESA Copernicus, Maxar, USGS, NLS Finland CC BY 4.0, NSW Spatial Services 2023, IGN France, CC0 jurisdictions) — each carries its own attribution string that MapTiler aggregates under the single "© MapTiler" credit per its written agreement with MapTiler AG.
- **Verified at:** https://www.maptiler.com/copyright/ and https://www.maptiler.com/terms/, directly fetched on 2026-04-30 (curl-archived locally; verbatim text extracted from saved HTML).
- **Page-fetch status:** successful

## OpenStreetMap — base data behind MapTiler

- **Licence (verbatim):** "OpenStreetMap is open data, licensed under the Open Data Commons Open Database License (ODbL) by the OpenStreetMap Foundation (OSMF). In summary: You are free to copy, distribute, transmit and adapt our data, as long as you credit OpenStreetMap and its contributors. If you alter or build upon our data, you may distribute the result only under the same license. The full legal code at Open Data Commons explains your rights and responsibilities. Our documentation is licensed under the Creative Commons Attribution-ShareAlike 2.0 license (CC BY-SA 2.0)."
- **Required attribution (verbatim):** "Where you use OpenStreetMap data, you are required to do the following two things: Provide credit to OpenStreetMap by displaying our attribution notice. Make clear that the data is available under the Open Database License." Also: "Generally speaking, to make clear that the data is available under the Open Database License, you may link to this copyright page. If you are distributing OSM in data form, please name and link directly to the license(s). In media where links are not possible (e.g. printed works), please include the full URL on the page, e.g. https://www.openstreetmap.org/copyright."
- **Redistribution status (this project):** ready, with share-alike conditions if redistributing OSM-derived data.
- **Notes:** Displaying MapTiler tiles inherits the OSM attribution requirement. The OSM page also notes Australia-specific upstream provenance: "Incorporates or developed using Administrative Boundaries © Geoscape Australia licensed by the Commonwealth of Australia under Creative Commons Attribution 4.0 International licence (CC BY 4.0)." If this project extracts OSM features into its own database, the share-alike clause attaches and any redistributed database must itself be ODbL-licensed.
- **Verified at:** https://www.openstreetmap.org/copyright, directly fetched on 2026-04-30 (curl-archived locally; verbatim text extracted from saved HTML).
- **Page-fetch status:** successful

## Natural Earth — fallback country/coastline boundaries

- **Licence (verbatim):** "All versions of Natural Earth raster + vector map data found on this website are in the public domain. You may use the maps in any manner, including modifying the content and design, electronic dissemination, and offset printing. The primary authors, Tom Patterson and Nathaniel Vaughn Kelso, and all other contributors renounce all financial claim to the maps and invites you to use them for personal, educational, and commercial purposes. No permission is needed to use Natural Earth. Crediting the authors is unnecessary."
- **Required attribution (verbatim):** None required. The page states crediting is "unnecessary" but offers two suggested citations: short text — "Made with Natural Earth."; long text — "Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com."
- **Redistribution status (this project):** ready.
- **Notes:** The page also disclaims warranty: "The authors provide Natural Earth as a public service and are not responsible for any problems relating to accuracy, content, design, and how it is used." Several upstream third-party data releases are quoted on the page (The Washington Post, EC JRC IES, XNR Productions, International Mapping Associates, Wikidata CC0); each is a non-exclusive licence to Natural Earth for the sole purpose of creating a world base map. Pin the scale used (1:10m, 1:50m, or 1:110m).
- **Verified at:** https://www.naturalearthdata.com/about/terms-of-use/, directly fetched on 2026-04-30 (curl-archived locally; verbatim text extracted from saved HTML).
- **Page-fetch status:** successful

## Australia Post — postcode locality CSV (verbatim from product page)

Considered as a comprehensive seed source for postcode-electorate
crosswalk expansion; explicitly **NOT** ingested at this time.

The original `/about-us/about-our-site/our-licensing-arrangements`
URL returns a 404 in 2026 (the page has moved or been retired). The
canonical free-tier product page is now at
https://postcode.auspost.com.au/free_display.html?id=1 and that
page's title is literally "Non-commercial use only". Verbatim text
below is from that page (Batch I direct-fetch, 2026-05-01).

- **Licence (verbatim):** "The contents of the Database are subject
  to change without notice and remain at all times the property of
  Australia Post."
- **Required attribution:** No specific attribution requirement is
  stated on the product page; Australia Post retains all property
  rights and prohibits reproduction without permission (verbatim
  prohibition wording captured below).
- **Redistribution status (this project):** **blocked**.
- **Notes (verbatim restrictions from the product page):**
  - "The user must not use the Postcode Booklet for the benefit of
    any third party, for reward or to commercialise in any way."
  - "To sub-license, sell, lend, rent, transfer, lease or grant any
    rights for the Postcode Booklet to any person, company,
    organisation, agency, or business entity."
  - "To create a Product or other derivative works from Postcode
    Booklet."
  - "To combine, embed, alter or modify the Postcode Booklet with or
    in other products, software or systems."

  Public-readable summary: this source cannot be embedded in any
  publicly redistributed dataset or used to power a public postcode
  finder. Do **not** seed this project's postcode list from the free
  Australia Post CSV. Use ABS POA boundaries + the AEC's own
  postcode finder + community-curated CC0 lists (e.g. Matthew
  Proctor's Australian-postcodes CC0 dataset on GitHub — see
  `docs/data_sources.md`) as alternative seed sources.
- **Verified at:** https://postcode.auspost.com.au/free_display.html?id=1
  — directly fetched 2026-05-01 (WebFetch; product page returned
  verbatim restriction wording). The historic
  `/about-us/about-our-site/our-licensing-arrangements` URL is a
  404 as of 2026-05-01.
- **Page-fetch status:** successful (current canonical product page).

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
4. **AIMS Coastline 50K** is now confirmed verbatim as
   "Licence Not Specified" on the data.gov.au record (the eAtlas
   companion page returned HTTP 403 in the 2026-04-30 verification
   round). Status is now **blocked** for public redistribution, not
   just needs-follow-up: an unspecified licence is conservatively
   treated as all-rights-reserved. Substitute with Natural Earth
   coastline (public domain) before any public release.
5. **Direct-page verification status (2026-05-01 round).** All ten
   sources now carry verbatim direct-fetch licence wording:
   AEC website (CC-BY 4.0), AEC GIS (Limited End-user Licence with
   derivative-product permission), APH (CC BY-NC-ND 4.0
   International), ABS (CC-BY 4.0), AIMS Coastline 50K
   (verbatim "Licence Not Specified" via data.gov.au), TVFY (ODbL),
   MapTiler ×2 (proprietary), OSM (ODbL), Natural Earth (public
   domain), and Australia Post (verbatim non-commercial-only
   restriction wording from the canonical product page at
   `postcode.auspost.com.au/free_display.html?id=1`; the historic
   `auspost.com.au/about-us/.../our-licensing-arrangements` URL is a
   404 as of 2026-05-01 and has been retired). The only remaining
   browser-fetch follow-up is the eAtlas companion of AIMS Coastline
   50K, whose origin returns HTTP 403 to plain HTTP clients and
   whose Wayback Machine snapshot is the SPA shell only — but the
   data.gov.au record alone is sufficient because its verbatim
   "Licence Not Specified" already drives the conservative blocked
   status.

The project's general public-redistribution policy continues to be
"conservative until verified". Local development and reproducibility
do not require these clearances; public data release does.
