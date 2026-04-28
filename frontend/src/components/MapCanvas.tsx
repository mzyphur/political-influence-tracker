import { useEffect, useRef } from "react";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import maplibregl, {
  type LayerSpecification,
  type LngLatBoundsLike,
  type MapLayerMouseEvent
} from "maplibre-gl";
import { featureCollection, mapStyleUrl } from "../map";
import type { ElectorateFeature } from "../types";

type MapCanvasProps = {
  features: ElectorateFeature[];
  selectedFeature: ElectorateFeature | null;
  initialBounds: LngLatBoundsLike;
  onSelectFeature: (feature: ElectorateFeature) => void;
};

const sourceId = "electorates";
const detailSourceId = "electorate-detail-components";
const fillLayerId = "electorate-fills";
const detailFillLayerId = "electorate-detail-fills";
const lineLayerId = "electorate-lines";
const detailLineLayerId = "electorate-detail-lines";
const selectedHaloLayerId = "selected-electorate-halo";
const selectedDetailHaloLayerId = "selected-electorate-detail-halo";
const selectedLayerId = "selected-electorate";
const selectedDetailLayerId = "selected-electorate-detail";
const detailComponentMinZoom = 5.25;
const minorComponentAreaThresholdSqKm = 120;
type LinePaint = NonNullable<Extract<LayerSpecification, { type: "line" }>["paint"]>;
type FillPaint = NonNullable<Extract<LayerSpecification, { type: "fill" }>["paint"]>;
type DisplayProperties = ElectorateFeature["properties"] & {
  map_component_area_hint: number;
  map_component_count: number;
  map_component_index: number;
};
type ComponentMode = "major" | "minor";
const selectionLayerIds = [
  selectedHaloLayerId,
  selectedDetailHaloLayerId,
  selectedLayerId,
  selectedDetailLayerId
];
const fillLayerIds = [fillLayerId, detailFillLayerId];
const electorateFillColor: FillPaint["fill-color"] = [
  "case",
  ["==", ["get", "chamber"], "senate"],
  [
    "match",
    ["get", "state_or_territory"],
    "ACT",
    "#7c3aed",
    "NSW",
    "#00a3e0",
    "NT",
    "#f97316",
    "QLD",
    "#ef4444",
    "SA",
    "#8b5cf6",
    "TAS",
    "#10b981",
    "VIC",
    "#2563eb",
    "WA",
    "#f59e0b",
    "#64748b"
  ],
  [
    "match",
    ["get", "party_short_name"],
    "ALP",
    "#f04438",
    "LP",
    "#1769e0",
    "LNP",
    "#0b5fd3",
    "NATS",
    "#21a857",
    "Nats",
    "#21a857",
    "AG",
    "#00a651",
    "IND",
    "#00a6a6",
    "ON",
    "#ff6b00",
    "UAP",
    "#ffd400",
    "JLN",
    "#8b5cf6",
    "KAP",
    "#c2410c",
    "CLP",
    "#0064b7",
    "CA",
    "#14b8d4",
    "AV",
    "#2dd4bf",
    "#64748b"
  ]
] as unknown as FillPaint["fill-color"];
const componentLineOpacity: LinePaint["line-opacity"] = 0.5;
const selectedComponentHaloOpacity: LinePaint["line-opacity"] = 0.92;
const selectedComponentStrokeOpacity: LinePaint["line-opacity"] = 1;
const selectedHaloWidth: LinePaint["line-width"] = [
  "interpolate",
  ["exponential", 1.2],
  ["zoom"],
  1.5,
  1,
  2.5,
  1.5,
  3,
  2.2,
  4.5,
  3,
  6,
  4.2,
  8,
  5.8,
  10,
  7.2,
  12,
  8.4
];
const selectedStrokeWidth: LinePaint["line-width"] = [
  "interpolate",
  ["exponential", 1.2],
  ["zoom"],
  1.5,
  0.45,
  2.5,
  0.75,
  3,
  1.1,
  4.5,
  1.6,
  6,
  2.4,
  8,
  3.4,
  10,
  4.4,
  12,
  5.2
];
const selectedHaloBlur: LinePaint["line-blur"] = [
  "interpolate",
  ["linear"],
  ["zoom"],
  1.5,
  0,
  3,
  0.1,
  6,
  0.35,
  10,
  0.8
];

function fillOpacity(selectedId: number | null | undefined): FillPaint["fill-opacity"] {
  return [
    "case",
    ["==", ["get", "electorate_id"], selectedId ?? -1],
    0.76,
    0.57
  ] as unknown as FillPaint["fill-opacity"];
}

export function MapCanvas({
  features,
  selectedFeature,
  initialBounds,
  onSelectFeature
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const featuresRef = useRef<ElectorateFeature[]>([]);
  const selectedFeatureRef = useRef<ElectorateFeature | null>(null);
  const missingKeyRef = useRef(false);
  featuresRef.current = features;
  selectedFeatureRef.current = selectedFeature;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const style = mapStyleUrl();
    missingKeyRef.current = style.missingKey;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: style.url,
      bounds: initialBounds,
      fitBoundsOptions: { padding: 34 },
      attributionControl: { compact: true }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    const initializeLayers = () => {
      if (map.getSource(sourceId)) {
        syncData(map, featuresRef.current);
        return;
      }
      map.addSource(sourceId, {
        type: "geojson",
        data: featureCollection([]) as FeatureCollection
      });
      map.addSource(detailSourceId, {
        type: "geojson",
        data: featureCollection([]) as FeatureCollection
      });
      map.addLayer({
        id: fillLayerId,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": electorateFillColor,
          "fill-opacity": fillOpacity(selectedFeatureRef.current?.id),
          "fill-antialias": false
        }
      });
      map.addLayer({
        id: detailFillLayerId,
        type: "fill",
        source: detailSourceId,
        minzoom: detailComponentMinZoom,
        paint: {
          "fill-color": electorateFillColor,
          "fill-opacity": fillOpacity(selectedFeatureRef.current?.id),
          "fill-antialias": false
        }
      });
      map.addLayer({
        id: lineLayerId,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": "#26343b",
          "line-opacity": componentLineOpacity,
          "line-width": 0.8
        }
      });
      map.addLayer({
        id: detailLineLayerId,
        type: "line",
        source: detailSourceId,
        minzoom: detailComponentMinZoom,
        paint: {
          "line-color": "#26343b",
          "line-opacity": componentLineOpacity,
          "line-width": 0.8
        }
      });
      map.addLayer({
        id: selectedHaloLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "electorate_id"], selectedFeatureRef.current?.id ?? -1],
        paint: {
          "line-color": "#ffffff",
          "line-width": selectedHaloWidth,
          "line-opacity": selectedComponentHaloOpacity,
          "line-blur": selectedHaloBlur
        }
      });
      map.addLayer({
        id: selectedDetailHaloLayerId,
        type: "line",
        source: detailSourceId,
        minzoom: detailComponentMinZoom,
        filter: ["==", ["get", "electorate_id"], selectedFeatureRef.current?.id ?? -1],
        paint: {
          "line-color": "#ffffff",
          "line-width": selectedHaloWidth,
          "line-opacity": selectedComponentHaloOpacity,
          "line-blur": selectedHaloBlur
        }
      });
      map.addLayer({
        id: selectedLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "electorate_id"], selectedFeatureRef.current?.id ?? -1],
        paint: {
          "line-color": "#ffe600",
          "line-width": selectedStrokeWidth,
          "line-opacity": selectedComponentStrokeOpacity
        }
      });
      map.addLayer({
        id: selectedDetailLayerId,
        type: "line",
        source: detailSourceId,
        minzoom: detailComponentMinZoom,
        filter: ["==", ["get", "electorate_id"], selectedFeatureRef.current?.id ?? -1],
        paint: {
          "line-color": "#ffe600",
          "line-width": selectedStrokeWidth,
          "line-opacity": selectedComponentStrokeOpacity
        }
      });
      syncData(map, featuresRef.current);
    };
    if (map.isStyleLoaded()) {
      initializeLayers();
    } else {
      map.on("load", initializeLayers);
    }
    const selectFeatureFromEvent = (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.electorate_id;
      const feature = featuresRef.current.find((item) => item.properties.electorate_id === Number(id));
      if (feature) onSelectFeature(feature);
    };
    const setPointerCursor = () => {
      map.getCanvas().style.cursor = "pointer";
    };
    const clearPointerCursor = () => {
      map.getCanvas().style.cursor = "";
    };
    map.on("click", fillLayerId, selectFeatureFromEvent);
    map.on("click", detailFillLayerId, selectFeatureFromEvent);
    map.on("mouseenter", fillLayerId, setPointerCursor);
    map.on("mouseenter", detailFillLayerId, setPointerCursor);
    map.on("mouseleave", fillLayerId, clearPointerCursor);
    map.on("mouseleave", detailFillLayerId, clearPointerCursor);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [initialBounds, onSelectFeature]);

  useEffect(() => {
    featuresRef.current = features;
    if (!mapRef.current?.isStyleLoaded()) return;
    syncData(mapRef.current, features);
  }, [features]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    for (const layerId of selectionLayerIds) {
      if (map.getLayer(layerId)) {
        map.setFilter(layerId, ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1]);
      }
    }
    for (const layerId of fillLayerIds) {
      if (map.getLayer(layerId)) {
        map.setPaintProperty(layerId, "fill-opacity", fillOpacity(selectedFeature?.id));
      }
    }
  }, [selectedFeature]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map-canvas" />
      {missingKeyRef.current && (
        <div className="map-warning">
          MapTiler key missing. Using fallback basemap.
        </div>
      )}
    </div>
  );
}

function syncData(map: maplibregl.Map, features: ElectorateFeature[]) {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;
  const detailSource = map.getSource(detailSourceId) as maplibregl.GeoJSONSource | undefined;
  if (source) {
    source.setData(displayFeatureCollection(features, "major"));
  }
  if (detailSource) {
    detailSource.setData(displayFeatureCollection(features, "minor"));
  }
}

function displayFeatureCollection(features: ElectorateFeature[], mode: ComponentMode): FeatureCollection {
  return {
    ...featureCollection([]),
    features: features.flatMap((feature) => displayFeaturesForElectorate(feature, mode))
  } as FeatureCollection;
}

function displayFeaturesForElectorate(
  feature: ElectorateFeature,
  mode: ComponentMode
): Feature<Geometry, DisplayProperties>[] {
  if (!feature.geometry) return [];
  if (feature.geometry.type !== "MultiPolygon") {
    if (mode === "minor") return [];
    return [
      {
        type: "Feature",
        id: feature.id,
        geometry: feature.geometry as Geometry,
        properties: {
          ...feature.properties,
          map_component_area_hint: polygonOrMultipolygonAreaHint(feature.geometry),
          map_component_count: 1,
          map_component_index: 0
        }
      }
    ];
  }
  const coordinates = feature.geometry.coordinates;
  if (!Array.isArray(coordinates)) {
    return [];
  }
  const componentCount = coordinates.length;
  const componentAreaHints = coordinates.map((polygonCoordinates) => {
    if (!Array.isArray(polygonCoordinates)) return 0;
    return polygonAreaHint(polygonCoordinates);
  });
  const largestComponentAreaHint = Math.max(...componentAreaHints);
  return coordinates.flatMap((polygonCoordinates, index) => {
    if (!Array.isArray(polygonCoordinates)) return [];
    const areaHint = componentAreaHints[index] ?? 0;
    const isMinor = isMinorDisplayComponent(componentCount, areaHint, largestComponentAreaHint);
    if ((mode === "minor") !== isMinor) return [];
    return [
      {
        type: "Feature",
        id: `${feature.id}:${index}`,
        geometry: {
          type: "Polygon",
          coordinates: polygonCoordinates
        } as Geometry,
        properties: {
          ...feature.properties,
          map_component_area_hint: areaHint,
          map_component_count: componentCount,
          map_component_index: index
        }
      }
    ];
  });
}

function isMinorDisplayComponent(
  componentCount: number,
  areaHint: number,
  largestComponentAreaHint: number
): boolean {
  return (
    componentCount > 1 &&
    areaHint < largestComponentAreaHint &&
    areaHint < minorComponentAreaThresholdSqKm
  );
}

function polygonOrMultipolygonAreaHint(geometry: ElectorateFeature["geometry"]): number {
  if (!geometry) return 0;
  if (geometry.type === "Polygon" && Array.isArray(geometry.coordinates)) {
    return polygonAreaHint(geometry.coordinates);
  }
  if (geometry.type === "MultiPolygon" && Array.isArray(geometry.coordinates)) {
    return geometry.coordinates.reduce<number>((total, polygonCoordinates) => {
      if (!Array.isArray(polygonCoordinates)) return total;
      return total + polygonAreaHint(polygonCoordinates);
    }, 0);
  }
  return 0;
}

function polygonAreaHint(coordinates: unknown): number {
  if (!Array.isArray(coordinates)) return 0;
  const rings = coordinates.filter(Array.isArray) as unknown[];
  if (rings.length === 0) return 0;
  const [outerRing, ...holes] = rings;
  const outerArea = ringAreaHint(outerRing);
  const holeArea = holes.reduce<number>((total, ring) => total + ringAreaHint(ring), 0);
  return Math.max(0, outerArea - holeArea);
}

function ringAreaHint(ring: unknown): number {
  if (!Array.isArray(ring) || ring.length < 4) return 0;
  const points = ring
    .filter((point): point is [number, number] => (
      Array.isArray(point) &&
      typeof point[0] === "number" &&
      typeof point[1] === "number"
    ));
  if (points.length < 4) return 0;
  const meanLatitude = points.reduce((total, point) => total + point[1], 0) / points.length;
  const kmPerDegreeLon = 111.32 * Math.cos((meanLatitude * Math.PI) / 180);
  const kmPerDegreeLat = 110.574;
  let area = 0;
  for (let index = 0; index < points.length - 1; index += 1) {
    const [x1, y1] = points[index];
    const [x2, y2] = points[index + 1];
    area += x1 * kmPerDegreeLon * y2 * kmPerDegreeLat;
    area -= x2 * kmPerDegreeLon * y1 * kmPerDegreeLat;
  }
  return Math.abs(area) / 2;
}
