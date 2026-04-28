# Frontend

React/Vite interface for the Australian Political Influence Explorer.

The first usable screen is the national map explorer:

- `/api/map/electorates` supplies electorate GeoJSON-style features.
- `/api/search` supplies global search results.
- MapTiler supplies the basemap through `VITE_MAPTILER_API_KEY`.
- The government-level selector includes Federal, State, and Council scopes.
  Federal/Commonwealth is active now; State and Council are visible planned
  expansion scopes until their ingestion layers are built.
- Federal House maps use electorate geometries. Federal Senate maps use
  state/territory composite geometries derived from source-backed House
  boundaries, with senator data from Senate office records.
- The frontend requests low-tolerance boundary geometry
  (`simplify_tolerance=0.0005`) because high per-electorate simplification
  creates visible cracks between neighbouring polygons. Exact source geometry
  remains available from the API with `simplify_tolerance=0`.
- `/api/coverage` supplies whole-database coverage counts and attribution caveats
  so users can distinguish map-linked representative records from broader
  party/entity/return-level money-flow records.
- `/api/representatives/{person_id}` supplies the side panel's selected
  representative record feed, including money, benefits, private interests,
  organisational roles, and other person-linked disclosed records.
- `/api/entities/{entity_id}` supplies search-result entity drilldowns for
  donors, companies, party/associated-entity records, and other parsed
  source/recipient entities that should not be forced onto one MP without
  explicit evidence.
- Representative record rows can be filtered by record family and expanded to
  show source links, source refs, evidence/review status, amount status, and
  missing-data flags.
- Clicking a representative opens a public contact details popup. The popup uses
  APH contact CSV phone/address fields and APH contact-list PDF email fields
  when the official PDF exposes an email; otherwise it shows the official APH
  profile/search link rather than inferring an email.
- House map fills and panel accents use explicit party short-code colors for the
  party codes currently present in the database. Senate map fills use
  state/territory colors because each Senate feature is multi-member.

## Local Development

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` and `/health` to `VITE_API_BASE_URL`, which
defaults to `http://127.0.0.1:8008`.

Create a local ignored env file when needed:

```bash
cp .env.example .env.local
```

`VITE_MAPTILER_API_KEY` is a browser-exposed map key. Keep private server-side
keys in `backend/.env`; only use frontend-safe map keys here.

## Build

```bash
npm run build
```
