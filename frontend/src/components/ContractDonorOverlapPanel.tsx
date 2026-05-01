/* ContractDonorOverlapPanel
 *
 * Lists suppliers that received Australian Government contracts
 * AND appear as donors / gift-givers / hosts in the deterministic
 * record (`influence_event`). Side-by-side: contract value (tier
 * 2 LLM-tagged) and donor money (tier 1 deterministic). NEVER
 * sums across tiers.
 *
 * Data source: /api/contract-donor-overlap, optionally filtered
 * by sector.
 *
 * Embedded in EntityProfilePanel when the profiled entity matches
 * a row in the overlap; also reachable as a standalone card on
 * the home view filtered by sector.
 */

import { useEffect, useState } from "react";
import { Banknote, Briefcase, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { fetchContractDonorOverlap } from "../api";
import { formatMoney } from "../map";
import type { ContractDonorOverlapRow, LoadState } from "../types";

type ContractDonorOverlapPanelProps = {
  /** Optional sector filter (e.g. "defence", "consulting"). */
  sector?: string;
  /** Soft cap on rows shown (default 20). */
  rowLimit?: number;
  /** Minimum contract value to filter on (default $1M). */
  minContractValueAud?: number;
  /** When true, the panel is collapsed by default. */
  initiallyCollapsed?: boolean;
};

export function ContractDonorOverlapPanel({
  sector,
  rowLimit = 20,
  minContractValueAud = 1_000_000,
  initiallyCollapsed = false
}: ContractDonorOverlapPanelProps) {
  const [rows, setRows] = useState<ContractDonorOverlapRow[]>([]);
  const [status, setStatus] = useState<LoadState>("idle");
  const [error, setError] = useState<string>("");
  const [caveat, setCaveat] = useState<string>("");
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);

  useEffect(() => {
    if (collapsed && status === "idle") return;
    let cancelled = false;
    setStatus("loading");
    setError("");
    fetchContractDonorOverlap({
      sector,
      minContractValueAud,
      limit: rowLimit
    })
      .then((response) => {
        if (cancelled) return;
        setRows(response.rows);
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
  }, [collapsed, sector, minContractValueAud, rowLimit, status]);

  return (
    <section
      className="contract-donor-overlap-panel"
      aria-label={
        sector
          ? `Contract suppliers in ${sector} sector that also donate`
          : "Contract suppliers that also donate"
      }
    >
      <header className="contract-donor-overlap-header">
        <div>
          <span className="result-type">
            <Briefcase size={12} aria-hidden="true" /> Contract × donor overlap
          </span>
          <h4>
            {sector ? `${sector} sector` : "All sectors"} &mdash; suppliers that ALSO donate
          </h4>
          <p className="muted small">
            Tier 1 (donor amount) + Tier 2 (LLM-tagged contract value) shown side-by-side.
            Never summed. <a href="/methodology.html#evidence-tiers">Methodology</a>.
          </p>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label={collapsed ? "Expand overlap" : "Collapse overlap"}
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
        </button>
      </header>

      {!collapsed && (
        <>
          {status === "loading" && (
            <p className="muted inline-loading">
              <Loader2 size={14} className="spin" aria-hidden="true" /> Loading overlap
            </p>
          )}
          {status === "error" && (
            <p className="muted">Could not load overlap: {error}</p>
          )}
          {status === "ready" && rows.length === 0 && (
            <p className="muted">
              No supplier-donor overlap rows match the current filter.
              Try lowering the minimum contract value or removing the
              sector filter.
            </p>
          )}
          {status === "ready" && rows.length > 0 && (
            <>
              <table className="contract-donor-overlap-table">
                <thead>
                  <tr>
                    <th scope="col">Supplier</th>
                    <th scope="col" className="numeric">
                      <Briefcase size={11} aria-hidden="true" /> Contracts
                      <span className="tier-pill tier-2">tier 2</span>
                    </th>
                    <th scope="col" className="numeric">
                      <Banknote size={11} aria-hidden="true" /> Donations
                      <span className="tier-pill tier-1">tier 1</span>
                    </th>
                    <th scope="col" className="numeric">N contracts</th>
                    <th scope="col" className="numeric">N events</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={`${row.supplier_normalized}-${row.contract_prompt_version}`}
                    >
                      <th scope="row">{row.supplier_name}</th>
                      <td className="numeric">
                        {row.total_contract_value_aud != null
                          ? formatMoney(row.total_contract_value_aud)
                          : "—"}
                      </td>
                      <td className="numeric">
                        {row.donor_total_money_aud != null
                          ? formatMoney(row.donor_total_money_aud)
                          : "—"}
                      </td>
                      <td className="numeric">{row.contract_count}</td>
                      <td className="numeric">{row.donor_event_count}</td>
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
