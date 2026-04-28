import {
  AlertCircle,
  ArrowRight,
  Banknote,
  ExternalLink,
  Gift,
  Globe2,
  Loader2,
  Mail,
  MapPin,
  Phone,
  X,
  Vote
} from "lucide-react";
import { formatMoney } from "../map";
import type { ElectorateFeature, LoadState, RepresentativeContact, RepresentativeProfile } from "../types";

type DetailsPanelProps = {
  feature: ElectorateFeature | null;
  caveat: string;
  partyColor: string;
  selectedPersonId: number | null;
  contactPersonId: number | null;
  representativeProfile: RepresentativeProfile | null;
  representativeProfileStatus: LoadState;
  onSelectRepresentative: (personId: number) => void;
  onCloseContact: () => void;
};

export function DetailsPanel({
  feature,
  caveat,
  partyColor,
  selectedPersonId,
  contactPersonId,
  representativeProfile,
  representativeProfileStatus,
  onSelectRepresentative,
  onCloseContact
}: DetailsPanelProps) {
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
            properties.current_representatives.map((representative) => {
              const isContactOpen = contactPersonId === representative.person_id;
              return (
                <div className="rep-item" key={representative.person_id}>
                  <button
                    className="rep-row"
                    data-selected={representative.person_id === selectedPersonId}
                    type="button"
                    aria-expanded={isContactOpen}
                    onClick={() => onSelectRepresentative(representative.person_id)}
                  >
                    <div>
                      <strong>{representative.display_name}</strong>
                      <span>{representative.party_name || "No party recorded"}</span>
                    </div>
                    <ArrowRight size={16} aria-hidden="true" />
                  </button>
                  {isContactOpen && (
                    <ContactPopup
                      profile={representativeProfile}
                      status={representativeProfileStatus}
                      onClose={onCloseContact}
                    />
                  )}
                </div>
              );
            })
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
        <h3>Selected Representative Records</h3>
        {representativeProfileStatus === "loading" && (
          <p className="muted inline-loading">
            <Loader2 size={14} className="spin" aria-hidden="true" />
            Loading source-backed records
          </p>
        )}
        {representativeProfileStatus === "error" && (
          <p className="muted">Could not load representative records.</p>
        )}
        {representativeProfileStatus === "ready" && representativeProfile && (
          <>
            <div className="event-family-grid">
              {representativeProfile.event_summary.length ? (
                representativeProfile.event_summary.map((summary) => (
                  <div className="event-family" key={summary.event_family}>
                    <small>{summary.event_family.replaceAll("_", " ")}</small>
                    <strong>{summary.event_count.toLocaleString("en-AU")}</strong>
                    <span>{formatMoney(summary.reported_amount_total)}</span>
                  </div>
                ))
              ) : (
                <p className="muted">No source-backed person-linked records are loaded yet.</p>
              )}
            </div>
            <div className="event-list">
              {representativeProfile.recent_events.slice(0, 8).map((event) => (
                <article className="event-row" key={event.id}>
                  <div>
                    <strong>{event.event_type.replaceAll("_", " ")}</strong>
                    <span>
                      {event.source_entity_name || event.source_raw_name || "Source not identified"}
                    </span>
                  </div>
                  <p>{event.description}</p>
                  <small>
                    {[eventTimeLabel(event), formatMoney(event.amount)]
                      .filter(Boolean)
                      .join(" · ")}
                  </small>
                </article>
              ))}
            </div>
          </>
        )}
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

function eventTimeLabel(event: { event_date: string | null; reporting_period: string | null }) {
  if (event.event_date) return event.event_date;
  if (event.reporting_period) return `Reporting period ${event.reporting_period}`;
  return null;
}

function ContactPopup({
  profile,
  status,
  onClose
}: {
  profile: RepresentativeProfile | null;
  status: LoadState;
  onClose: () => void;
}) {
  if (status === "loading") {
    return (
      <div className="contact-popover" role="dialog" aria-label="Representative contact details">
        <p className="muted inline-loading">
          <Loader2 size={14} className="spin" aria-hidden="true" />
          Loading public contact details
        </p>
      </div>
    );
  }
  if (status === "error" || !profile) {
    return (
      <div className="contact-popover" role="dialog" aria-label="Representative contact details">
        <p className="muted">Could not load public contact details.</p>
      </div>
    );
  }

  const contact = profile.contact;
  return (
    <div className="contact-popover" role="dialog" aria-label="Representative contact details">
      <div className="contact-popover-header">
        <div>
          <small>Public contact details</small>
          <strong>{profile.person.display_name}</strong>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close contact details">
          <X size={15} aria-hidden="true" />
        </button>
      </div>

      <div className="contact-grid">
        <ContactLine
          icon={<Mail size={15} />}
          label="Email"
          value={contact.email}
          href={contact.email ? `mailto:${contact.email}` : null}
          fallback="Not published in loaded APH contact record"
        />
        <ContactLine
          icon={<Phone size={15} />}
          label="Electorate phone"
          value={contact.phones.electorate}
          href={telHref(contact.phones.electorate)}
          fallback="Not listed"
        />
        <ContactLine
          icon={<Phone size={15} />}
          label="Parliament phone"
          value={contact.phones.parliament}
          href={telHref(contact.phones.parliament)}
          fallback="Not listed"
        />
        <ContactLine
          icon={<MapPin size={15} />}
          label="Physical office"
          value={contact.addresses.physical_office}
          fallback="Not listed"
        />
        <ContactLine
          icon={<MapPin size={15} />}
          label="Postal address"
          value={contact.addresses.postal}
          fallback="Not listed"
        />
        <ContactLine
          icon={<Globe2 size={15} />}
          label="Web profile"
          value={contact.web.official_profile ? "APH profile/search" : null}
          href={contact.web.official_profile}
          fallback="Not listed"
        />
      </div>

      <div className="contact-source-row">
        <ContactSourceLink contact={contact} />
      </div>
      <p className="contact-note">{contact.source_note}</p>
    </div>
  );
}

function ContactLine({
  icon,
  label,
  value,
  href,
  fallback
}: {
  icon: React.ReactNode;
  label: string;
  value: string | null;
  href?: string | null;
  fallback: string;
}) {
  return (
    <div className="contact-line">
      <span className="contact-icon">{icon}</span>
      <div>
        <small>{label}</small>
        {value && href ? (
          <a href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer">
            {value}
          </a>
        ) : (
          <strong>{value || fallback}</strong>
        )}
      </div>
    </div>
  );
}

function ContactSourceLink({ contact }: { contact: RepresentativeContact }) {
  if (!contact.source_url) return <span>Source: APH public contact records</span>;
  return (
    <a href={contact.source_url} target="_blank" rel="noreferrer">
      Source: APH public contact records
    </a>
  );
}

function telHref(phone: string | null) {
  if (!phone) return null;
  const cleaned = phone.replace(/[^\d+]/g, "");
  return cleaned ? `tel:${cleaned}` : null;
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
