import { AlertCircle, ArrowRight, Banknote, ExternalLink, Gift, Vote } from "lucide-react";
import { formatMoney } from "../map";
import type { ElectorateFeature } from "../types";

type DetailsPanelProps = {
  feature: ElectorateFeature | null;
  caveat: string;
  partyColor: string;
};

export function DetailsPanel({ feature, caveat, partyColor }: DetailsPanelProps) {
  if (!feature) {
    return (
      <aside className="details-panel empty" aria-label="Selection details">
        <AlertCircle size={20} />
        <p>No electorate selected.</p>
      </aside>
    );
  }

  const properties = feature.properties;
  return (
    <aside className="details-panel" aria-label="Selection details">
      <div className="panel-header" style={{ borderColor: partyColor }}>
        <div>
          <p className="eyebrow">{properties.state_or_territory || "Federal"} · {properties.chamber}</p>
          <h2>{properties.electorate_name}</h2>
        </div>
        <span className="party-dot" style={{ background: partyColor }} />
      </div>

      <section className="panel-section">
        <h3>Current Representation</h3>
        {properties.map_geometry_scope && (
          <p className="scope-caption">
            Map geometry: {properties.map_geometry_scope.replaceAll("_", " ")}
          </p>
        )}
        <div className="rep-list">
          {properties.current_representatives.length ? (
            properties.current_representatives.map((representative) => (
              <div className="rep-row" key={representative.person_id}>
                <div>
                  <strong>{representative.display_name}</strong>
                  <span>{representative.party_name || "No party recorded"}</span>
                </div>
                <ArrowRight size={16} aria-hidden="true" />
              </div>
            ))
          ) : (
            <p className="muted">No current representative is attached in the database.</p>
          )}
        </div>
      </section>

      <section className="panel-section">
        <h3>Representative-Linked Context</h3>
        <div className="fact-grid">
          <Fact
            icon={<ExternalLink size={17} />}
            label="Non-rejected records"
            value={properties.current_representative_lifetime_influence_event_count.toLocaleString("en-AU")}
          />
          <Fact
            icon={<Banknote size={17} />}
            label="Money records"
            value={properties.current_representative_lifetime_money_event_count.toLocaleString("en-AU")}
          />
          <Fact
            icon={<Gift size={17} />}
            label="Benefit records"
            value={properties.current_representative_lifetime_benefit_event_count.toLocaleString("en-AU")}
          />
          <Fact
            icon={<Vote size={17} />}
            label="Reported total"
            value={formatMoney(properties.current_representative_lifetime_reported_amount_total)}
          />
        </div>
      </section>

      <section className="panel-section">
        <h3>Party Breakdown</h3>
        <div className="party-breakdown">
          {properties.party_breakdown.length ? (
            properties.party_breakdown.map((party) => (
              <div className="party-row" key={`${party.party_id}:${party.party_name}`}>
                <span>{party.party_name || "No party recorded"}</span>
                <strong>{party.representative_count}</strong>
              </div>
            ))
          ) : (
            <p className="muted">No party breakdown is available.</p>
          )}
        </div>
      </section>

      <p className="caveat">{caveat}</p>
    </aside>
  );
}

function Fact({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="fact">
      <span className="fact-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
