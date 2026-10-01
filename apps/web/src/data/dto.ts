import type { Lang } from '@mona/ui';

export type Currency = 'EUR' | 'RON';
export interface Money {
  value: number;
  currency: Currency;
}
export type DocStatus = 'filed' | 'review' | 'processing' | 'unreadable';
export type Reason = 'low' | 'entity' | 'conflict' | 'unreadable';
export type Band = 'high' | 'medium' | 'low';
export type Actor = 'mona' | 'user';
export type Via = 'ui' | 'chat' | 'telegram' | 'pipeline';
export type FieldKey =
  | 'entity'
  | 'counterparty'
  | 'issuer'
  | 'reference'
  | 'doc_type'
  | 'doc_date'
  | 'period_start'
  | 'period_end'
  | 'amount'
  | 'due_date'
  | 'addressee';
export type PipelineStage = 'queued' | 'reading' | 'ocr' | 'classifying' | 'filing' | 'done' | 'failed';

export interface Evidence {
  documentId: string;
  documentTitle: string;
  field: FieldKey | null;
  page: number;
  quote: string;
  verified: boolean;
  findQuery: string | null;
}

export interface ExtractedField {
  key: FieldKey;
  value: string;
  money?: Money;
  evidence: Evidence;
  confidence: number;
}

export interface DocumentSummary {
  id: string;
  title: string;
  originalName: string;
  fileName: string;
  path: string[];
  location: 'inbox' | 'archive';
  entityId: string | null;
  entityName: string | null;
  subUnitId: string | null;
  categoryId: string | null;
  subcategoryKey: string | null;
  counterpartyId: string | null;
  counterparty: string | null;
  docType: string | null;
  reference: string | null;
  date: string | null;
  periodStart: string | null;
  periodEnd: string | null;
  fiscalYear: number | null;
  amount?: Money;
  dueDate: string | null;
  status: DocStatus;
  reasons: Reason[];
  confidence: number | null;
  band: Band | null;
  pipelineStage: PipelineStage;
  arrivedAt: string;
  source: 'drop' | 'telegram';
  filedAt: string | null;
  filedBy: Actor | null;
  badgeUntil: string | null;
  rule: { id: string; name: string } | null;
  batchId: string;
  pageCount: number | null;
  thumbnailUrl: string | null;
  pdfUrl: string;
}

export interface Suggestion {
  entityId: string | null;
  subUnitId: string | null;
  categoryId: string | null;
  subcategoryKey: string | null;
  fileName: string | null;
  path: string[];
  confidence: number;
  band: Band;
  reasons: Reason[];
  sentence: string;
  evidence: Evidence[];
  ruleId: string | null;
  conflictingRuleIds: string[];
}

export interface Deadline {
  id: string;
  documentId: string | null;
  label: string;
  entityId: string;
  entityName: string;
  dueDate: string;
  amount?: Money;
  paidBy?: string;
  status: 'open' | 'done' | 'dismissed';
  daysLeft: number;
  reminder: { id: string; remindOn: string } | null;
}

export interface DocumentDetail extends DocumentSummary {
  fields: ExtractedField[];
  suggestion: Suggestion | null;
  journal: JournalEntry[];
  deadlines: Deadline[];
}

export interface PathState {
  location: 'inbox' | 'archive' | 'trash';
  path: string[];
  fileName: string;
  status: DocStatus;
}

export type JournalAction =
  | 'file'
  | 'move'
  | 'rename'
  | 'unfile'
  | 'delete'
  | 'undo'
  | 'redo'
  | 'doc.update'
  | 'rule.create'
  | 'rule.change'
  | 'deadline.add'
  | 'reminder.add'
  | 'mark.unreadable';

export type UndoState = 'undoable' | 'undone' | 'superseded' | 'not_undoable';

export interface JournalEntry {
  id: number;
  at: string;
  actor: Actor;
  via: Via;
  action: JournalAction;
  documentIds: string[];
  subjectId: string | null;
  before: PathState | Record<string, unknown> | null;
  after: PathState | Record<string, unknown> | null;
  batchId?: string;
  groupId: string | null;
  ruleId: string | null;
  confidence: number | null;
  band: Band | null;
  undoable: boolean;
  undoState: UndoState;
  undoneBy?: number;
  undoOf: number | null;
}

export interface JournalGroup {
  id: string;
  kind: 'intake_batch' | 'rule_apply' | 'correction' | 'undo' | 'redo' | 'refile';
  at: string;
  actor: Actor;
  via: Via;
  batchId: string | null;
  ruleId: string | null;
  counts: { entries: number; undoable: number; superseded: number; undone: number };
  undoState: 'undoable' | 'partial' | 'undone' | 'not_undoable';
  targetGroupId: string | null;
}

export type DocRefs = Record<string, { title: string; fileName: string; deleted: boolean }>;

export type ActivityItem =
  | { kind: 'group'; group: JournalGroup; preview: JournalEntry[]; entriesTotal: number; redoGroupId: string | null }
  | { kind: 'entry'; entry: JournalEntry };

export interface Feed<T> {
  items: T[];
  nextCursor: string | null;
}
export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export type DocumentSort = 'relevance' | 'date_desc' | 'date_asc' | 'arrived_desc' | 'amount_desc';
export type ArchiveStatus = 'filed' | 'review' | 'unreadable';

export interface DocumentFacets {
  entities: { id: string; name: string; count: number }[];
  years: { year: number; count: number }[];
  categories: { id: string; label: string; count: number }[];
  counterparties: { id: string; name: string; count: number }[];
  statuses: { status: DocStatus; count: number }[];
  amount: { min: number | null; max: number | null };
}

export interface DocumentPage extends Page<DocumentSummary> {
  facets: DocumentFacets;
}

export interface FolderNode {
  name: string;
  path: string[];
  documentCount: number;
  hasChildren: boolean;
}

export interface FolderListing {
  path: string[];
  folders: FolderNode[];
  documents: DocumentSummary[];
}

export interface ExportPreview {
  entityId: string;
  fiscalYear: number;
  documentCount: number;
  inReview: number;
  categories: { id: string; label: string; count: number }[];
  fiscalYears: number[];
}

export interface ExportPack {
  id: string;
  entityId: string;
  entityName: string;
  fiscalYear: number;
  status: 'building' | 'ready' | 'failed';
  documentCount: number | null;
  zipUrl: string | null;
  csvUrl: string | null;
}

export interface ReminderResult {
  reminderId: string;
  remindOn: string;
  created: boolean;
  deadline: Deadline | null;
}

export interface ActivityPage extends Feed<ActivityItem> {
  documents: DocRefs;
  rules: Record<string, { name: string }>;
}

export interface GroupView {
  group: JournalGroup;
  entries: JournalEntry[];
  documents: DocRefs;
}

export interface UndoResult {
  groupId: string | null;
  undone: { journalId: number; documentId: string; title: string; to: PathState }[];
  skipped: { journalId: number; state: 'superseded' | 'already_undone' | 'not_undoable' | 'not_allowed' }[];
  entries: JournalEntry[];
  ruleStates: { ruleId: string; state: 'draft' | 'active' | 'disabled' }[];
}

export type UndoTarget = { journalId: number } | { groupId: string };

export interface FileOpResult {
  document: DocumentDetail | null;
  outcome: 'moved' | 'unchanged';
  journalIds: number[];
  groupId: string | null;
  undo: UndoTarget | null;
}

export interface CorrectionRequest {
  entityId?: string;
  subUnitId?: string | null;
  categoryId?: string;
  subcategoryKey?: string | null;
  counterparty?: { id: string } | { name: string };
  docDate?: string;
  periodEnd?: string;
  dueDate?: string | null;
  amount?: Money | null;
}

export interface IntakeItem {
  id: string;
  originalName: string;
  sha256: string;
  sizeBytes: number;
  outcome: 'accepted' | 'duplicate' | 'rejected';
  rejectReason: 'unsupported_type' | 'too_large' | 'empty' | 'unreadable_file' | null;
  documentId: string | null;
  deleted: boolean;
  restoreJournalId: number | null;
}

export interface BatchCounts {
  items: number;
  accepted: number;
  duplicate: number;
  rejected: number;
  processing: number;
  filed: number;
  review: number;
  unreadable: number;
  failed: number;
}

export interface BatchSummary {
  id: string;
  source: 'drop' | 'telegram' | 'reclassify';
  status: 'running' | 'done';
  title: string | null;
  visitor: boolean;
  startedAt: string;
  finishedAt: string | null;
  counts: BatchCounts;
  groupId: string;
  debrief: { interviewId: string; status: 'generating' | 'ready' | 'done' | 'failed' | 'cancelled'; openQuestions: number } | null;
}

export interface BatchDetail {
  batch: BatchSummary;
  items: (IntakeItem & { document: DocumentSummary | null })[];
}

export interface IntakeResult {
  batch: BatchSummary;
  items: IntakeItem[];
}

export interface Entity {
  id: string;
  key: string;
  displayName: string;
  folderName: string;
  visibility: 'practice' | 'personal';
  fiscalYearEnd: string;
  filingLanguage: Lang | null;
  subUnits: { id: string; key: string; label: string; personId: string | null }[];
}

export interface EntityList {
  items: Entity[];
  documentCounts: Record<string, number>;
  visitorsEntityId: string | null;
}

export interface CategoryDto {
  id: string;
  labels: Record<Lang, string>;
  icon: string;
  subcategories: { key: string; labels: Record<Lang, string> }[];
}

export interface Counterparty {
  id: string;
  key: string;
  name: string;
  kind: string | null;
}

export type ConditionField = 'counterparty' | 'text' | 'doc_type' | 'category' | 'entity' | 'addressee' | 'person' | 'iban' | 'siren' | 'amount';

export interface Condition {
  field: ConditionField;
  op: string;
  value?: unknown;
}

export type RuleAction = Record<string, unknown>;

export interface Rule {
  id: string;
  name: string;
  condition: string;
  conditionText?: string;
  conditions?: Condition[];
  action?: RuleAction;
  destination: string[];
  enabled: boolean;
  state: 'draft' | 'active' | 'disabled';
  source: 'interview' | 'correction' | 'seed';
  version: number;
  priority: number;
  firedCount: number;
  lastFiredAt?: string;
  correctionsSince: number;
}

export interface RulePreview {
  rule: Rule;
  moves: { documentId: string; title: string; from: string[]; fromFileName: string; to: string[]; toFileName: string }[];
  movesTotal: number;
  stays: string[];
  staysTotal: number;
  applied: boolean;
  groupId: string | null;
}

export interface ApplyResult {
  preview: RulePreview;
  groupId: string | null;
  moved: number;
  unchanged: number;
  failed: { documentId: string; code: string }[];
}

export interface LikeThisResult {
  rule: Rule;
  preview: RulePreview;
}

export interface SettingsThresholds {
  confidenceHigh: number;
  confidenceLow: number;
  badgeHours: number;
}

export interface ShellState {
  reviewCount: number;
  processingCount: number;
  queue: { llm: number; cpu: number };
  mona: 'online' | 'offline';
}

export interface RuleDraft {
  kind: 'always' | 'depends' | 'ask';
  discriminator: ConditionField | null;
  branches: { conditions: Condition[]; action: RuleAction }[];
}

export interface InterviewOption {
  id: string;
  label: string;
  suggested?: boolean;
  ruleDraft: RuleDraft | null;
}

export interface InterviewQuestion {
  id: string;
  ordinal: number;
  question: string;
  lang: Lang;
  affects: string[];
  affectsCount: number;
  evidence: Evidence[];
  options: InterviewOption[];
  suggestionConfidence: number;
  status: 'open' | 'answered' | 'skipped';
  answer: { optionId: string | null; freeText: string | null; ruleIds: string[] } | null;
}

export type InterviewScope =
  | { type: 'batch'; batchId: string }
  | { type: 'queue' }
  | { type: 'counterparty'; counterpartyId: string }
  | { type: 'documents'; documentIds: string[] }
  | { type: 'seed' };

export type InterviewStatus = 'generating' | 'ready' | 'done' | 'failed' | 'cancelled';

export interface Interview {
  id: string;
  kind: 'seed' | 'debrief' | 'on_demand';
  status: InterviewStatus;
  questions: InterviewQuestion[];
  batchId: string | null;
  createdAt: string;
  lang: Lang;
  scope: InterviewScope;
  openQuestions: number;
  readyAt: string | null;
  finishedAt: string | null;
  error: 'no_questions' | 'generation_failed' | 'timeout' | null;
  source: 'live' | 'cache' | null;
}

export interface AnswerResult {
  question: InterviewQuestion;
  rules: Rule[];
  previews: RulePreview[];
  interviewStatus: InterviewStatus;
}

export interface ApplyAllResult {
  results: ApplyResult[];
}

export interface Draft {
  id: string;
  documentId: string;
  lang: Lang;
  status: 'generating' | 'ready' | 'failed';
  title: string | null;
  body: string | null;
  docxUrl: string | null;
}

export interface ConversationSummary {
  id: string;
  title: string;
  lastMessageAt: string;
  turnCount: number;
}
