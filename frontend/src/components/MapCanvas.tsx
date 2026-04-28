import { useEffect, useRef } from "react";
import type { FeatureCollection } from "geojson";
import maplibregl, { type LngLatBoundsLike, type MapLayerMouseEvent } from "maplibre-gl";
import { featureCollection, mapStyleUrl } from "../map";
import type { ElectorateFeature } from "../types";

type MapCanvasProps = {
  features: ElectorateFeature[];
  selectedFeature: ElectorateFeature | null;
  initialBounds: LngLatBoundsLike;
  onSelectFeature: (feature: ElectorateFeature) => void;
};

const sourceId = "electorates";
const fillLayerId = "electorate-fills";
const lineLayerId = "electorate-lines";
const selectedLayerId = "selected-electorate";

export function MapCanvas({
  features,
  selectedFeature,
  initialBounds,
  onSelectFeature
}: MapCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const featuresRef = useRef<ElectorateFeature[]>([]);
  const missingKeyRef = useRef(false);

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
    map.on("load", () => {
      map.addSource(sourceId, {
        type: "geojson",
        data: featureCollection([]) as FeatureCollection
      });
      map.addLayer({
        id: fillLayerId,
        type: "fill",
        source: sourceId,
        paint: {
          "fill-color": [
            "match",
            ["get", "party_short_name"],
            "ALP",
            "#d94a46",
            "LP",
            "#2e65b8",
            "LNP",
            "#2e65b8",
            "Nats",
            "#2f8c56",
            "AG",
            "#2f9a6a",
            "#68717d"
          ],
          "fill-opacity": [
            "case",
            ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
            0.68,
            0.42
          ]
        }
      });
      map.addLayer({
        id: lineLayerId,
        type: "line",
        source: sourceId,
        paint: {
          "line-color": "#27323a",
          "line-opacity": 0.5,
          "line-width": 0.7
        }
      });
      map.addLayer({
        id: selectedLayerId,
        type: "line",
        source: sourceId,
        filter: ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        paint: {
          "line-color": "#f8b34b",
          "line-width": 3,
          "line-opacity": 0.95
        }
      });
      syncData(map, features);
    });
    map.on("click", fillLayerId, (event: MapLayerMouseEvent) => {
      const id = event.features?.[0]?.properties?.electorate_id;
      const feature = featuresRef.current.find((item) => item.properties.electorate_id === Number(id));
      if (feature) onSelectFeature(feature);
    });
    map.on("mouseenter", fillLayerId, () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", fillLayerId, () => {
      map.getCanvas().style.cursor = "";
    });
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [initialBounds, onSelectFeature, features, selectedFeature?.id]);

  useEffect(() => {
    featuresRef.current = features;
    if (!mapRef.current?.isStyleLoaded()) return;
    syncData(mapRef.current, features);
  }, [features]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    if (map.getLayer(selectedLayerId)) {
      map.setFilter(selectedLayerId, ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1]);
    }
    if (map.getLayer(fillLayerId)) {
      map.setPaintProperty(fillLayerId, "fill-opacity", [
        "case",
        ["==", ["get", "electorate_id"], selectedFeature?.id ?? -1],
        0.68,
        0.42
      ]);
    }
    if (selectedFeature?.geometry) {
      const bounds = featureBounds(selectedFeature);
      if (bounds) map.fitBounds(bounds, { padding: 72, duration: 520, maxZoom: 8 });
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
  if (!source) return;
  source.setData(
    featureCollection(features.filter((feature) => feature.geometry)) as FeatureCollection
  );
}

function featureBounds(feature: ElectorateFeature): maplibregl.LngLatBoundsLike | null {
  if (!feature.geometry) return null;
  const coordinates: number[][] = [];
  collectPositions(feature.geometry.coordinates, coordinates);
  if (!coordinates.length) return null;
  const bounds = new maplibregl.LngLatBounds(coordinates[0] as [number, number], coordinates[0] as [number, number]);
  for (const coordinate of coordinates) bounds.extend(coordinate as [number, number]);
  return bounds;
}

function collectPositions(value: unknown, output: number[][]) {
  if (!Array.isArray(value)) return;
  if (typeof value[0] === "number" && typeof value[1] === "number") {
    output.push(value as number[]);
    return;
  }
  for (const item of value) collectPositions(item, output);
}
