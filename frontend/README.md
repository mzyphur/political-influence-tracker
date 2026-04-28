# Frontend

React/Vite interface for the Australian Political Influence Explorer.

The first usable screen is the national map explorer:

- `/api/map/electorates` supplies electorate GeoJSON-style features.
- `/api/search` supplies global search results.
- MapTiler supplies the basemap through `VITE_MAPTILER_API_KEY`.

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
