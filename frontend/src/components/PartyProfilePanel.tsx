import { Banknote, Building2, Loader2, Network, Users, X } from "lucide-react";
import { formatMoney } from "../map";
import type { LoadState, PartyEvent, PartyProfile } from "../types";

type PartyProfilePanelProps = {
  profile: PartyProfile | null;
  status: LoadState;
  error: string;
  onOpenGraph: (partyId: number, label: string) => void;
  onClose: () => void;
};

export function PartyProfilePanel({
  profile,
  status,
  error,
  onOpenGraph,
  onClose
}: PartyProfilePanelProps) {
  if (status === "idle") return null;

  return (
    <section className="entity-profile-panel" aria-label="Party money profile">
      <div className="entity-profile-header">
        <div>
          <span className="result-type">Party profile</span>
          <h2>{profile ? partyDisplayName(profile) : "Loading party"}</h2>
          {profile && (
            <p>
              {[profile.party.short_name, profile.party.jurisdiction_level]
                .filter(Boolean)
                .join(" · ")}
            </p>
          )}
        </div>
        <div className="profile-header-actions">
          {profile && (
            <button
              className="icon-button"
              type="button"
              aria-label={`Open evidence network for ${profile.party.name}`}
              title="Open source-backed evidence network"
              onClick={() => onOpenGraph(profile.party.id, partyDisplayName(profile))}
            >
              <Network size={15} aria-hidden="true" />
            </button>
          )}
          <button className="icon-button" type="button" aria-label="Close party profile" onClick={onClose}>
            <X size={15} aria-hidden="true" />
          </button>
        </div>
      </div>

      {status === "loading" && (
        <p className="muted inline-loading">
          <Loader2 size={14} className="spin" aria-hidden="true" />
          Loading party/entity money records
        </p>
      )}

      {status === "error" && <p className="muted">Could not load party profile: {error}</p>}

      {status === "ready" && profile && (
        <>
          <div className="fact-grid compact-grid">
            <ProfileFact
              icon={<Users size={16} />}
              label="Current reps"
              value={profile.office_summary
                .reduce((total, row) => total + row.current_representative_count, 0)
                .toLocaleString("en-AU")}
            />
            <ProfileFact
              icon={<Building2 size={16} />}
              label="Reviewed entities"
              value={profile.linked_entities.length.toLocaleString("en-AU")}
            />
            <ProfileFact
              icon={<Banknote size={16} />}
              label="Reviewed money"
              value={summaryCount(profile.money_summary)}
            />
            <ProfileFact
              icon={<Banknote size={16} />}
              label="Reported total"
              value={formatMoney(summaryAmount(profile.money_summary))}
            />
          </div>

          <PartyRankList
            title="Top sources to party entities"
            rows={profile.top_sources.map((row) => ({
              key: `${row.source_id}:${row.source_label}`,
              label: row.source_label,
              count: row.event_count,
              amount: row.reported_amount_total
            }))}
          />

          <PartyRankList
            title="Top recipients from party entities"
            rows={profile.top_recipients.map((row) => ({
              key: `${row.recipient_id}:${row.recipient_label}`,
              label: row.recipient_label,
              count: row.event_count,
              amount: row.reported_amount_total
            }))}
          />

          <PartyRankList
            title="Associated-entity return entities"
            rows={profile.associated_entity_returns.map((row) => ({
              key: `${row.entity_id}:${row.canonical_name}`,
              label: row.canonical_name,
              count: row.event_count,
              amount: row.reported_amount_total
            }))}
          />

          <div className="entity-rank-list">
            <h3>Reviewed party entities</h3>
            {profile.linked_entities.slice(0, 8).map((entity) => (
              <div className="entity-rank-row" key={entity.entity_id}>
                <span>{entity.canonical_name}</span>
                <strong>{entity.review_status.replaceAll("_", " ")}</strong>
                <small>{entity.link_type.replaceAll("_", " ")}</small>
              </div>
            ))}
            {profile.linked_entities.length === 0 && (
              <p className="muted">No reviewed party entities are linked yet.</p>
            )}
          </div>

          <details className="review-candidate-panel">
            <summary>
              <span>Entity candidates for review</span>
              <strong>{profile.candidate_entities.length.toLocaleString("en-AU")}</strong>
            </summary>
            <p>
              These are name-pattern candidates for human review. They are not treated as
              reviewed party links in totals or graphs until accepted by the review workflow.
            </p>
            <div className="entity-rank-list candidate-rank-list">
              {profile.candidate_entities.slice(0, 8).map((entity) => (
                <div
                  className="entity-rank-row candidate-rank-row"
                  key={`${entity.entity_id}:${entity.link_type}`}
                >
                  <span>{entity.canonical_name}</span>
                  <strong>Pending review</strong>
                  <small>
                    {[
                      entity.link_type.replaceAll("_", " "),
                      entity.reported_amount_total ? formatMoney(entity.reported_amount_total) : null
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </div>
              ))}
              {profile.candidate_entities.length === 0 && (
                <p className="muted">No party/entity candidates are queued for review.</p>
              )}
            </div>
          </details>

          <div className="entity-event-list">
            <h3>Recent party/entity money records</h3>
            {profile.recent_events.slice(0, 6).map((event) => (
              <PartyEventRow event={event} key={event.id} />
            ))}
            {profile.recent_events.length === 0 && (
              <p className="muted">No non-rejected money records are linked to this party profile yet.</p>
            )}
          </div>

          <p className="caveat compact">{profile.caveat}</p>
        </>
      )}
    </section>
  );
}

function partyDisplayName(profile: PartyProfile) {
  return profile.party.display_name || profile.party.name;
}

function summaryCount(rows: Array<{ event_count: number }>) {
  return rows.reduce((total, row) => total + row.event_count, 0).toLocaleString("en-AU");
}

function summaryAmount(rows: Array<{ reported_amount_total: number | null }>) {
  return rows.reduce((total, row) => total + (row.reported_amount_total ?? 0), 0);
}

function ProfileFact({
  icon,
  label,
  value
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="fact">
      <span className="fact-icon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PartyRankList({
  title,
  rows
}: {
  title: string;
  rows: Array<{ key: string; label: string; count: number; amount: number | null }>;
}) {
  if (!rows.length) return null;
  return (
    <div className="entity-rank-list">
      <h3>{title}</h3>
      {rows.slice(0, 5).map((row) => (
        <div className="entity-rank-row" key={row.key}>
          <span>{row.label}</span>
          <strong>{formatMoney(row.amount)}</strong>
          <small>{row.count.toLocaleString("en-AU")} records</small>
        </div>
      ))}
    </div>
  );
}

function eventTimeLabel(event: PartyEvent) {
  if (event.event_date) return event.event_date;
  if (event.reporting_period) return `Reporting period ${event.reporting_period}`;
  return "Date not disclosed";
}

function PartyEventRow({ event }: { event: PartyEvent }) {
  const sourceHref = event.source_final_url || event.source_url;
  const counterparty =
    event.entity_role === "as_source"
      ? event.recipient_entity_name || event.recipient_raw_name
      : event.source_entity_name || event.source_raw_name;
  return (
    <article className="entity-event-row">
      <div>
        <strong>{event.event_type.replaceAll("_", " ")}</strong>
        <span>{counterparty || "Counterparty not identified"}</span>
      </div>
      <small>
        {[eventTimeLabel(event), formatMoney(event.amount)].filter(Boolean).join(" · ")}
      </small>
      {sourceHref && (
        <a href={sourceHref} target="_blank" rel="noreferrer">
          {event.source_name || event.source_id}
        </a>
      )}
    </article>
  );
}
