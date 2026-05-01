/* IndustryActivityCard
 *
 * A reader-facing card listing the top sectors by combined activity
 * (donor money + contract value), with the two amounts surfaced
 * side-by-side. NEVER sums across evidence tiers.
 *
 * Powers questions like "the gas industry / coal industry / pharma /
 * defence" rollups. Sources:
 *   - Tier 1 (deterministic): donations / gifts / private interests
 *     from public registers (AEC + APH).
 *   - Tier 2 (LLM-tagged): AusTender contract awards via Stage 3
 *     of the LLM extraction pipeline.
 *
 * Responsive: collapses to a single-column list on narrow viewports.
 *
 * The card uses the existing project styling (entity-profile-panel
 * pattern) so it fits cleanly into the existing UI without a new
 * design system.
 */

import { useEffect, useState } from "react";
import { Banknote, Briefcase, ChevronDown, ChevronUp, Gift, Loader2, Plane } from "lucide-react";
import { fetchIndustryAnatomy } from "../api";
import { formatMoney } from "../map";
import type { IndustryAnatomyRow, LoadState } from "../types";

const FRIENDLY_SECTOR_LABELS: Record<string, string> = {
  fossil_fuels: "Fossil fuels (general)",
  coal: "Coal",
  gas: "Gas",
  petroleum: "Petroleum / oil",
  uranium: "Uranium",
  fossil_fuels_other: "Fossil fuels (mixed)",
  mining: "Mining (general)",
  iron_ore: "Iron ore",
  critical_minerals: "Critical minerals",
  mining_other: "Mining (other commodities)",
  renewable_energy: "Renewable energy",
  property_development: "Property development",
  construction: "Construction",
  gambling: "Gambling",
  alcohol: "Alcohol",
  tobacco: "Tobacco",
  finance: "Finance",
  superannuation: "Superannuation",
  insurance: "Insurance",
  banking: "Banking",
  technology: "Technology",
  telecoms: "Telecoms",
  defence: "Defence",
  consulting: "Consulting",
  law: "Law",
  accounting: "Accounting",
  healthcare: "Healthcare",
  pharmaceuticals: "Pharmaceuticals",
  education: "Education",
  media: "Media",
  sport_entertainment: "Sport / entertainment",
  transport: "Transport",
  aviation: "Aviation",
  agriculture: "Agriculture",
  unions: "Unions",
  business_associations: "Business associations",
  charities_nonprofits: "Charities / nonprofits",
  foreign_government: "Foreign government",
  government_owned: "Government-owned entities",
  political_entity: "Political entities",
  individual_uncoded: "Individuals (uncoded)",
  unknown: "Unknown / uncoded"
};

function friendlySectorLabel(slug: string): string {
  return FRIENDLY_SECTOR_LABELS[slug] ?? slug;
}

type IndustryActivityCardProps = {
  /** When true, the card is collapsed by default. */
  initiallyCollapsed?: boolean;
  /** Soft cap on rows shown (default 12). */
  rowLimit?: number;
};

export function IndustryActivityCard({
  initiallyCollapsed = false,
  rowLimit = 12
}: IndustryActivityCardProps) {
  const [rows, setRows] = useState<IndustryAnatomyRow[]>([]);
  const [status, setStatus] = useState<LoadState>("idle");
  const [error, setError] = useState<string>("");
  const [caveat, setCaveat] = useState<string>("");
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);

  useEffect(() => {
    if (collapsed && status === "idle") return;
    let cancelled = false;
    setStatus("loading");
    setError("");
    fetchIndustryAnatomy({ limit: 200 })
      .then((response) => {
        if (cancelled) return;
        // Filter out duplicate-sector rows (multiple v1/v2 prompt
        // versions can yield duplicates; pick highest-activity row).
        const seen = new Map<string, IndustryAnatomyRow>();
        for (const row of response.rows) {
          const existing = seen.get(row.sector);
          const score =
            (row.total_money_aud ?? 0) + (row.total_contract_value_aud ?? 0);
          const existingScore = existing
            ? (existing.total_money_aud ?? 0) +
              (existing.total_contract_value_aud ?? 0)
            : -1;
          if (!existing || score > existingScore) seen.set(row.sector, row);
        }
        const dedup = Array.from(seen.values());
        // Filter out catch-alls that aren't useful for industry analysis.
        const filtered = dedup.filter(
          (r) =>
            r.sector !== "unknown" &&
            r.sector !== "individual_uncoded" &&
            ((r.total_money_aud ?? 0) > 0 ||
              (r.total_contract_value_aud ?? 0) > 0 ||
              (r.gift_count ?? 0) > 0 ||
              (r.sponsored_travel_count ?? 0) > 0)
        );
        filtered.sort((a, b) => {
          const sa =
            (a.total_money_aud ?? 0) + (a.total_contract_value_aud ?? 0);
          const sb =
            (b.total_money_aud ?? 0) + (b.total_contract_value_aud ?? 0);
          return sb - sa;
        });
        setRows(filtered.slice(0, rowLimit));
        setCaveat(response.claim_discipline_caveat);
        setStatus("ready");
      })
      .catch((err: Error) => {
        if (cancelled) return;
        setError(err.message);
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [collapsed, rowLimit, status]);

  return (
    <section className="industry-activity-card" aria-label="Industry-level political-influence activity">
      <header className="industry-activity-header">
        <div>
          <span className="result-type">Industry activity (federal)</span>
          <h3>Influence anatomy by sector</h3>
          <p className="muted small">
            Every evidence stream surfaced side-by-side: donations,
            gifts, sponsored travel, contracts. Never summed across
            tiers. See <a href="/methodology.html#evidence-tiers">methodology</a>.
          </p>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label={collapsed ? "Expand industry activity" : "Collapse industry activity"}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
        </button>
      </header>

      {!collapsed && (
        <>
          {status === "loading" && (
            <p className="muted inline-loading">
              <Loader2 size={14} className="spin" aria-hidden="true" /> Loading industry rollup
            </p>
          )}
          {status === "error" && (
            <p className="muted">Could not load industry rollup: {error}</p>
          )}
          {status === "ready" && rows.length === 0 && (
            <p className="muted">
              No sectors with recorded donor or contract activity yet.
              Once the full Stage 1 entity classification + Stage 3
              contract tagging runs land, this list populates.
            </p>
          )}
          {status === "ready" && rows.length > 0 && (
            <>
              <table className="industry-activity-table">
                <thead>
                  <tr>
                    <th scope="col">Sector</th>
                    <th scope="col" className="numeric" title="Direct + party-mediated donations (deterministic, evidence tier 1)">
                      <Banknote size={13} aria-hidden="true" /> Donations
                      <span className="tier-pill tier-1">t1</span>
                    </th>
                    <th scope="col" className="numeric" title="Disclosed gifts received by MPs from sector entities (LLM-extracted from APH register, evidence tier 2)">
                      <Gift size={13} aria-hidden="true" /> Gifts
                      <span className="tier-pill tier-2">t2</span>
                    </th>
                    <th scope="col" className="numeric" title="Sponsored travel funded by sector entities (LLM-extracted, evidence tier 2)">
                      <Plane size={13} aria-hidden="true" /> Travel
                      <span className="tier-pill tier-2">t2</span>
                    </th>
                    <th scope="col" className="numeric" title="Government contract awards (LLM-tagged, evidence tier 2)">
                      <Briefcase size={13} aria-hidden="true" /> Contracts
                      <span className="tier-pill tier-2">t2</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.sector}>
                      <th scope="row">{friendlySectorLabel(row.sector)}</th>
                      <td className="numeric">
                        {row.total_money_aud != null
                          ? formatMoney(row.total_money_aud)
                          : "—"}
                      </td>
                      <td className="numeric">
                        {(row.gift_count ?? 0) > 0 ? row.gift_count : "—"}
                      </td>
                      <td className="numeric">
                        {(row.sponsored_travel_count ?? 0) > 0
                          ? row.sponsored_travel_count
                          : "—"}
                      </td>
                      <td className="numeric">
                        {row.total_contract_value_aud != null
                          ? formatMoney(row.total_contract_value_aud)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {caveat && (
                <p className="muted small claim-discipline-caveat">{caveat}</p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
