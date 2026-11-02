import { collectClosedFenceBodies, stripLangFence } from "@/lib/mdFenceScan";

/** The theme is the one setting a chat card changes; every other one is changed in Settings. */
type SettingsProposalField = "appearance";

type SettingsProposalChange = {
  field: SettingsProposalField;
  value: string;
  label: string;
};

export type SettingsProposal = {
  proposal_id: string;
  changes: SettingsProposalChange[];
};


// An older card for the model, tone, language or memory is not drawn: chat no longer
// changes those, and the server would refuse its confirm.
const FIELDS = new Set<SettingsProposalField>(["appearance"]);

function normalizeChange(raw: unknown): SettingsProposalChange | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const field = row.field;
  const value = row.value;
  if (typeof field !== "string" || typeof value !== "string") return null;
  if (!FIELDS.has(field as SettingsProposalField)) return null;
  const label = typeof row.label === "string" && row.label.trim() ? row.label : value;
  return { field: field as SettingsProposalField, value, label };
}

function normalizeProposal(raw: unknown): SettingsProposal | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const proposalId = row.proposal_id;
  if (typeof proposalId !== "string" || !proposalId.trim()) return null;
  const changesRaw = row.changes;
  if (!Array.isArray(changesRaw)) return null;
  const changes = changesRaw
    .map(normalizeChange)
    .filter((item): item is SettingsProposalChange => item !== null);
  if (changes.length === 0) return null;
  return { proposal_id: proposalId, changes };
}

export function parseSettingsProposals(content: string): SettingsProposal[] {
  const proposals: SettingsProposal[] = [];
  for (const body of collectClosedFenceBodies(content, "settings_proposal")) {
    try {
      const parsed = normalizeProposal(JSON.parse(body));
      if (parsed) proposals.push(parsed);
    } catch {
      /* skip bad fence */
    }
  }
  return proposals;
}

export function stripSettingsProposalFences(content: string): string {
  return stripLangFence(content, "settings_proposal")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function hasSettingsProposalFence(content: string): boolean {
  return /```settings_proposal/i.test(content);
}
