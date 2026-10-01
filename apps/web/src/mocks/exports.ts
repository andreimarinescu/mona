import type { DocumentSummary, Entity, ExportPack, ExportPreview } from '../data/dto';

export class ExportError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly field: string | null = null,
  ) {
    super(message);
  }
}

interface Job {
  pack: ExportPack;
  readyAt: number;
  fails: boolean;
}

export interface ExportsWorld {
  now(): number;
  buildMs: number;
  entities: Entity[];
  visitorsId: string;
  documents(): DocumentSummary[];
  categoryLabel(id: string): string;
  nextId(prefix: string): string;
}

export function createExports(world: ExportsWorld) {
  const jobs = new Map<string, Job>();
  const control = { failNext: false };

  function exportable(entityId: string): Entity {
    const entity = world.entities.find((e) => e.id === entityId);
    if (!entity) throw new ExportError(404, 'not_found', 'Unknown entity.');
    if (entity.visibility === 'personal' || entity.id === world.visitorsId) throw new ExportError(403, 'not_allowed', 'This entity is never exported.');
    return entity;
  }

  const inYear = (d: DocumentSummary, entityId: string, fiscalYear: number) => d.entityId === entityId && d.fiscalYear === fiscalYear;

  function preview(entityId: string, fiscalYear: number): ExportPreview {
    exportable(entityId);
    const docs = world.documents();
    const filed = docs.filter((d) => d.status === 'filed' && inYear(d, entityId, fiscalYear));
    const counts = new Map<string, number>();
    for (const d of filed) if (d.categoryId) counts.set(d.categoryId, (counts.get(d.categoryId) ?? 0) + 1);
    const years = new Set(docs.filter((d) => d.status === 'filed' && d.entityId === entityId && d.fiscalYear !== null).map((d) => d.fiscalYear!));
    return {
      entityId,
      fiscalYear,
      documentCount: filed.length,
      inReview: docs.filter((d) => (d.status === 'review' || d.status === 'unreadable') && inYear(d, entityId, fiscalYear)).length,
      categories: [...counts].map(([id, count]) => ({ id, label: world.categoryLabel(id), count })).sort((a, b) => b.count - a.count),
      fiscalYears: [...years].sort((a, b) => b - a),
    };
  }

  function view(job: Job): ExportPack {
    if (job.pack.status !== 'building' || world.now() < job.readyAt) return { ...job.pack };
    if (job.fails) job.pack = { ...job.pack, status: 'failed' };
    else job.pack = { ...job.pack, status: 'ready', zipUrl: `/api/exports/${job.pack.id}/zip`, csvUrl: `/api/exports/${job.pack.id}/csv` };
    return { ...job.pack };
  }

  function start(entityId: string, fiscalYear: number): { pack: ExportPack; created: boolean } {
    const entity = exportable(entityId);
    const running = [...jobs.values()].find((j) => view(j).status === 'building' && j.pack.entityId === entityId && j.pack.fiscalYear === fiscalYear);
    if (running) return { pack: view(running), created: false };
    const { documentCount } = preview(entityId, fiscalYear);
    const pack: ExportPack = { id: world.nextId('exp'), entityId, entityName: entity.displayName, fiscalYear, status: 'building', documentCount, zipUrl: null, csvUrl: null };
    jobs.set(pack.id, { pack, readyAt: world.now() + world.buildMs, fails: control.failNext });
    control.failNext = false;
    return { pack: { ...pack }, created: true };
  }

  function get(id: string): ExportPack {
    const job = jobs.get(id);
    if (!job) throw new ExportError(404, 'not_found', 'Unknown export.');
    return view(job);
  }

  return { preview, start, get, control };
}
