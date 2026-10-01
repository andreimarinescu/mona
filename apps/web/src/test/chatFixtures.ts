import type { MonaUIMessage } from '../chat/types';
import type { Deadline, DocumentSummary, Draft, ExportPack, Interview, Rule, RulePreview } from '../data/dto';

export const DOC: DocumentSummary = {
  id: 'doc_01j9zq3k8e6y4v2m7c5r1t0b9a',
  title: 'Prévia Retraite, payment notice Q1',
  originalName: 'scan_0412.pdf',
  fileName: '2026-01-06_Previa_Avis.pdf',
  path: ['Personnel', '2026 Personnel', 'Assurances'],
  location: 'archive',
  entityId: 'ent_01j9zq3k8h9b7y5q0f8v4x3e2d',
  entityName: 'Personnel',
  subUnitId: null,
  categoryId: 'insurance',
  subcategoryKey: null,
  counterpartyId: 'cpt_01j9zq3k8e6y4v2m7c5r1t0b9a',
  counterparty: 'Prévia Retraite',
  docType: 'notice',
  reference: null,
  date: '2026-01-06',
  periodStart: null,
  periodEnd: null,
  fiscalYear: 2026,
  amount: { value: 955.2, currency: 'EUR' },
  dueDate: null,
  status: 'filed',
  reasons: [],
  confidence: 71,
  band: 'medium',
  pipelineStage: 'done',
  arrivedAt: '2026-01-07T08:00:00.000Z',
  source: 'drop',
  filedAt: '2026-01-07T08:01:00.000Z',
  filedBy: 'mona',
  badgeUntil: null,
  rule: null,
  batchId: 'bat_01j9zq3k8e6y4v2m7c5r1t0b9a',
  pageCount: 1,
  thumbnailUrl: null,
  pdfUrl: '/api/documents/doc_01j9zq3k8e6y4v2m7c5r1t0b9a/pdf',
};

export const DEADLINE: Deadline = {
  id: 'ddl_01j9zq3k8e6y4v2m7c5r1t0b9a',
  documentId: DOC.id,
  label: 'Contributions, third quarter',
  entityId: 'ent_01j9zq3k8e6y4v2m7c5r1t0b9a',
  entityName: 'Cabinet Marchand',
  dueDate: '2026-10-02',
  amount: { value: 1284, currency: 'EUR' },
  paidBy: 'Main account •• 4471',
  status: 'open',
  daysLeft: 2,
  reminder: null,
};

const evidence = (n: number) => ({
  documentId: DOC.id,
  documentTitle: `2025_Previa_Letter_${n}.pdf`,
  field: null,
  page: n,
  quote: n === 1 ? 'annual certificate, contract Madelin retirement no. 4418' : 'guarantee daily allowances, independent profession',
  verified: true,
  findQuery: n === 1 ? 'Madelin' : null,
});

export const INTERVIEW: Interview = {
  id: 'int_01j9zq3k8e6y4v2m7c5r1t0b9a',
  kind: 'debrief',
  status: 'ready',
  questions: [
    {
      id: 'qst_01j9zq3k8e6y4v2m7c5r1t0b9a',
      ordinal: 1,
      question: 'I found 4 letters from Prévia Retraite. Are they personal, or for the practice?',
      lang: 'en',
      affects: [DOC.id],
      affectsCount: 4,
      evidence: [evidence(1), evidence(2)],
      options: [
        { id: 'o1', label: 'For the practice', suggested: true, ruleDraft: { kind: 'always', discriminator: null, branches: [] } },
        { id: 'o2', label: 'Personal', ruleDraft: { kind: 'always', discriminator: null, branches: [] } },
        { id: 'o3', label: 'Ask me each time', ruleDraft: { kind: 'ask', discriminator: null, branches: [] } },
      ],
      suggestionConfidence: 72,
      status: 'open',
      answer: null,
    },
  ],
  batchId: 'bat_01j9zq3k8e6y4v2m7c5r1t0b9a',
  createdAt: '2026-10-01T08:00:00.000Z',
  lang: 'en',
  scope: { type: 'batch', batchId: 'bat_01j9zq3k8e6y4v2m7c5r1t0b9a' },
  openQuestions: 1,
  readyAt: '2026-10-01T08:00:30.000Z',
  finishedAt: null,
  error: null,
  source: 'live',
};

export const RULE: Rule = {
  id: 'rul_01j9zq3k8e6y4v2m7c5r1t0b9a',
  name: 'Prévia Retraite · Personal (retirement)',
  condition: 'Counterparty is Prévia Retraite and the text mentions a retirement contract',
  destination: ['Personnel', '2026 Personnel', 'Assurances', 'Retraite'],
  enabled: true,
  state: 'active',
  source: 'interview',
  version: 1,
  priority: 100,
  firedCount: 3,
  correctionsSince: 0,
};

export const APPLIED_PREVIEW: RulePreview = {
  rule: RULE,
  moves: [
    { documentId: DOC.id, title: DOC.title, from: [], fromFileName: 'scan_0412.pdf', to: RULE.destination, toFileName: '2026-01-06_Previa_Avis.pdf' },
    { documentId: 'doc_01j9zq3k8f7z5w3n8d6s2v1c0b', title: 'Prévia Retraite, payment notice Q2', from: [], fromFileName: 'scan_0413.pdf', to: RULE.destination, toFileName: '2026-04-03_Previa_Avis.pdf' },
  ],
  movesTotal: 4,
  stays: ['doc_01j9zq3k8g8a6x4p9e7t3w2d1c'],
  staysTotal: 2,
  applied: true,
  groupId: 'grp_01j9zq3k8e6y4v2m7c5r1t0b9a',
};

export const DRAFT: Draft = {
  id: 'drf_01j9zq3k8e6y4v2m7c5r1t0b9a',
  documentId: DOC.id,
  lang: 'fr',
  status: 'ready',
  title: 'Réponse au centre des cotisations',
  body: 'Objet : demande d’échéancier · compte n° [VOTRE N° DE COMPTE]\nMadame, Monsieur, …',
  docxUrl: '/api/drafts/drf_01j9zq3k8e6y4v2m7c5r1t0b9a/docx',
};

export const EXPORT: ExportPack = {
  id: 'exp_01j9zq3k8e6y4v2m7c5r1t0b9a',
  entityId: 'ent_01j9zq3k8e6y4v2m7c5r1t0b9a',
  entityName: 'Cabinet Marchand',
  fiscalYear: 2025,
  status: 'ready',
  documentCount: 12,
  zipUrl: '/api/exports/exp_01j9zq3k8e6y4v2m7c5r1t0b9a/zip',
  csvUrl: '/api/exports/exp_01j9zq3k8e6y4v2m7c5r1t0b9a/csv',
};

/** One assistant message carrying every card kind, as the adapter streams them (C3 §5.5). */
export function cardsMessage(over: Partial<{ interview: Interview; draft: Draft; preview: RulePreview }> = {}): MonaUIMessage {
  return {
    id: 'msg_cards',
    role: 'assistant',
    metadata: { conversationId: 'cnv_01j9zq3k8e6y4v2m7c5r1t0b9a', replyLanguage: 'en', reasoningMs: 2400 },
    parts: [
      { type: 'step-start' },
      { type: 'reasoning', text: 'Looking for the notices.', state: 'done' },
      { type: 'dynamic-tool', toolName: 'search_documents', toolCallId: 'call_1', state: 'output-available', input: {}, output: { status: 'completed' } },
      { type: 'data-doc', id: DOC.id, data: DOC },
      { type: 'data-deadline', id: DEADLINE.id, data: DEADLINE },
      { type: 'data-interview', id: INTERVIEW.id, data: over.interview ?? INTERVIEW },
      { type: 'data-rulePreview', id: RULE.id, data: over.preview ?? APPLIED_PREVIEW },
      { type: 'data-draft', id: DRAFT.id, data: over.draft ?? DRAFT },
      { type: 'data-export', id: EXPORT.id, data: EXPORT },
      { type: 'text', text: 'In 2025 you paid €3,820.80 [1].', state: 'done' },
    ],
  } as MonaUIMessage;
}
