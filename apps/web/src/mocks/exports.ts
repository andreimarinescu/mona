import type { DocumentSummary, Entity, ExportPack, ExportPreview, TableColumnKey, TableFileFormat, TableView } from '../data/dto';

export class ExportError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly field: string | null = null,
    readonly details: Record<string, unknown> | null = null,
  ) {
    super(message);
  }
}

const COLUMN_LABELS: Partial<Record<TableColumnKey, string>> = { title: 'Title', entity: 'Entity', due_date: 'Due date', payment_iban: 'Payment IBAN', amount: 'Amount' };
const SHOWN = 50;

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
  note(conversationId: string | undefined, kind: string, text: string): void;
}

interface Spec {
  title: string;
  columns: TableColumnKey[];
  documentIds: string[];
}

export function createExports(world: ExportsWorld) {
  const jobs = new Map<string, Job>();
  const specs = new Map<string, Spec>();
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
    const pack: ExportPack = { id: world.nextId('exp'), entityId, entityName: entity.displayName, fiscalYear, status: 'building', documentCount, zipUrl: null, csvUrl: null, format: null, title: null, fileName: null, fileUrl: null, truncated: false };
    jobs.set(pack.id, { pack, readyAt: world.now() + world.buildMs, fails: control.failNext });
    control.failNext = false;
    return { pack: { ...pack }, created: true };
  }

  function table(format: 'csv' | 'xlsx' | 'docx', title: string, documentCount: number): ExportPack {
    const id = world.nextId('exp');
    const pack: ExportPack = {
      id, entityId: null, entityName: null, fiscalYear: null, status: 'ready', documentCount, zipUrl: null, csvUrl: null,
      format, title, fileName: `${title}.${format}`, fileUrl: `/api/exports/${id}/${format}`, truncated: false,
    };
    jobs.set(id, { pack, readyAt: world.now(), fails: false });
    return { ...pack };
  }

  function cellOf(d: DocumentSummary, key: TableColumnKey): string | number | null {
    if (key === 'title') return d.title;
    if (key === 'entity') return d.entityName;
    if (key === 'due_date') return d.dueDate;
    if (key === 'payment_iban') return d.paymentIban ?? null;
    if (key === 'amount') return d.amount?.value ?? null;
    return null;
  }

  /** A36: a table in the chat, kept as its spec and built from the live documents when read. */
  function inline(title: string, documentIds: string[], columns: TableColumnKey[]): TableView {
    const id = world.nextId('exp');
    const pack: ExportPack = {
      id, entityId: null, entityName: null, fiscalYear: null, status: 'ready', documentCount: documentIds.length, zipUrl: null, csvUrl: null,
      format: 'table', title, fileName: null, fileUrl: null, truncated: false,
    };
    jobs.set(id, { pack, readyAt: world.now(), fails: false });
    specs.set(id, { title, columns, documentIds });
    return tableView(id);
  }

  function tableView(id: string): TableView {
    const spec = specs.get(id);
    if (!spec) throw new ExportError(404, 'not_found', 'Not a table.');
    const live = new Map(world.documents().map((d) => [d.id, d]));
    const docs = spec.documentIds.flatMap((d) => (live.has(d) ? [live.get(d)!] : []));
    if (docs.length === 0) throw new ExportError(409, 'conflict', 'No document of this table is still visible.', null, { reason: 'empty' });
    const rows: TableView['rows'] = docs.map((d) => ({ ...Object.fromEntries(spec.columns.map((c) => [c, cellOf(d, c)])), currency: d.amount?.currency ?? null }));
    return {
      id, title: spec.title, columns: spec.columns.map((key) => ({ key, label: COLUMN_LABELS[key] ?? key })), rows: rows.slice(0, SHOWN), rowsTotal: rows.length,
      truncated: false, emptyColumns: spec.columns.filter((c) => rows.every((r) => r[c] === null || r[c] === '')), lang: 'en',
    };
  }

  function tableFile(id: string, format: TableFileFormat, conversationId: string | undefined): ExportPack {
    const view = tableView(id);
    const pack = table(format, view.title, view.rowsTotal);
    world.note(conversationId, 'table.download', `Downloaded the table "${view.title}" as ${format.toUpperCase()} (${view.rowsTotal} rows).`);
    return pack;
  }

  function get(id: string): ExportPack {
    const job = jobs.get(id);
    if (!job) throw new ExportError(404, 'not_found', 'Unknown export.');
    return view(job);
  }

  return { preview, start, table, inline, tableView, tableFile, get, control };
}
