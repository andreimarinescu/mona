import type { ActivityPage, BatchSummary, BriefFacts, CategoryDto, CategoryList, CategoryPatch, Deadline, DocumentSummary, EntityDetail, HomeView, LearnedItem, Page, Rule, RuleListItem, RulePatch, RulePreview } from '../data/dto';
import { addDays, toIsoDate } from '../data/calendar';
import { parseTemplate } from '../data/template';
import { MockError } from './errors';
import { makeId } from './ids';
import { norm } from './archive';
import { CATEGORIES, ENTITIES, INGESTION_HISTORY, OVERNIGHT, PEOPLE, RULES_SEED, VISITORS_ID } from './seed';
import { MESSAGES, renderTemplates, type SampleValues } from './template';

export interface RegistryDeps {
  now(): number;
  worldRules: Map<string, Rule>;
  worldRuleCreated: Map<string, number>;
  moveEntries(): { ruleId: string | null; action: string; at: string; actor: string }[];
  fileEntries(): { actor: string; at: string; entityId: string | null }[];
  entryCount(sinceMs: number): number;
  documents(): DocumentSummary[];
  review(entityId?: string): { total: number; items: DocumentSummary[] };
  activity(entityId?: string): ActivityPage;
  lastBatch(): BatchSummary | null;
  deadlines(): Deadline[];
  showcaseDocumentId(): string | null;
}

const HOUR = 3_600_000;
const STATE_ORDER = { active: 0, draft: 1, disabled: 2 } as const;

function startOfDay(ms: number): number {
  const d = new Date(ms);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

export function createRegistry(deps: RegistryDeps) {
  const { now } = deps;
  const categories: CategoryDto[] = structuredClone(CATEGORIES);
  const seeded = new Map<string, Rule>();
  const seededCreated = new Map<string, number>();

  for (const r of RULES_SEED) {
    const rule: Rule = {
      id: makeId('rul', r.n),
      name: r.name,
      condition: r.condition,
      destination: r.destination,
      enabled: r.state === 'active',
      state: r.state,
      source: r.source,
      version: 1,
      priority: r.state === 'active' ? 50 : 10,
      firedCount: r.firedCount,
      correctionsSince: r.correctionsSince,
    };
    if (r.lastFiredHoursAgo !== null) rule.lastFiredAt = new Date(now() - r.lastFiredHoursAgo * HOUR).toISOString();
    seeded.set(rule.id, rule);
    const created = now() - r.createdHoursAgo * HOUR;
    seededCreated.set(rule.id, r.createdHoursAgo <= 6 ? Math.max(created, startOfDay(now()) + 60_000) : created);
  }

  const allRules = () => [...seeded.values(), ...deps.worldRules.values()];
  const createdAt = (id: string) => seededCreated.get(id) ?? deps.worldRuleCreated.get(id) ?? now();
  const findRule = (id: string) => {
    const rule = seeded.get(id) ?? deps.worldRules.get(id);
    if (!rule) throw new MockError(404, 'not_found', 'Unknown rule.');
    return rule;
  };
  const item = (rule: Rule): RuleListItem => ({ rule: { ...rule }, valid: true, problems: [] });

  function listRules(q: URLSearchParams): Page<RuleListItem> {
    const needle = norm(q.get('q') ?? '');
    const offset = Number(q.get('offset') ?? 0);
    const limit = Number(q.get('limit') ?? 50);
    const items = allRules()
      .filter((r) => (!q.get('state') || r.state === q.get('state')) && (!q.get('source') || r.source === q.get('source')) && (!needle || norm(r.name).includes(needle)))
      .sort((a, b) => STATE_ORDER[a.state] - STATE_ORDER[b.state] || b.priority - a.priority || b.firedCount - a.firedCount)
      .map(item);
    return { items: items.slice(offset, offset + limit), total: items.length, offset, limit };
  }

  function patchRule(id: string, body: RulePatch): RuleListItem {
    const rule = findRule(id);
    if (body.name !== undefined && (typeof body.name !== 'string' || body.name.trim().length < 1 || body.name.length > 120)) {
      throw new MockError(422, 'invalid_rule', 'The name is 1 to 120 characters.', 'name', { message: 'The name is 1 to 120 characters.' });
    }
    if (body.priority !== undefined && !Number.isInteger(body.priority)) throw new MockError(422, 'invalid_rule', 'The priority is a whole number.', 'priority', { message: 'The priority is a whole number.' });
    if (body.name !== undefined) rule.name = body.name.trim();
    if (body.priority !== undefined) rule.priority = body.priority;
    if (body.enabled !== undefined) {
      rule.enabled = body.enabled;
      rule.state = body.enabled ? 'active' : 'disabled';
    }
    return item(rule);
  }

  function learned(sinceIso: string | null): LearnedItem[] {
    const since = sinceIso ? Date.parse(sinceIso) : now() - 7 * 24 * HOUR;
    const moves = deps.moveEntries();
    return allRules()
      .filter((r) => (r.source === 'interview' || r.source === 'correction') && createdAt(r.id) >= since)
      .sort((a, b) => createdAt(b.id) - createdAt(a.id))
      .map((rule) => ({ rule: { ...rule }, createdAt: new Date(createdAt(rule.id)).toISOString(), moved: moves.filter((e) => e.ruleId === rule.id && e.action === 'move').length + (seeded.has(rule.id) ? rule.firedCount : 0) }));
  }

  const emptyPreview = (rule: Rule): RulePreview => ({ rule: { ...rule }, moves: [], movesTotal: 0, stays: [], staysTotal: 0, applied: false, groupId: null });

  function categoryList(): CategoryList {
    const counts: Record<string, number> = {};
    for (const d of deps.documents()) if (d.categoryId) counts[d.categoryId] = (counts[d.categoryId] ?? 0) + 1;
    return { items: structuredClone(categories), documentCounts: counts };
  }

  function patchCategory(id: string, body: CategoryPatch): CategoryDto {
    const category = categories.find((c) => c.id === id);
    if (!category) throw new MockError(404, 'not_found', 'Unknown category.');
    if (body.template) {
      for (const [kind, key] of [['path', 'pathTemplate'], ['file', 'fileTemplate']] as const) {
        const parsed = parseTemplate(body.template[key], kind);
        if (parsed.error) throw new MockError(422, 'invalid_template', 'The template is not valid.', `template.${key}`, { template: kind, offset: parsed.error.offset, message: MESSAGES[parsed.error.reason] });
      }
    }
    if (body.labels) {
      for (const lang of ['en', 'fr', 'ro'] as const) {
        const label = body.labels[lang];
        if (typeof label !== 'string' || label.trim() === '') throw new MockError(422, 'invalid_value', 'Every language needs a label.', `labels.${lang}`);
      }
      category.labels = { ...body.labels };
    }
    if (body.template) category.template = { ...body.template };
    return structuredClone(category);
  }

  function previewTemplate(body: { pathTemplate: string; fileTemplate: string; entityId?: string }) {
    const entity = ENTITIES.find((e) => e.id === body.entityId) ?? ENTITIES[0]!;
    const sample: SampleValues = {
      entity: entity.folderName,
      fyEnd: entity.fiscalYearEnd,
      category: 'Appels de paiement',
      sub: 'Contribution annuelle',
      counterparty: 'Example Supplier',
      issuer: null,
      reference: '2025-A-118',
      docDate: '2026-02-27',
      periodEnd: '2025-12-31',
    };
    return renderTemplates(String(body.pathTemplate ?? ''), String(body.fileTemplate ?? ''), sample);
  }

  function entityDetail(id: string): EntityDetail {
    const entity = ENTITIES.find((e) => e.id === id);
    if (!entity) throw new MockError(404, 'not_found', 'Unknown entity.');
    return { ...entity, aliases: [], addresses: [], purgeAfterHours: id === VISITORS_ID ? 24 : null, sortOrder: ENTITIES.indexOf(entity) };
  }

  function home(q: URLSearchParams): HomeView {
    const t = now();
    const entityId = q.get('entityId') ?? undefined;
    const sinceMs = q.get('since') ? Date.parse(q.get('since')!) : startOfDay(t);
    const defaultWindow = !q.get('since');
    const filedEntries = deps.fileEntries().filter((e) => e.actor === 'mona' && Date.parse(e.at) >= sinceMs && (!entityId || e.entityId === entityId));
    const byEntity = new Map<string, number>();
    for (const e of filedEntries) if (e.entityId) byEntity.set(e.entityId, (byEntity.get(e.entityId) ?? 0) + 1);
    if (defaultWindow) {
      const [cabinet, atelier] = ENTITIES;
      if (cabinet && (!entityId || entityId === cabinet.id)) byEntity.set(cabinet.id, (byEntity.get(cabinet.id) ?? 0) + OVERNIGHT.cabinet);
      if (atelier && (!entityId || entityId === atelier.id)) byEntity.set(atelier.id, (byEntity.get(atelier.id) ?? 0) + OVERNIGHT.atelier);
    }
    const names = new Map(ENTITIES.map((e) => [e.id, e.displayName]));
    const filedCount = [...byEntity.values()].reduce((a, b) => a + b, 0);

    const review = deps.review(entityId);
    const byReason: Partial<Record<'low' | 'entity' | 'conflict' | 'unreadable', number>> = {};
    for (const d of review.items) for (const r of d.reasons) byReason[r] = (byReason[r] ?? 0) + 1;

    const day = (offset: number) => toIsoDate(new Date(t + offset * 24 * HOUR));
    const showcase = deps.showcaseDocumentId();
    const synthetic = (n: number, label: string, days: number, cents: number, entity: number, documentId: string | null): Deadline => {
      const entityRef = ENTITIES[entity]!;
      return {
        id: makeId('ddl', 800 + n),
        documentId,
        label,
        entityId: entityRef.id,
        entityName: entityRef.displayName,
        dueDate: day(days),
        amount: { value: cents / 100, currency: 'EUR' },
        status: 'open',
        daysLeft: days,
        reminder: null,
      };
    };
    const open = [
      ...deps.deadlines().filter((d) => d.status === 'open'),
      synthetic(1, 'URSSAF, quarterly contributions', 2, 128_400, 0, showcase),
      synthetic(2, 'Mutuelle Horizon, instalment', 5, 31_840, 3, null),
      synthetic(3, 'SIE Laval, VAT return', 19, 214_600, 2, null),
    ]
      .filter((d) => !entityId || d.entityId === entityId)
      .sort((a, b) => a.daysLeft - b.daysLeft);
    const dueSoon = open.filter((d) => d.daysLeft <= 7).slice(0, 5);

    const today = day(0);
    const arrivals = new Map<string, number>();
    for (const d of deps.documents()) {
      const date = toIsoDate(new Date(d.arrivedAt));
      arrivals.set(date, (arrivals.get(date) ?? 0) + 1);
    }
    const days = Array.from({ length: 14 }, (_, i) => {
      const date = i === 13 ? today : addDays(today, i - 13);
      return { date, count: i === 13 ? (arrivals.get(today) ?? 0) : (INGESTION_HISTORY[i] ?? 0) + (arrivals.get(date) ?? 0) };
    });

    const batch = deps.lastBatch();
    const pending = batch?.debrief && batch.debrief.openQuestions > 0 && batch.debrief.status === 'ready' ? { interviewId: batch.debrief.interviewId, openQuestions: batch.debrief.openQuestions } : null;
    const facts: BriefFacts = {
      generatedAt: new Date(t).toISOString(),
      since: new Date(sinceMs).toISOString(),
      filed: { count: filedCount, byEntity: [...byEntity].map(([id, count]) => ({ entityId: id, name: names.get(id) ?? id, count })) },
      needsReview: { count: review.total, byReason },
      dueSoon,
      remindersToday: [],
      learned: learned(new Date(sinceMs).toISOString()).map((l) => ({ ruleId: l.rule.id, name: l.rule.name, createdAt: l.createdAt, firedSince: l.rule.firedCount })),
      pendingInterview: pending,
    };
    const activity = deps.activity(entityId);
    return {
      facts,
      journalEntryCount: deps.entryCount(sinceMs) + (defaultWindow ? OVERNIGHT.entries : 0),
      review: { total: review.total, items: review.items.slice(0, 3) },
      due: { total: open.length, items: open.slice(0, 3) },
      activity: { items: activity.items.slice(0, 3), documents: activity.documents, rules: activity.rules },
      ingestion: { days, lastBatch: batch },
    };
  }

  return { listRules, rule: (id: string) => item(findRule(id)), patchRule, learned, ownsRule: (id: string) => seeded.has(id), emptyPreview: (id: string) => emptyPreview(findRule(id)), categoryList, patchCategory, previewTemplate, entityDetail, people: () => ({ items: structuredClone(PEOPLE) }), home };
}

export type Registry = ReturnType<typeof createRegistry>;
