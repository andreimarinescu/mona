import type {
  ActivityItem,
  ActivityPage,
  ApplyResult,
  Band,
  BatchDetail,
  Deadline,
  BatchSummary,
  CorrectionRequest,
  DocRefs,
  DocumentDetail,
  DocumentSummary,
  Entity,
  ExtractedField,
  FileOpResult,
  IntakeItem,
  JournalAction,
  JournalEntry,
  JournalGroup,
  PathState,
  PipelineStage,
  Reason,
  ReminderResult,
  Rule,
  RulePreview,
  UndoResult,
  UndoState,
} from '../data/dto';
import { createAccount } from './account';
import { MockError } from './errors';
import { createRegistry } from './registry';
import { listFolder, norm, parseSearchParams, searchDocuments } from './archive';
import { createExports } from './exports';
import { createInterviews } from './interviews';
import { makeId } from './ids';
import { ARCHIVE_SEED, ATELIER, CABINET, CATEGORIES, ENTITIES, FISCAL_YEAR_END, NORDTEL_AMOUNT, NORDTEL_DATES, NORDTEL_FILED_TITLES, REVIEW_SEED, SHOWCASE_FIELDS, VISITORS_ID } from './seed';
import { calendarDate, toIsoDate } from '../data/calendar';

export { norm, MockError };

type State = PathState & { entityId: string | null; categoryId: string | null; subcategoryKey: string | null };

interface Entry extends Omit<JournalEntry, 'undoState' | 'undoable' | 'before' | 'after'> {
  before: State | null;
  after: State | null;
  undoneBy?: number;
}

type Group = Omit<JournalGroup, 'counts' | 'undoState'>;

interface Plan {
  index: number;
  outcome: 'filed' | 'review' | 'unreadable';
}

interface Doc {
  summary: DocumentSummary;
  sha256: string;
  deleted: boolean;
  fields: ExtractedField[];
  plan?: Plan;
  correction?: { counterparty: string | null };
  suggestion: { entityId: string | null; categoryId: string | null; subcategoryKey: string | null; sentence: string; evidence: { field: string; quote: string }[] } | null;
}

interface Batch {
  id: string;
  groupId: string;
  title: string | null;
  visitor: boolean;
  startedAt: number;
  finishedAt: number | null;
  itemIds: string[];
  debriefAt: number | null;
  items: Map<string, IntakeItem>;
}

export interface WorldOptions {
  now?: () => number;
  stepMs?: number;
  debriefDelayMs?: number;
  exportMs?: number;
  seed?: boolean;
  /** Read by the chat handlers, not the world. */
  chatDelayMs?: number;
  draftMs?: number;
  locked?: boolean;
  autoLockMinutes?: number;
  locale?: 'en' | 'fr' | 'ro';
}

const UNDOABLE: JournalAction[] = ['file', 'move', 'rename', 'unfile', 'delete', 'undo', 'redo'];
const PIPELINE_STAGES: PipelineStage[] = ['queued', 'reading', 'ocr', 'classifying', 'filing'];

export function createWorld(options: WorldOptions = {}) {
  const now = options.now ?? (() => Date.now());
  const stepMs = options.stepMs ?? 600;
  const debriefDelayMs = options.debriefDelayMs ?? 3_000;
  let counter = 1;
  const id = (prefix: string) => makeId(prefix, counter++);

  const docs = new Map<string, Doc>();
  const batches = new Map<string, Batch>();
  const groups = new Map<string, Group>();
  const rules = new Map<string, Rule>();
  const ruleCreated = new Map<string, number>();
  const entries: Entry[] = [];
  let entrySeq = 4100;

  const entityById = (entityId: string | null): Entity | undefined => ENTITIES.find((e) => e.id === entityId);
  const category = (categoryId: string | null) => CATEGORIES.find((c) => c.id === categoryId);

  function pathFor(entityId: string | null, categoryId: string | null, subcategoryKey: string | null, at: number): string[] {
    const entity = entityById(entityId);
    const cat = category(categoryId);
    if (!entity || !cat) return [];
    const sub = cat.subcategories.find((s) => s.key === subcategoryKey);
    return [entity.folderName, `${new Date(at).getFullYear()} ${entity.folderName}`, cat.labels.fr, ...(sub ? [sub.labels.fr] : [])];
  }

  function fileNameFor(doc: Doc, at: number): string {
    const d = new Date(at).toISOString().slice(0, 10);
    const stem = (doc.summary.counterparty ?? 'Document').replace(/[^A-Za-z0-9]+/g, '');
    const ext = doc.summary.fileName.split('.').pop() ?? 'pdf';
    return `${d}_${stem}_${doc.summary.docType ?? 'doc'}.${ext}`;
  }

  function stateOf(doc: Doc): State {
    const s = doc.summary;
    return {
      location: doc.deleted ? 'trash' : s.location,
      path: s.path,
      fileName: s.fileName,
      status: s.status,
      entityId: s.entityId,
      categoryId: s.categoryId,
      subcategoryKey: s.subcategoryKey,
    };
  }

  function applyState(doc: Doc, state: State) {
    const s = doc.summary;
    doc.deleted = state.location === 'trash';
    s.location = state.location === 'archive' ? 'archive' : 'inbox';
    s.path = state.path;
    s.fileName = state.fileName;
    s.status = state.status === 'processing' ? 'review' : state.status;
    if (state.status === 'processing') s.reasons = s.reasons.length > 0 ? s.reasons : ['low'];
    s.entityId = state.entityId;
    s.entityName = entityById(state.entityId)?.displayName ?? null;
    s.categoryId = state.categoryId;
    s.subcategoryKey = state.subcategoryKey;
    if (s.status === 'filed') {
      s.reasons = [];
      s.filedAt = new Date(now()).toISOString();
    }
    doc.suggestion = s.status === 'filed' ? null : doc.suggestion;
  }

  function record(init: {
    actor: 'mona' | 'user';
    via: 'ui' | 'pipeline' | 'chat';
    action: JournalAction;
    doc?: Doc;
    before?: State | null;
    after?: State | null;
    groupId?: string | null;
    batchId?: string;
    ruleId?: string | null;
    undoOf?: number | null;
    at?: number;
    confidence?: number | null;
  }): Entry {
    const entry: Entry = {
      id: entrySeq++,
      at: new Date(init.at ?? now()).toISOString(),
      actor: init.actor,
      via: init.via,
      action: init.action,
      documentIds: init.doc ? [init.doc.summary.id] : [],
      subjectId: null,
      before: init.before ?? null,
      after: init.after ?? null,
      batchId: init.batchId,
      groupId: init.groupId ?? null,
      ruleId: init.ruleId ?? null,
      confidence: init.confidence ?? null,
      band: init.confidence == null ? null : init.confidence >= 85 ? 'high' : 'medium',
      undoOf: init.undoOf ?? null,
    };
    entries.push(entry);
    return entry;
  }

  function newGroup(kind: JournalGroup['kind'], actor: 'mona' | 'user', via: 'ui' | 'pipeline', extra: Partial<Group> = {}, at?: number): Group {
    const group: Group = {
      id: id('grp'),
      kind,
      at: new Date(at ?? now()).toISOString(),
      actor,
      via,
      batchId: null,
      ruleId: null,
      targetGroupId: null,
      ...extra,
    };
    groups.set(group.id, group);
    return group;
  }

  const entryById = (entryId: number) => entries.find((e) => e.id === entryId);

  function chainTip(e: Entry): { tip: Entry; depth: number } {
    let tip = e;
    let depth = 0;
    while (tip.undoneBy !== undefined) {
      tip = entryById(tip.undoneBy)!;
      depth += 1;
    }
    return { tip, depth };
  }

  function undoStateOf(e: Entry): UndoState {
    if (!UNDOABLE.includes(e.action)) return 'not_undoable';
    const { tip, depth } = chainTip(e);
    if (depth % 2 === 1) return 'undone';
    const doc = docs.get(e.documentIds[0] ?? '');
    const now_ = doc ? stateOf(doc) : null;
    const tipAfter = tip.after;
    if (!doc || !tipAfter || !now_ || now_.location !== tipAfter.location || now_.path.join('/') !== tipAfter.path.join('/') || now_.fileName !== tipAfter.fileName) return 'superseded';
    return 'undoable';
  }

  function dto(e: Entry): JournalEntry {
    const undoState = undoStateOf(e);
    return { ...e, undoState, undoable: undoState === 'undoable' };
  }

  function groupDto(g: Group): JournalGroup {
    const inGroup = entries.filter((e) => e.groupId === g.id && UNDOABLE.includes(e.action));
    const states = inGroup.map(undoStateOf);
    const count = (s: UndoState) => states.filter((x) => x === s).length;
    const undoable = count('undoable');
    const undone = count('undone');
    const undoState: JournalGroup['undoState'] = undoable === inGroup.length && undoable > 0 ? 'undoable' : undoable > 0 ? 'partial' : undone > 0 ? 'undone' : 'not_undoable';
    return { ...g, counts: { entries: entries.filter((e) => e.groupId === g.id).length, undoable, superseded: count('superseded'), undone }, undoState };
  }

  function badgeUntil(s: DocumentSummary): string | null {
    if (s.status !== 'filed' || s.filedBy !== 'mona' || !s.filedAt) return null;
    const until = Date.parse(s.filedAt) + 24 * 3_600_000;
    return now() < until ? new Date(until).toISOString() : null;
  }

  function summaryOf(doc: Doc): DocumentSummary {
    const s = { ...doc.summary };
    s.badgeUntil = badgeUntil(s);
    s.thumbnailUrl = s.status === 'processing' ? null : `/api/documents/${s.id}/thumbnail`;
    return s;
  }

  const reminders = new Map<string, { id: string; targetId: string; remindOn: string }>();
  const deadlineStatus = new Map<string, Deadline['status']>();
  const counterpartyIds = new Map<string, string>();
  const ruleIds = new Map<string, string>();
  const today = () => toIsoDate(new Date(now()));
  const deadlineIdOf = (doc: Doc) => doc.summary.id.replace(/^doc_/, 'ddl_');

  function counterpartyId(name: string): string {
    if (!counterpartyIds.has(name)) counterpartyIds.set(name, makeId('cpt', counterpartyIds.size + 1));
    return counterpartyIds.get(name)!;
  }

  function fiscalYearOf(entityId: string, date: string): number {
    const y = Number(date.slice(0, 4));
    const end = FISCAL_YEAR_END[entityId];
    return end && date.slice(5) > end ? y + 1 : y;
  }

  function deadlinesOf(doc: Doc): Deadline[] {
    const s = doc.summary;
    if (!s.dueDate || s.status === 'processing') return [];
    const id = deadlineIdOf(doc);
    const reminder = [...reminders.values()].find((r) => r.targetId === id || r.targetId === s.id);
    const daysLeft = Math.round((calendarDate(s.dueDate).getTime() - calendarDate(today()).getTime()) / 86_400_000);
    return [
      { id, documentId: s.id, label: s.title, entityId: s.entityId ?? '', entityName: s.entityName ?? '', dueDate: s.dueDate, amount: s.amount, status: deadlineStatus.get(id) ?? 'open', daysLeft, reminder: reminder ? { id: reminder.id, remindOn: reminder.remindOn } : null },
    ];
  }

  function detailOf(doc: Doc): DocumentDetail {
    const s = summaryOf(doc);
    const sg = doc.suggestion;
    const reviewable = s.status === 'review' || s.status === 'unreadable';
    const band: Band = (s.confidence ?? 0) >= 85 ? 'high' : (s.confidence ?? 0) >= 60 ? 'medium' : 'low';
    return {
      ...s,
      fields: doc.fields,
      deadlines: deadlinesOf(doc),
      suggestion:
        reviewable && sg
          ? {
              entityId: sg.entityId,
              subUnitId: null,
              categoryId: sg.categoryId,
              subcategoryKey: sg.subcategoryKey,
              fileName: sg.entityId ? fileNameFor(doc, Date.parse(s.arrivedAt)) : null,
              path: pathFor(sg.entityId, sg.categoryId, sg.subcategoryKey, Date.parse(s.arrivedAt)),
              confidence: s.confidence ?? 0,
              band,
              reasons: s.reasons,
              sentence: sg.sentence,
              evidence: sg.evidence.map((ev) => ({
                documentId: s.id,
                documentTitle: s.title,
                field: ev.field as never,
                page: 1,
                quote: ev.quote,
                verified: true,
                findQuery: ev.quote.slice(0, 40),
              })),
              ruleId: null,
              conflictingRuleIds: [],
            }
          : null,
      journal: entries
        .filter((e) => e.documentIds.includes(s.id))
        .sort((a, b) => b.id - a.id)
        .map(dto),
    };
  }

  function addDoc(init: { title: string; fileName: string; counterparty: string | null; docType: string; batchId: string; arrivedAt: number; source?: 'drop' | 'telegram'; sha256?: string; status?: DocumentSummary['status']; pipelineStage?: PipelineStage }): Doc {
    const docId = id('doc');
    const summary: DocumentSummary = {
      id: docId,
      title: init.title,
      originalName: init.fileName,
      fileName: init.fileName,
      path: [],
      location: 'inbox',
      entityId: null,
      entityName: null,
      subUnitId: null,
      categoryId: null,
      subcategoryKey: null,
      counterpartyId: null,
      counterparty: init.counterparty,
      docType: init.docType,
      reference: null,
      date: null,
      periodStart: null,
      periodEnd: null,
      fiscalYear: null,
      dueDate: null,
      status: init.status ?? 'processing',
      reasons: [],
      confidence: null,
      band: null,
      pipelineStage: init.pipelineStage ?? 'queued',
      arrivedAt: new Date(init.arrivedAt).toISOString(),
      source: init.source ?? 'drop',
      filedAt: null,
      filedBy: null,
      badgeUntil: null,
      rule: null,
      batchId: init.batchId,
      pageCount: 1,
      thumbnailUrl: null,
      pdfUrl: `/api/documents/${docId}/pdf`,
    };
    const doc: Doc = { summary, sha256: init.sha256 ?? docId.padEnd(64, '0').replace(/[^0-9a-f]/g, '0'), deleted: false, fields: [], suggestion: null };
    docs.set(docId, doc);
    return doc;
  }

  function fileDoc(doc: Doc, entityId: string, categoryId: string, subcategoryKey: string | null, by: { actor: 'mona' | 'user'; via: 'ui' | 'pipeline'; groupId: string | null; batchId?: string; at?: number; confidence?: number; fileName?: string }) {
    const s = doc.summary;
    const at = by.at ?? now();
    const before = stateOf(doc);
    s.entityId = entityId;
    s.entityName = entityById(entityId)?.displayName ?? null;
    s.categoryId = categoryId;
    s.subcategoryKey = subcategoryKey;
    s.path = pathFor(entityId, categoryId, subcategoryKey, at);
    s.location = 'archive';
    s.status = 'filed';
    s.reasons = [];
    s.fileName = by.fileName ?? fileNameFor(doc, at);
    s.filedAt = new Date(at).toISOString();
    s.filedBy = by.actor;
    s.pipelineStage = 'done';
    s.confidence = by.confidence ?? s.confidence;
    s.band = 'high';
    doc.suggestion = null;
    return record({ actor: by.actor, via: by.via, action: 'file', doc, before, after: stateOf(doc), groupId: by.groupId, batchId: by.batchId, at, confidence: by.confidence ?? null });
  }

  function seed() {
    const t0 = now();
    const hours = (h: number) => t0 - h * 3_600_000;
    const batchId = id('bat');
    const seedGroup = newGroup('intake_batch', 'mona', 'pipeline', { batchId }, hours(32));
    batches.set(batchId, { id: batchId, groupId: seedGroup.id, title: 'Overnight batch', visitor: false, startedAt: hours(33), finishedAt: hours(32), itemIds: [], debriefAt: null, items: new Map() });

    for (const item of REVIEW_SEED) {
      const doc = addDoc({ title: item.title, fileName: item.fileName, counterparty: item.counterparty, docType: item.docType, batchId, arrivedAt: hours(item.hoursAgo), source: item.source, status: item.status, pipelineStage: 'done' });
      const s = doc.summary;
      s.reasons = item.reasons as Reason[];
      if (item.entityId) {
        s.date = toIsoDate(new Date(hours(item.hoursAgo)));
        s.fiscalYear = fiscalYearOf(item.entityId, s.date);
      }
      if (item.counterparty) s.counterpartyId = counterpartyId(item.counterparty);
      s.confidence = item.confidence;
      s.band = item.confidence == null ? null : item.confidence >= 85 ? 'high' : item.confidence >= 60 ? 'medium' : 'low';
      s.entityId = item.entityId;
      s.entityName = entityById(item.entityId)?.displayName ?? null;
      s.categoryId = item.categoryId;
      s.subcategoryKey = item.subcategoryKey;
      doc.suggestion = { entityId: item.entityId, categoryId: item.categoryId, subcategoryKey: item.subcategoryKey, sentence: item.sentence, evidence: item.evidence };
      if (item.status === 'unreadable') {
        record({ actor: 'mona', via: 'pipeline', action: 'mark.unreadable', doc, before: null, after: stateOf(doc), groupId: seedGroup.id, batchId, at: hours(item.hoursAgo - 1) });
      }
    }

    NORDTEL_FILED_TITLES.forEach((title, i) => {
      const doc = addDoc({ title, fileName: `Nordtel_Pro_0${6 + i}26.pdf`, counterparty: 'Nordtel', docType: 'invoice', batchId, arrivedAt: hours(2_000 - i * 700), status: 'filed', pipelineStage: 'done' });
      doc.summary.reasons = [];
      Object.assign(doc.summary, { date: NORDTEL_DATES[i], fiscalYear: fiscalYearOf(ATELIER.id, NORDTEL_DATES[i]!), amount: { value: NORDTEL_AMOUNT, currency: 'EUR' }, counterpartyId: counterpartyId('Nordtel') });
      fileDoc(doc, ATELIER.id, 'invoices', 'telecom', { actor: 'mona', via: 'pipeline', groupId: seedGroup.id, batchId, at: hours(40 + i), confidence: 93 });
    });

    const edf = addDoc({ title: 'Energie Verte bill, September', fileName: 'EnergieVerte_facture_sept.pdf', counterparty: 'Energie Verte', docType: 'invoice', batchId, arrivedAt: hours(60), status: 'filed', pipelineStage: 'done' });
    edf.summary.reasons = [];
    Object.assign(edf.summary, { date: '2026-09-05', fiscalYear: 2026, amount: { value: 148.2, currency: 'EUR' }, counterpartyId: counterpartyId('Energie Verte') });
    fileDoc(edf, CABINET.id, 'invoices', 'supplies', { actor: 'mona', via: 'pipeline', groupId: seedGroup.id, batchId, at: hours(50), confidence: 91 });
    const moveBefore = stateOf(edf);
    edf.summary.entityId = ATELIER.id;
    edf.summary.entityName = ATELIER.displayName;
    edf.summary.path = pathFor(ATELIER.id, 'invoices', 'supplies', hours(24));
    edf.summary.filedBy = 'user';
    edf.summary.filedAt = new Date(hours(24)).toISOString();
    record({ actor: 'user', via: 'ui', action: 'move', doc: edf, before: moveBefore, after: stateOf(edf), at: hours(24) });

    for (const item of ARCHIVE_SEED) {
      const at = calendarDate(item.date).getTime() + 9 * 3_600_000;
      const doc = addDoc({ title: item.title, fileName: item.fileName, counterparty: item.counterparty, docType: item.docType, batchId, arrivedAt: at, pipelineStage: 'done' });
      const s = doc.summary;
      Object.assign(s, {
        date: item.date,
        fiscalYear: fiscalYearOf(item.entityId, item.date),
        counterpartyId: counterpartyId(item.counterparty),
        reference: item.reference ?? null,
        dueDate: item.dueDate ?? null,
        pageCount: item.showcase ? 1 : 2,
        amount: item.amount === undefined ? undefined : { value: item.amount, currency: 'EUR' },
      });
      if (item.rule) {
        if (!ruleIds.has(item.rule)) ruleIds.set(item.rule, makeId('rul', 900 + ruleIds.size));
        s.rule = { id: ruleIds.get(item.rule)!, name: item.rule };
      }
      const filedBy = item.filedBy ?? 'mona';
      fileDoc(doc, item.entityId, item.categoryId, item.subcategoryKey, { actor: filedBy, via: filedBy === 'user' ? 'ui' : 'pipeline', groupId: null, batchId, at, confidence: 96, fileName: item.fileName });
      if (!item.showcase) entries.pop();
      else {
        s.confidence = 96;
        record({ actor: 'mona', via: 'pipeline', action: 'deadline.add', doc, batchId, at: at + 1_000 });
        doc.fields = SHOWCASE_FIELDS.map((f) => ({
          key: f.key,
          value: f.value,
          money: f.money,
          confidence: f.confidence,
          evidence: { documentId: s.id, documentTitle: s.title, field: f.key, page: f.page, quote: f.quote, verified: f.verified, findQuery: f.findQuery },
        }));
      }
    }
  }

  function batchSummary(batch: Batch): BatchSummary {
    const accepted = [...batch.items.values()].filter((i) => i.outcome === 'accepted');
    const live = accepted.map((i) => docs.get(i.documentId!)!);
    const count = (pred: (d: Doc) => boolean) => live.filter(pred).length;
    const counts = {
      items: batch.items.size,
      accepted: accepted.length,
      duplicate: [...batch.items.values()].filter((i) => i.outcome === 'duplicate').length,
      rejected: [...batch.items.values()].filter((i) => i.outcome === 'rejected').length,
      processing: count((d) => d.summary.status === 'processing'),
      filed: count((d) => d.summary.status === 'filed'),
      review: count((d) => d.summary.status === 'review'),
      unreadable: count((d) => d.summary.status === 'unreadable'),
      failed: 0,
    };
    const status: BatchSummary['status'] = batch.finishedAt === null ? 'running' : 'done';
    const debriefReady = batch.debriefAt !== null && now() >= batch.debriefAt && counts.review > 0;
    const reviewIds = live.filter((d) => d.summary.status === 'review').map((d) => d.summary.id);
    const iv = interviews.forBatch(batch.id) ?? (debriefReady ? interviews.debrief(batch.id, reviewIds) : null);
    return {
      id: batch.id,
      source: 'drop',
      status,
      title: batch.title,
      visitor: batch.visitor,
      startedAt: new Date(batch.startedAt).toISOString(),
      finishedAt: batch.finishedAt === null ? null : new Date(batch.finishedAt).toISOString(),
      counts,
      groupId: batch.groupId,
      debrief: iv ? { interviewId: iv.id, status: iv.status, openQuestions: iv.openQuestions } : null,
    };
  }

  function tick() {
    const t = now();
    for (const batch of batches.values()) {
      if (batch.finishedAt !== null) continue;
      batch.itemIds.forEach((itemId) => {
        const item = batch.items.get(itemId)!;
        const doc = item.documentId ? docs.get(item.documentId) : undefined;
        if (!doc?.plan || doc.summary.status !== 'processing') return;
        const elapsed = t - batch.startedAt - doc.plan.index * stepMs;
        const step = Math.floor(elapsed / stepMs);
        if (step < PIPELINE_STAGES.length) {
          doc.summary.pipelineStage = PIPELINE_STAGES[Math.max(0, step)]!;
          return;
        }
        const finishedAt = batch.startedAt + (doc.plan.index + PIPELINE_STAGES.length) * stepMs;
        const s = doc.summary;
        s.pipelineStage = 'done';
        s.thumbnailUrl = `/api/documents/${s.id}/thumbnail`;
        if (doc.plan.outcome === 'filed') {
          const entityId = batch.visitor ? VISITORS_ID : CABINET.id;
          s.confidence = 92;
          fileDoc(doc, entityId, 'invoices', 'supplies', { actor: 'mona', via: 'pipeline', groupId: batch.groupId, batchId: batch.id, at: finishedAt, confidence: 92 });
        } else if (doc.plan.outcome === 'review') {
          s.status = 'review';
          s.reasons = ['low'];
          s.confidence = 64;
          s.band = 'low';
          s.entityId = CABINET.id;
          s.entityName = CABINET.displayName;
          s.categoryId = 'invoices';
          doc.suggestion = {
            entityId: CABINET.id,
            categoryId: 'invoices',
            subcategoryKey: null,
            sentence: `I think this document from ${s.counterparty ?? 'an unknown sender'} belongs to ${CABINET.displayName}, but I'm not sure enough to file it.`,
            evidence: [{ field: 'counterparty', quote: s.counterparty ?? s.title }],
          };
        } else {
          s.status = 'unreadable';
          s.reasons = ['unreadable'];
          s.confidence = null;
          doc.suggestion = { entityId: null, categoryId: null, subcategoryKey: null, sentence: "I can't read this document. Could you scan it again, or take a clearer photo?", evidence: [] };
          record({ actor: 'mona', via: 'pipeline', action: 'mark.unreadable', doc, before: null, after: stateOf(doc), groupId: batch.groupId, batchId: batch.id, at: finishedAt });
        }
      });
      const running = [...batch.items.values()].some((i) => i.outcome === 'accepted' && docs.get(i.documentId!)?.summary.status === 'processing');
      if (!running) {
        batch.finishedAt = t;
        batch.debriefAt = t + debriefDelayMs;
      }
    }
  }

  function planFor(name: string): Plan['outcome'] {
    const n = name.toLowerCase();
    if (n.includes('blurry') || n.includes('unreadable')) return 'unreadable';
    if (n.includes('unknown') || n.includes('scan')) return 'review';
    return 'filed';
  }

  async function intake(files: { name: string; type: string; bytes: Uint8Array }[], opts: { visitor: boolean; title?: string }) {
    if (files.length > 50 || files.some((f) => f.bytes.length > 25 * 1024 * 1024)) throw new MockError(413, 'too_large', 'Upload over the limits.');
    const startedAt = now();
    const batch: Batch = { id: id('bat'), groupId: '', title: opts.title ?? null, visitor: opts.visitor, startedAt, finishedAt: null, itemIds: [], debriefAt: null, items: new Map() };
    const group = newGroup('intake_batch', 'mona', 'pipeline', { batchId: batch.id });
    batch.groupId = group.id;
    batches.set(batch.id, batch);
    let accepted = 0;
    for (const file of files) {
      const itemId = id('itm');
      const digest = await crypto.subtle.digest('SHA-256', file.bytes as BufferSource);
      const sha256 = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
      const pdf = file.bytes.length >= 4 && String.fromCharCode(...file.bytes.slice(0, 4)) === '%PDF';
      const png = file.bytes.length >= 4 && file.bytes[0] === 0x89 && file.bytes[1] === 0x50;
      const jpg = file.bytes.length >= 3 && file.bytes[0] === 0xff && file.bytes[1] === 0xd8;
      const base: IntakeItem = { id: itemId, originalName: file.name, sha256, sizeBytes: file.bytes.length, outcome: 'accepted', rejectReason: null, documentId: null, deleted: false, restoreJournalId: null };
      const existing = [...docs.values()].find((d) => d.sha256 === sha256);
      if (file.bytes.length === 0) Object.assign(base, { outcome: 'rejected', rejectReason: 'empty' });
      else if (!pdf && !png && !jpg) Object.assign(base, { outcome: 'rejected', rejectReason: 'unsupported_type' });
      else if (existing) {
        const del = existing.deleted ? [...entries].reverse().find((e) => e.action === 'delete' && e.documentIds[0] === existing.summary.id) : undefined;
        Object.assign(base, { outcome: 'duplicate', documentId: existing.summary.id, deleted: existing.deleted, restoreJournalId: del?.id ?? null });
      } else {
        const title = file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ');
        const doc = addDoc({ title, fileName: file.name, counterparty: title.split(' ')[0] ?? null, docType: 'document', batchId: batch.id, arrivedAt: startedAt, sha256 });
        doc.plan = { index: accepted, outcome: planFor(file.name) };
        accepted += 1;
        base.documentId = doc.summary.id;
      }
      batch.itemIds.push(itemId);
      batch.items.set(itemId, base);
    }
    if (accepted === 0) {
      batch.finishedAt = startedAt;
      batch.debriefAt = null;
    }
    return { batch: batchSummary(batch), items: batch.itemIds.map((i) => batch.items.get(i)!) };
  }

  function batchDetail(batchId: string): BatchDetail {
    tick();
    const batch = batches.get(batchId);
    if (!batch) throw new MockError(404, 'not_found', 'Unknown batch.');
    return {
      batch: batchSummary(batch),
      items: batch.itemIds.map((i) => {
        const item = batch.items.get(i)!;
        const doc = item.documentId ? docs.get(item.documentId) : undefined;
        return { ...item, document: doc ? summaryOf(doc) : null };
      }),
    };
  }

  function latestBatch() {
    tick();
    const all = [...batches.values()].sort((a, b) => b.startedAt - a.startedAt);
    return { items: all.slice(0, 1).map(batchSummary), total: all.length, offset: 0, limit: 1 };
  }

  function reviewList(filter: { reason?: string; entityId?: string | null; offset?: number; limit?: number }) {
    tick();
    const items = [...docs.values()]
      .filter((d) => !d.deleted && (d.summary.status === 'review' || d.summary.status === 'unreadable'))
      .filter((d) => !filter.reason || d.summary.reasons.includes(filter.reason as Reason))
      .filter((d) => !filter.entityId || d.summary.entityId === filter.entityId)
      .sort((a, b) => Date.parse(a.summary.arrivedAt) - Date.parse(b.summary.arrivedAt))
      .map(summaryOf);
    const offset = filter.offset ?? 0;
    const limit = filter.limit ?? 50;
    return { items: items.slice(offset, offset + limit), total: items.length, offset, limit };
  }

  function getDoc(docId: string): Doc {
    tick();
    const doc = docs.get(docId);
    if (!doc || doc.deleted) throw new MockError(404, 'not_found', 'Unknown document.');
    return doc;
  }

  const document = (docId: string) => detailOf(getDoc(docId));

  function result(doc: Doc, outcome: FileOpResult['outcome'], ids: number[], groupId: string | null, undo: FileOpResult['undo']): FileOpResult {
    return { document: detailOf(doc), outcome, journalIds: ids, groupId, undo };
  }

  function confirm(docId: string): FileOpResult {
    const doc = getDoc(docId);
    if (doc.summary.status === 'filed') return result(doc, 'unchanged', [], null, null);
    const sg = doc.suggestion;
    if (!sg?.entityId || !sg.categoryId) throw new MockError(422, 'not_renderable', 'No entity.');
    const entry = fileDoc(doc, sg.entityId, sg.categoryId, sg.subcategoryKey, { actor: 'user', via: 'ui', groupId: null });
    doc.summary.filedBy = 'user';
    return result(doc, 'moved', [entry.id], null, { journalId: entry.id });
  }

  function correct(docId: string, body: CorrectionRequest): FileOpResult {
    const doc = getDoc(docId);
    if (doc.summary.entityId === VISITORS_ID || body.entityId === VISITORS_ID) throw new MockError(403, 'not_allowed', 'Visitors is not a target.');
    const s = doc.summary;
    const entityId = body.entityId ?? s.entityId ?? doc.suggestion?.entityId ?? null;
    const categoryId = body.categoryId ?? s.categoryId ?? doc.suggestion?.categoryId ?? null;
    if (!entityId || !categoryId) throw new MockError(422, 'not_renderable', 'No entity.');
    const subcategoryKey = body.subcategoryKey !== undefined ? body.subcategoryKey : body.categoryId ? null : (s.subcategoryKey ?? null);
    const group = newGroup('correction', 'user', 'ui');
    const wasFiled = s.status === 'filed';
    const before = stateOf(doc);
    let entry: Entry;
    if (wasFiled) {
      const at = now();
      s.entityId = entityId;
      s.entityName = entityById(entityId)?.displayName ?? null;
      s.categoryId = categoryId;
      s.subcategoryKey = subcategoryKey;
      s.path = pathFor(entityId, categoryId, subcategoryKey, at);
      s.filedBy = 'user';
      entry = record({ actor: 'user', via: 'ui', action: 'move', doc, before, after: stateOf(doc), groupId: group.id });
    } else {
      entry = fileDoc(doc, entityId, categoryId, subcategoryKey, { actor: 'user', via: 'ui', groupId: group.id });
      s.filedBy = 'user';
    }
    doc.correction = { counterparty: s.counterparty };
    return result(doc, 'moved', [entry.id], group.id, { groupId: group.id });
  }

  const correctionRules = new Set<string>();

  function ruleFor(doc: Doc): Rule {
    const existing = [...rules.values()].find((r) => correctionRules.has(r.id) && r.name.startsWith(doc.summary.counterparty ?? ''));
    if (existing) return existing;
    const rule: Rule = {
      id: id('rul'),
      name: `${doc.summary.counterparty}: ${entityById(doc.summary.entityId)?.displayName ?? ''}`,
      condition: `Counterparty is ${doc.summary.counterparty}`,
      destination: pathFor(doc.summary.entityId, doc.summary.categoryId, doc.summary.subcategoryKey, now()),
      enabled: false,
      state: 'draft',
      source: 'correction',
      version: 1,
      priority: 100,
      firedCount: 0,
      correctionsSince: 0,
    };
    rules.set(rule.id, rule);
    correctionRules.add(rule.id);
    ruleCreated.set(rule.id, now());
    return rule;
  }

  function candidates(source: Doc): Doc[] {
    return [...docs.values()].filter(
      (d) => !d.deleted && d.summary.id !== source.summary.id && d.summary.status === 'filed' && d.summary.counterparty === source.summary.counterparty && d.summary.entityId !== source.summary.entityId,
    );
  }

  /** What a rule moves: a like-this rule follows its corrected document, an interview rule its branch. */
  interface RuleTarget {
    candidates(): Doc[];
    stays(): string[];
    place(d: Doc, groupId: string): void;
  }
  const ruleTargets = new Map<string, RuleTarget>();
  const ruleGroups = new Map<string, string>();

  function preview(rule: Rule): RulePreview {
    const target = ruleTargets.get(rule.id)!;
    const groupId = ruleGroups.get(rule.id) ?? null;
    const applied = groupId !== null && groupDto(groups.get(groupId)!).undoState !== 'undone';
    const moves = applied
      ? entries
          .filter((e) => e.groupId === groupId && (e.action === 'move' || e.action === 'file'))
          .map((e) => ({ documentId: e.documentIds[0]!, title: docs.get(e.documentIds[0]!)!.summary.title, from: e.before!.path, fromFileName: e.before!.fileName, to: e.after!.path, toFileName: e.after!.fileName }))
      : target.candidates().map((d) => ({
          documentId: d.summary.id,
          title: d.summary.title,
          from: d.summary.path,
          fromFileName: d.summary.fileName,
          to: rule.destination,
          toFileName: d.summary.fileName,
        }));
    const stays = target.stays();
    return { rule: { ...rule }, moves, movesTotal: moves.length, stays, staysTotal: stays.length, applied, groupId: applied ? groupId : null };
  }

  function likeThis(docId: string) {
    const doc = getDoc(docId);
    if (!doc.correction) throw new MockError(404, 'not_found', 'No correction.');
    if (!doc.summary.counterparty) throw new MockError(422, 'invalid_value', 'No counterparty.', 'counterparty');
    const rule = ruleFor(doc);
    ruleTargets.set(rule.id, {
      candidates: () => candidates(doc),
      stays: () => [doc.summary.id],
      place: (d, groupId) => {
        const before = stateOf(d);
        d.summary.entityId = doc.summary.entityId;
        d.summary.entityName = doc.summary.entityName;
        d.summary.path = rule.destination;
        d.summary.filedBy = 'user';
        record({ actor: 'user', via: 'ui', action: 'move', doc: d, before, after: stateOf(d), groupId, ruleId: rule.id });
      },
    });
    return { rule, preview: preview(rule) };
  }

  function registerRule(rule: Rule, target: RuleTarget) {
    rules.set(rule.id, rule);
    ruleTargets.set(rule.id, target);
  }

  /** Files a document at an explicit place, as a rule application does (one journal `file` entry). */
  function fileTo(d: Doc, to: { entityId: string; categoryId: string; subcategoryKey: string | null; path: string[] }, groupId: string, ruleId: string) {
    const before = stateOf(d);
    const s = d.summary;
    Object.assign(s, { entityId: to.entityId, entityName: entityById(to.entityId)?.displayName ?? null, categoryId: to.categoryId, subcategoryKey: to.subcategoryKey, path: to.path });
    Object.assign(s, { location: 'archive', status: 'filed', reasons: [], filedAt: new Date(now()).toISOString(), filedBy: 'user', rule: { id: ruleId, name: rules.get(ruleId)?.name ?? '' } });
    record({ actor: 'user', via: 'ui', action: 'file', doc: d, before, after: stateOf(d), groupId, ruleId });
  }

  const notes: { conversationId: string; kind: string; text: string; consumed: boolean }[] = [];
  function note(conversationId: string | undefined, kind: string, text: string) {
    if (conversationId) notes.push({ conversationId, kind, text, consumed: false });
  }
  function consumeNotes(conversationId: string): string[] {
    return notes.filter((n) => n.conversationId === conversationId && !n.consumed).map((n) => {
      n.consumed = true;
      return n.text;
    });
  }

  function applyRule(ruleId: string, conversationId?: string): ApplyResult {
    const rule = rules.get(ruleId);
    if (!rule) throw new MockError(404, 'not_found', 'Unknown rule.');
    const current = preview(rule);
    if (current.applied) return { preview: current, groupId: null, moved: 0, unchanged: current.movesTotal, failed: [] };
    const group = newGroup('rule_apply', 'user', 'ui', { ruleId });
    ruleGroups.set(ruleId, group.id);
    record({ actor: 'user', via: 'ui', action: 'rule.change', groupId: group.id, ruleId });
    rule.state = 'active';
    rule.enabled = true;
    for (const d of ruleTargets.get(ruleId)!.candidates()) ruleTargets.get(ruleId)!.place(d, group.id);
    const after = preview(rule);
    note(conversationId, 'rule.apply', `Applied the rule "${rule.name}": ${after.movesTotal} documents moved, ${after.staysTotal} already in place.`);
    return { preview: after, groupId: group.id, moved: after.movesTotal, unchanged: 0, failed: [] };
  }

  function undoEntry(e: Entry, groupId: string | null): Entry {
    const { tip } = chainTip(e);
    const doc = docs.get(e.documentIds[0]!)!;
    const next = record({ actor: 'user', via: 'ui', action: tip.action === 'undo' ? 'redo' : 'undo', doc, before: tip.after, after: tip.before, groupId, undoOf: tip.id });
    tip.undoneBy = next.id;
    if (tip.before) applyState(doc, tip.before);
    if (tip.before?.status === 'processing') {
      doc.summary.status = 'review';
      doc.suggestion ??= { entityId: null, categoryId: null, subcategoryKey: null, sentence: "I couldn't file this one with enough confidence.", evidence: [] };
    }
    return next;
  }

  function entryUndo(entryId: number, conversationId?: string): UndoResult {
    tick();
    const e = entryById(entryId);
    if (!e) throw new MockError(404, 'not_found', 'Unknown entry.');
    const state = undoStateOf(e);
    if (state === 'not_undoable') throw new MockError(422, 'not_undoable', 'Not undoable.');
    if (state === 'undone') throw new MockError(409, 'already_undone', 'Already undone.');
    if (state === 'superseded') throw new MockError(409, 'superseded', 'Superseded.');
    const next = undoEntry(e, null);
    note(conversationId, 'undo', `Undid 1 change(s): ${docs.get(e.documentIds[0]!)!.summary.title}.`);
    return {
      groupId: null,
      undone: [{ journalId: e.id, documentId: e.documentIds[0]!, title: docs.get(e.documentIds[0]!)!.summary.title, to: next.after! }],
      skipped: [],
      entries: [dto(next)],
      ruleStates: [],
    };
  }

  function groupUndo(groupId: string, conversationId?: string): UndoResult {
    tick();
    const g = groups.get(groupId);
    if (!g) throw new MockError(404, 'not_found', 'Unknown group.');
    const targets = entries.filter((e) => e.groupId === groupId && UNDOABLE.includes(e.action)).sort((a, b) => b.id - a.id);
    const live = targets.filter((e) => undoStateOf(e) === 'undoable');
    if (live.length === 0) throw new MockError(targets.some((e) => undoStateOf(e) === 'undone') ? 409 : 422, targets.some((e) => undoStateOf(e) === 'undone') ? 'already_undone' : 'not_undoable', 'Nothing to undo.');
    const u = newGroup(g.kind === 'undo' ? 'redo' : 'undo', 'user', 'ui', { targetGroupId: g.id });
    const created: Entry[] = [];
    const undone: UndoResult['undone'] = [];
    const skipped: UndoResult['skipped'] = [];
    for (const e of targets) {
      if (undoStateOf(e) !== 'undoable') {
        skipped.push({ journalId: e.id, state: undoStateOf(e) === 'undone' ? 'already_undone' : 'superseded' });
        continue;
      }
      const next = undoEntry(e, u.id);
      created.push(next);
      undone.push({ journalId: e.id, documentId: e.documentIds[0]!, title: docs.get(e.documentIds[0]!)!.summary.title, to: next.after! });
    }
    const ruleStates: UndoResult['ruleStates'] = [];
    if (g.ruleId) {
      const rule = rules.get(g.ruleId);
      if (rule) {
        rule.state = 'draft';
        rule.enabled = false;
        ruleStates.push({ ruleId: rule.id, state: 'draft' });
      }
    }
    note(conversationId, 'undo', `Undid ${undone.length} change(s): ${g.ruleId ? `the rule "${rules.get(g.ruleId)?.name ?? ''}"` : 'a group'}.`);
    return { groupId: u.id, undone, skipped, entries: created.map(dto), ruleStates };
  }

  function activity(filter: { actor?: string; entityId?: string; kind?: string; q?: string; cursor?: string; limit?: number }): ActivityPage {
    tick();
    type Item = { at: number; key: string; item: ActivityItem };
    const all: Item[] = [];
    const docIds = new Set<string>();
    const ruleIds = new Set<string>();
    const matchDoc = (docId: string | undefined) => {
      if (!filter.entityId && !filter.q) return true;
      const d = docId ? docs.get(docId) : undefined;
      if (!d) return false;
      if (filter.entityId && d.summary.entityId !== filter.entityId) return false;
      if (filter.q && !norm(`${d.summary.title} ${d.summary.fileName}`).includes(norm(filter.q))) return false;
      return true;
    };
    for (const g of groups.values()) {
      const inGroup = entries.filter((e) => e.groupId === g.id);
      if (inGroup.length === 0 || (filter.actor && g.actor !== filter.actor)) continue;
      if (filter.kind && g.kind !== filter.kind) continue;
      if (!inGroup.some((e) => e.documentIds.length === 0 ? !filter.entityId && !filter.q : matchDoc(e.documentIds[0]))) continue;
      const target = [...groups.values()].find((x) => x.targetGroupId === g.id && groupDto(x).undoState !== 'undone');
      all.push({ at: Date.parse(g.at), key: `${g.at}|${g.id}`, item: { kind: 'group', group: groupDto(g), preview: inGroup.slice(0, 5).map(dto), entriesTotal: inGroup.length, redoGroupId: target?.id ?? null } });
    }
    for (const e of entries) {
      if (e.groupId !== null || (filter.actor && e.actor !== filter.actor)) continue;
      if (filter.kind && e.action !== filter.kind) continue;
      if (e.documentIds.length === 0 ? filter.entityId || filter.q : !matchDoc(e.documentIds[0])) continue;
      all.push({ at: Date.parse(e.at), key: `${e.at}|${String(e.id).padStart(8, '0')}`, item: { kind: 'entry', entry: dto(e) } });
    }
    all.sort((a, b) => (a.key < b.key ? 1 : -1));
    const limit = filter.limit ?? 30;
    const start = filter.cursor ? all.findIndex((i) => i.key === filter.cursor) + 1 : 0;
    const page = all.slice(start, start + limit);
    const nextCursor = start + limit < all.length ? page[page.length - 1]!.key : null;
    const collect = (e: JournalEntry) => {
      if (e.documentIds[0]) docIds.add(e.documentIds[0]);
      if (e.ruleId) ruleIds.add(e.ruleId);
    };
    for (const { item } of page) {
      if (item.kind === 'entry') collect(item.entry);
      else {
        if (item.group.ruleId) ruleIds.add(item.group.ruleId);
        item.preview.forEach(collect);
      }
    }
    return { items: page.map((p) => p.item), nextCursor, documents: docRefs(docIds), rules: ruleRefs(ruleIds) };
  }

  function docRefs(ids: Iterable<string>): DocRefs {
    const out: DocRefs = {};
    for (const docId of ids) {
      const d = docs.get(docId);
      if (d) out[docId] = { title: d.summary.title, fileName: d.summary.fileName, deleted: d.deleted };
    }
    return out;
  }

  function ruleRefs(ids: Iterable<string>) {
    const out: Record<string, { name: string }> = {};
    for (const ruleId of ids) {
      const r = rules.get(ruleId);
      if (r) out[ruleId] = { name: r.name };
    }
    return out;
  }

  function groupView(groupId: string) {
    tick();
    const g = groups.get(groupId);
    if (!g) throw new MockError(404, 'not_found', 'Unknown group.');
    const inGroup = entries.filter((e) => e.groupId === groupId);
    return { group: groupDto(g), entries: inGroup.map(dto), documents: docRefs(inGroup.flatMap((e) => e.documentIds)) };
  }

  function shell() {
    tick();
    const all = [...docs.values()].filter((d) => !d.deleted);
    return {
      reviewCount: all.filter((d) => d.summary.status === 'review' || d.summary.status === 'unreadable').length,
      processingCount: all.filter((d) => d.summary.status === 'processing').length,
      queue: { llm: 0, cpu: 0 },
      mona: account.mona(),
    };
  }

  function entityList() {
    const counts: Record<string, number> = {};
    for (const d of docs.values()) if (!d.deleted && d.summary.entityId) counts[d.summary.entityId] = (counts[d.summary.entityId] ?? 0) + 1;
    return { items: ENTITIES, documentCounts: counts, visitorsEntityId: VISITORS_ID };
  }

  const liveSummaries = () => [...docs.values()].filter((d) => !d.deleted).map(summaryOf);
  const entityNames = new Map(ENTITIES.map((e) => [e.id, e.displayName]));
  const exportJobs = createExports({
    now,
    buildMs: options.exportMs ?? 1_500,
    entities: ENTITIES,
    visitorsId: VISITORS_ID,
    documents: liveSummaries,
    categoryLabel: (categoryId) => category(categoryId)?.labels.en ?? categoryId,
    nextId: id,
  });

  function search(query: URLSearchParams) {
    tick();
    return searchDocuments(liveSummaries(), parseSearchParams(query), CATEGORIES, entityNames);
  }

  function folders(path: string[], entityId?: string) {
    tick();
    return listFolder(liveSummaries(), path, entityId);
  }

  function createReminder(body: { deadlineId?: string; documentId?: string; remindOn?: string; note?: string; conversationId?: string }): { created: boolean; result: ReminderResult } {
    if (!!body.deadlineId === !!body.documentId) throw new MockError(400, 'invalid_request', 'Exactly one of deadlineId and documentId.', 'deadlineId');
    if (!body.remindOn || !/^\d{4}-\d{2}-\d{2}$/.test(body.remindOn)) throw new MockError(400, 'invalid_request', 'remindOn is a date.', 'remindOn');
    if (body.remindOn < today()) throw new MockError(422, 'invalid_value', 'The reminder date has passed.', 'remindOn');
    const doc = body.documentId ? getDoc(body.documentId) : [...docs.values()].find((d) => deadlineIdOf(d) === body.deadlineId && !d.deleted);
    if (!doc) throw new MockError(404, 'not_found', 'Unknown target.');
    const targetId = deadlinesOf(doc)[0]?.id ?? doc.summary.id;
    const existing = [...reminders.values()].find((r) => r.targetId === targetId && r.remindOn === body.remindOn);
    const reminder = existing ?? { id: id('rem'), targetId, remindOn: body.remindOn };
    if (!existing) reminders.set(reminder.id, reminder);
    if (!existing) note(body.conversationId, 'reminder.add', `Set a reminder for "${doc.summary.title}" on ${reminder.remindOn}.`);
    return { created: !existing, result: { reminderId: reminder.id, remindOn: reminder.remindOn, created: !existing, deadline: deadlinesOf(doc)[0] ?? null } };
  }

  function allDeadlines(): Deadline[] {
    tick();
    return [...docs.values()].filter((d) => !d.deleted).flatMap(deadlinesOf);
  }

  function markDeadline(deadlineId: string, status: Deadline['status']): Deadline {
    const found = allDeadlines().find((d) => d.id === deadlineId);
    if (!found) throw new MockError(404, 'not_found', 'Unknown deadline.');
    deadlineStatus.set(deadlineId, status);
    return { ...found, status };
  }

  function cancelReminder(reminderId: string) {
    if (!reminders.delete(reminderId)) throw new MockError(404, 'not_found', 'Unknown reminder.');
  }

  const interviews = createInterviews({ now, id, docs, registerRule, fileTo, applyRule, previewRule, ruleState: (ruleId) => rules.get(ruleId)?.state, note });

  if (options.seed !== false) seed();

  function previewRule(ruleId: string): RulePreview {
    const rule = rules.get(ruleId);
    if (rule) return preview(rule);
    if (registry.ownsRule(ruleId)) return registry.emptyPreview(ruleId);
    throw new MockError(404, 'not_found', 'Unknown rule.');
  }

  const account = createAccount({ now, locked: options.locked, autoLockMinutes: options.autoLockMinutes, locale: options.locale });
  const registry = createRegistry({
    now,
    worldRules: rules,
    worldRuleCreated: ruleCreated,
    moveEntries: () => entries.map((e) => ({ ruleId: e.ruleId, action: e.action, at: e.at, actor: e.actor })),
    fileEntries: () => entries.filter((e) => e.action === 'file').map((e) => ({ actor: e.actor, at: e.at, entityId: e.after?.entityId ?? null })),
    entryCount: (since) => entries.filter((e) => Date.parse(e.at) >= since).length,
    documents: liveSummaries,
    review: (entityId) => reviewList({ entityId: entityId ?? null, limit: 200 }),
    activity: (entityId) => activity({ entityId, limit: 3 }),
    lastBatch: () => latestBatch().items[0] ?? null,
    deadlines: () => [...docs.values()].filter((d) => !d.deleted && d.summary.entityId !== VISITORS_ID).flatMap(deadlinesOf),
    showcaseDocumentId: () => [...docs.values()].find((d) => d.summary.title === 'Call for contributions, Q3 2026')?.summary.id ?? null,
  });

  return {
    now,
    tick,
    id,
    intake,
    batchDetail,
    latestBatch,
    reviewList,
    document,
    confirm,
    correct,
    likeThis,
    applyRule,
    registerRule,
    fileTo,
    note,
    consumeNotes,
    notes,
    allDeadlines,
    markDeadline,
    summaryOf: (d: Doc) => summaryOf(d),
    interviews,
    previewRule,
    entryUndo,
    groupUndo,
    activity,
    groupView,
    shell,
    entityList,
    search,
    folders,
    exports: exportJobs,
    createReminder,
    cancelReminder,
    docs,
    entries,
    batches,
    registry,
    account,
    thumbnail: (docId: string) => getDoc(docId).summary.title,
  };
}

export type World = ReturnType<typeof createWorld>;
