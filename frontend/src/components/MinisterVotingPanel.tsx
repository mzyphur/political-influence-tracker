/* MinisterVotingPanel
 *
 * Per-minister voting record summary by policy topic. Powers the
 * "how did Minister Z vote on bills affecting their portfolio's
 * industries?" surface. Embedded in DetailsPanel for MPs that are
 * also cabinet ministers.
 *
 * Data source: /api/minister-voting-pattern (joins minister_role
 * to vote_division via person_vote, with They Vote For You policy
 * topic tags applied via division_topic).
 *
 * The panel does NOT pre-judge "alignment" — it surfaces the raw
 * counts (aye/no/rebellion) and the consumer interprets. This
 * preserves the project's claim-discipline rule.
 */

import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp, Loader2, Vote } from "lucide-react";
import { fetchMinisterVotingPattern } from "../api";
import type { LoadState, MinisterVotingPatternRow } from "../types";

type MinisterVotingPanelProps = {
  /** Full canonical-name of the minister, e.g. "Mark Dreyfus". */
  ministerName: string;
  /** When true, the panel is collapsed by default. */
  initiallyCollapsed?: boolean;
};

export function MinisterVotingPanel({
  ministerName,
  initiallyCollapsed = false
}: MinisterVotingPanelProps) {
  const [rows, setRows] = useState<MinisterVotingPatternRow[]>([]);
  const [status, setStatus] = useState<LoadState>("idle");
  const [error, setError] = useState<string>("");
  const [caveat, setCaveat] = useState<string>("");
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);

  useEffect(() => {
    if (collapsed && status === "idle") return;
    if (!ministerName) return;
    let cancelled = false;
    setStatus("loading");
    setError("");
    fetchMinisterVotingPattern({ ministerName, limit: 100 })
      .then((response) => {
        if (cancelled) return;
        // Sort by division_count desc — the topics with most votes first.
        const sorted = [...response.rows].sort(
          (a, b) => b.division_count - a.division_count
        );
        setRows(sorted);
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
  }, [collapsed, ministerName, status]);

  if (!ministerName) return null;

  return (
    <section
      className="minister-voting-panel"
      aria-label={`Voting record for ${ministerName}`}
    >
      <header className="minister-voting-header">
        <div>
          <span className="result-type">
            <Vote size={12} aria-hidden="true" /> Voting record
          </span>
          <h4>How {ministerName} voted by policy topic</h4>
          <p className="muted small">
            Topics from <a href="https://theyvoteforyou.org.au" target="_blank" rel="noreferrer noopener">They Vote For You</a> (CC-BY).
            No automatic "alignment" labels &mdash; raw counts only.
          </p>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label={collapsed ? "Expand voting record" : "Collapse voting record"}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
        </button>
      </header>

      {!collapsed && (
        <>
          {status === "loading" && (
            <p className="muted inline-loading">
              <Loader2 size={14} className="spin" aria-hidden="true" /> Loading voting record
            </p>
          )}
          {status === "error" && (
            <p className="muted">Could not load voting record: {error}</p>
          )}
          {status === "ready" && rows.length === 0 && (
            <p className="muted">
              No topic-tagged divisions on record for this minister
              (yet). The voting record covers federal divisions
              tagged by They Vote For You; older or untagged
              divisions don't appear here.
            </p>
          )}
          {status === "ready" && rows.length > 0 && (
            <>
              <table className="minister-voting-table">
                <thead>
                  <tr>
                    <th scope="col">Policy topic</th>
                    <th scope="col" className="numeric">Aye</th>
                    <th scope="col" className="numeric">No</th>
                    <th scope="col" className="numeric">Rebel</th>
                    <th scope="col" className="numeric">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 30).map((row) => (
                    <tr key={`${row.minister_role_id}-${row.topic_id}`}>
                      <th scope="row">{row.policy_topic_label}</th>
                      <td className="numeric">{row.aye_count}</td>
                      <td className="numeric">{row.no_count}</td>
                      <td className="numeric">{row.rebellion_count}</td>
                      <td className="numeric">{row.division_count}</td>
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
