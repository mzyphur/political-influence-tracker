import type { ElectorateFeature, ElectorateFeatureCollection } from "./types";

export const AUSTRALIA_BOUNDS: [[number, number], [number, number]] = [
  [111.5, -44.5],
  [154.5, -9.0]
];

export function mapStyleUrl(): { url: string; missingKey: boolean } {
  const key = import.meta.env.VITE_MAPTILER_API_KEY;
  const styleId = import.meta.env.VITE_MAPTILER_STYLE_ID || "basic-v2";
  if (!key) {
    return { url: "https://demotiles.maplibre.org/style.json", missingKey: true };
  }
  return {
    url: `https://api.maptiler.com/maps/${styleId}/style.json?key=${key}`,
    missingKey: false
  };
}

export function featureCollection(features: ElectorateFeature[]): ElectorateFeatureCollection {
  return {
    type: "FeatureCollection",
    features,
    feature_count: features.length,
    filters: {},
    caveat: ""
  };
}

export function electorateColor(partyName?: string | null): string {
  const name = (partyName || "").toLowerCase();
  if (name.includes("labor")) return "#d85a54";
  if (name.includes("liberal")) return "#2f72b7";
  if (name.includes("national")) return "#4f9659";
  if (name.includes("greens")) return "#2d9b75";
  if (name.includes("independent")) return "#c7953d";
  return "#78828c";
}

export function senateRegionColor(state?: string | null): string {
  switch ((state || "").toUpperCase()) {
    case "ACT":
      return "#6b8fcf";
    case "NSW":
      return "#5e9fc0";
    case "NT":
      return "#d48952";
    case "QLD":
      return "#b96969";
    case "SA":
      return "#7d79bf";
    case "TAS":
      return "#4c9b82";
    case "VIC":
      return "#687ec3";
    case "WA":
      return "#c49a4c";
    default:
      return "#78828c";
  }
}

export function formatMoney(value?: number | null): string {
  if (value === null || value === undefined) return "Not disclosed";
  return new Intl.NumberFormat("en-AU", {
    style: "currency",
    currency: "AUD",
    maximumFractionDigits: 0
  }).format(value);
}

export function findFeatureByResult(
  resultId: string | number,
  resultType: string,
  features: ElectorateFeature[]
): ElectorateFeature | undefined {
  if (resultType === "electorate") {
    return features.find((feature) => String(feature.id) === String(resultId));
  }
  if (resultType === "representative") {
    return features.find((feature) =>
      feature.properties.current_representatives.some(
        (representative) => String(representative.person_id) === String(resultId)
      )
    );
  }
  return undefined;
}
