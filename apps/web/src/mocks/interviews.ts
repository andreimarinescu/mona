import type { AnswerResult, ApplyResult, DocumentSummary, Evidence, Interview, InterviewQuestion, Rule, RulePreview } from '../data/dto';
import { CABINET, PERSONAL, PRIVATE_INSURER } from './seed';

export class InterviewError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: Record<string, unknown> | null = null,
  ) {
    super(message);
  }
}

interface MockDoc {
  summary: DocumentSummary;
  deleted: boolean;
}

interface Branch {
  label: string;
  condition: string;
  entityId: string;
  categoryId: string;
  subcategoryKey: string | null;
  path: (year: number) => string[];
  docIds: (affects: string[]) => string[];
}

export interface InterviewDeps {
  now(): number;
  id(prefix: string): string;
  docs: Map<string, MockDoc>;
  registerRule(rule: Rule, target: { candidates(): MockDoc[]; stays(): string[]; place(d: MockDoc, groupId: string): void }): void;
  fileTo(d: MockDoc, to: { entityId: string; categoryId: string; subcategoryKey: string | null; path: string[] }, groupId: string, ruleId: string): void;
  applyRule(ruleId: string, conversationId?: string): ApplyResult;
  previewRule(ruleId: string): RulePreview;
  ruleState(ruleId: string): Rule['state'] | undefined;
  note(conversationId: string | undefined, kind: string, text: string): void;
}

const QUOTES = ['contrat retraite Madelin n° 4418, cotisation annuelle', 'garantie décès et capital vie, adhérent principal', 'avis d’échéance, prélèvement trimestriel'];

/** The mock debrief: two questions about a batch's review documents; answer 1 of the first drafts two branch rules. */
export function createInterviews(deps: InterviewDeps) {
  const interviews = new Map<string, Interview>();
  const branches = new Map<string, Branch[]>();
  const byBatch = new Map<string, string>();

  const year = () => new Date(deps.now()).getFullYear();
  const insurance = (label: string | null) => (y: number) => [PERSONAL.folderName, `${y} ${PERSONAL.folderName}`, 'Assurances', ...(label ? [label] : [])];

  function evidence(docIds: string[]): Evidence[] {
    return docIds.slice(0, 3).map((docId, i) => {
      const d = deps.docs.get(docId)!;
      return { documentId: docId, documentTitle: d.summary.fileName, field: null, page: 1, quote: QUOTES[i % QUOTES.length]!, verified: true, findQuery: i === 2 ? null : QUOTES[i % QUOTES.length]!.split(' ').slice(0, 2).join(' ') };
    });
  }

  function view(iv: Interview): Interview {
    const questions = iv.questions.map((q) => {
      const affects = q.affects.filter((d) => !deps.docs.get(d)?.deleted);
      return { ...q, affects, affectsCount: affects.length, evidence: q.evidence.map((e) => ({ ...e, documentTitle: deps.docs.get(e.documentId)?.summary.fileName ?? e.documentTitle })) };
    });
    return { ...iv, questions, openQuestions: questions.filter((q) => q.status === 'open').length };
  }

  function debrief(batchId: string, reviewDocIds: string[]): Interview {
    const existing = byBatch.get(batchId);
    if (existing) return view(interviews.get(existing)!);
    const ivId = deps.id('int');
    const at = new Date(deps.now()).toISOString();
    const q1: InterviewQuestion = {
      id: deps.id('qst'),
      ordinal: 1,
      question: `I found ${reviewDocIds.length} letters from ${PRIVATE_INSURER} in this batch. Are they personal, or for the practice? I’ll remember your answer for the next ones.`,
      lang: 'en',
      affects: reviewDocIds,
      affectsCount: reviewDocIds.length,
      evidence: evidence(reviewDocIds),
      options: [
        { id: 'o1', label: 'Personal: split retirement and life insurance', suggested: true, ruleDraft: { kind: 'depends', discriminator: 'text', branches: [] } },
        { id: 'o2', label: 'For the practice', ruleDraft: { kind: 'always', discriminator: null, branches: [] } },
        { id: 'o3', label: 'Ask me each time', ruleDraft: { kind: 'ask', discriminator: null, branches: [] } },
      ],
      suggestionConfidence: 72,
      status: 'open',
      answer: null,
    };
    const last = reviewDocIds.slice(-1);
    const q2: InterviewQuestion = {
      id: deps.id('qst'),
      ordinal: 2,
      question: 'This reminder is addressed to the practice. Should letters like it always go to the practice?',
      lang: 'en',
      affects: last,
      affectsCount: last.length,
      evidence: evidence(last),
      options: [
        { id: 'o1', label: 'Yes, always the practice', suggested: true, ruleDraft: { kind: 'always', discriminator: null, branches: [] } },
        { id: 'o2', label: 'No, it’s personal', ruleDraft: { kind: 'always', discriminator: null, branches: [] } },
        { id: 'o3', label: 'Ask me each time', ruleDraft: { kind: 'ask', discriminator: null, branches: [] } },
      ],
      suggestionConfidence: 81,
      status: 'open',
      answer: null,
    };
    const even = (affects: string[]) => affects.filter((_, i) => i % 2 === 0);
    const odd = (affects: string[]) => affects.filter((_, i) => i % 2 === 1);
    const all = (affects: string[]) => affects;
    branches.set(`${q1.id}:o1`, [
      { label: 'retirement', condition: 'the text mentions a retirement contract', entityId: PERSONAL.id, categoryId: 'insurance', subcategoryKey: 'retirement', path: insurance('Retraite'), docIds: even },
      { label: 'life insurance', condition: 'the text mentions life insurance', entityId: PERSONAL.id, categoryId: 'insurance', subcategoryKey: 'life', path: insurance('Assurance vie'), docIds: odd },
    ]);
    branches.set(`${q1.id}:o2`, [{ label: 'practice', condition: 'always', entityId: CABINET.id, categoryId: 'insurance', subcategoryKey: null, path: (y) => [CABINET.folderName, `${y} ${CABINET.folderName}`, 'Assurances'], docIds: all }]);
    branches.set(`${q2.id}:o1`, [{ label: 'practice', condition: 'always', entityId: CABINET.id, categoryId: 'insurance', subcategoryKey: null, path: (y) => [CABINET.folderName, `${y} ${CABINET.folderName}`, 'Assurances'], docIds: all }]);
    branches.set(`${q2.id}:o2`, [{ label: 'personal', condition: 'always', entityId: PERSONAL.id, categoryId: 'insurance', subcategoryKey: null, path: insurance(null), docIds: all }]);
    const iv: Interview = {
      id: ivId,
      kind: 'debrief',
      status: 'ready',
      questions: [q1, q2],
      batchId,
      createdAt: at,
      lang: 'en',
      scope: { type: 'batch', batchId },
      openQuestions: 2,
      readyAt: at,
      finishedAt: null,
      error: null,
      source: 'live',
    };
    interviews.set(ivId, iv);
    byBatch.set(batchId, ivId);
    return view(iv);
  }

  function find(interviewId: string, questionId?: string) {
    const iv = interviews.get(interviewId);
    if (!iv) throw new InterviewError(404, 'not_found', 'Unknown interview.');
    if (questionId === undefined) return { iv, q: undefined };
    const q = iv.questions.find((x) => x.id === questionId);
    if (!q) throw new InterviewError(404, 'not_found', 'Unknown question.');
    return { iv, q };
  }

  function settle(iv: Interview) {
    if (iv.questions.every((q) => q.status !== 'open')) {
      iv.status = 'done';
      iv.finishedAt = new Date(deps.now()).toISOString();
    }
  }

  function result(iv: Interview, q: InterviewQuestion): AnswerResult {
    const ruleIds = q.answer?.ruleIds ?? [];
    const previews = ruleIds.filter((r) => deps.ruleState(r) !== undefined).map((r) => deps.previewRule(r));
    const option = q.options.find((o) => o.id === q.answer?.optionId);
    return {
      question: view(iv).questions.find((x) => x.id === q.id)!,
      rules: previews.map((p) => p.rule),
      previews: option?.ruleDraft?.kind === 'ask' ? [] : previews,
      interviewStatus: iv.status,
    };
  }

  function answer(interviewId: string, questionId: string, body: { optionId?: string; freeText?: string; conversationId?: string }): AnswerResult {
    const { iv, q } = find(interviewId, questionId);
    if (q!.answer && q!.answer.optionId === (body.optionId ?? null) && q!.answer.freeText === (body.freeText ?? null)) return result(iv, q!);
    if (q!.status === 'answered') throw new InterviewError(409, 'already_answered', 'Already answered.', { answer: { optionId: q!.answer!.optionId, freeText: q!.answer!.freeText } });
    if (q!.status === 'skipped' || iv.status === 'generating' || iv.status === 'failed' || iv.status === 'cancelled') throw new InterviewError(409, 'conflict', 'Not answerable.', { reason: 'interview_not_ready' });
    const option = body.optionId ? q!.options.find((o) => o.id === body.optionId) : undefined;
    if (body.optionId && !option) throw new InterviewError(422, 'invalid_value', 'Unknown option.');
    const ruleIds: string[] = [];
    if (option && option.ruleDraft?.kind !== 'ask') {
      for (const b of branches.get(`${q!.id}:${option.id}`) ?? []) {
        const docIds = b.docIds(q!.affects);
        const rule: Rule = {
          id: deps.id('rul'),
          name: `${PRIVATE_INSURER} · ${option.label}${branches.get(`${q!.id}:${option.id}`)!.length > 1 ? ` (${b.label})` : ''}`,
          condition: `Counterparty is ${PRIVATE_INSURER} and ${b.condition}`,
          destination: b.path(year()),
          enabled: false,
          state: 'draft',
          source: 'interview',
          version: 1,
          priority: 100,
          firedCount: 0,
          correctionsSince: 0,
        };
        const pending = () => docIds.map((d) => deps.docs.get(d)!).filter((d) => d && !d.deleted && d.summary.path.join('/') !== rule.destination.join('/'));
        deps.registerRule(rule, {
          candidates: pending,
          stays: () => [],
          place: (d, groupId) => deps.fileTo(d, { entityId: b.entityId, categoryId: b.categoryId, subcategoryKey: b.subcategoryKey, path: rule.destination }, groupId, rule.id),
        });
        ruleIds.push(rule.id);
      }
    }
    q!.status = 'answered';
    q!.answer = { optionId: option?.id ?? null, freeText: body.freeText ?? null, ruleIds };
    settle(iv);
    const out = result(iv, q!);
    const drafted = out.rules.length > 0 ? ` ${out.rules.length} rule(s) drafted: ${out.rules.map((r) => `"${r.name}"`).join(', ')}` : '';
    deps.note(
      body.conversationId,
      option ? 'interview.answer' : 'interview.answer_text',
      option ? `Answered interview question "${q!.question.slice(0, 80)}" with "${option.label}".${drafted}` : `Answered interview question "${q!.question.slice(0, 80)}" in their own words: "${(body.freeText ?? '').slice(0, 80)}". No rule was drafted.`,
    );
    return out;
  }

  function skip(interviewId: string, questionId: string, conversationId?: string): InterviewQuestion {
    const { iv, q } = find(interviewId, questionId);
    if (q!.status === 'answered') throw new InterviewError(409, 'conflict', 'Answered.', { reason: 'answered' });
    q!.status = 'skipped';
    settle(iv);
    deps.note(conversationId, 'interview.skip', `Skipped interview question "${q!.question.slice(0, 80)}".`);
    return view(iv).questions.find((x) => x.id === q!.id)!;
  }

  function applyAll(interviewId: string, questionId: string, conversationId?: string): { results: ApplyResult[] } {
    const { q } = find(interviewId, questionId);
    const live = (q!.answer?.ruleIds ?? []).filter((r) => {
      const state = deps.ruleState(r);
      return state === 'draft' || state === 'active';
    });
    if (q!.status !== 'answered' || live.length === 0) throw new InterviewError(409, 'conflict', 'Nothing to apply.', { reason: 'nothing_to_apply' });
    return { results: live.map((r) => deps.applyRule(r, conversationId)) };
  }

  return {
    debrief,
    get: (interviewId: string) => view(find(interviewId).iv),
    forBatch: (batchId: string) => {
      const ivId = byBatch.get(batchId);
      return ivId ? view(interviews.get(ivId)!) : null;
    },
    answer,
    skip,
    applyAll,
  };
}
