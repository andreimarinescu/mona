import { HttpResponse, bypass, http, type HttpHandler } from 'msw';
import { ExportError } from './exports';
import { MockError, type World } from './world';

function fail(err: unknown) {
  if (err instanceof MockError || err instanceof ExportError) return HttpResponse.json({ error: { code: err.code, message: err.message, field: err.field } }, { status: err.status });
  throw err;
}

function guard<T>(run: () => T | Promise<T>) {
  return async () => {
    try {
      return HttpResponse.json((await run()) as never);
    } catch (err) {
      return fail(err);
    }
  };
}

function thumbnailSvg(title: string): string {
  const safe = title.replace(/[<&>]/g, ' ');
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 400" width="300" height="400"><rect width="300" height="400" fill="#fff"/><text x="24" y="48" font-family="sans-serif" font-size="18" font-weight="700" fill="#222">${safe.slice(0, 28)}</text><g fill="#ddd"><rect x="24" y="88" width="252" height="8"/><rect x="24" y="112" width="220" height="8"/><rect x="24" y="136" width="240" height="8"/><rect x="24" y="160" width="180" height="8"/></g></svg>`;
}

function chatStream(): Response {
  const chunks = [
    { type: 'start', messageId: 'msg_mock', messageMetadata: { conversationId: 'cnv_mock' } },
    { type: 'start-step' },
    { type: 'text-start', id: 't1' },
    { type: 'text-delta', id: 't1', delta: 'Let us go through your questions.' },
    { type: 'text-end', id: 't1' },
    { type: 'finish-step' },
    { type: 'finish', finishReason: 'stop' },
  ];
  return new Response(chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join('') + 'data: [DONE]\n\n', {
    headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' },
  });
}

export const chatBodies: Record<string, unknown>[] = [];

export function createHandlers(world: World): HttpHandler[] {
  return [
    http.get('/api/health', () => HttpResponse.json({ status: 'ok', db: 'ok', version: '0.1.0' })),
    http.get('/api/auth/state', () =>
      HttpResponse.json({ authenticated: true, locked: false, locale: 'en', csrfToken: 'mock-csrf', autoLockMinutes: 15, profileName: 'Léa Marchand' }),
    ),
    http.get('/api/shell', guard(() => world.shell())),
    http.get('/api/settings', () =>
      HttpResponse.json({ profileName: 'Léa Marchand', locale: 'en', autoLockMinutes: 15, practiceName: 'Cabinet Marchand', filingLanguage: 'fr', confidenceHigh: 85, confidenceLow: 60, badgeHours: 24, debriefQueueThreshold: 5, debriefEarlyMin: 5 }),
    ),
    http.get('/api/entities', guard(() => world.entityList())),
    http.get('/api/categories', guard(() => world.categories())),

    http.post('/api/intake', async ({ request }) => {
      try {
        const form = await request.formData();
        const files = await Promise.all(
          form.getAll('file').map(async (f) => {
            const file = f as File;
            return { name: file.name, type: file.type, bytes: new Uint8Array(await file.arrayBuffer()) };
          }),
        );
        const result = await world.intake(files, { visitor: form.get('visitor') === 'true', title: (form.get('title') as string | null) ?? undefined });
        return HttpResponse.json(result, { status: 201 });
      } catch (err) {
        return fail(err);
      }
    }),
    http.get('/api/batches', ({ request }) => {
      const limit = Number(new URL(request.url).searchParams.get('limit') ?? 50);
      const latest = world.latestBatch();
      return HttpResponse.json({ ...latest, items: latest.items.slice(0, limit) });
    }),
    http.get('/api/batches/:id', ({ params }) => guard(() => world.batchDetail(String(params.id)))()),

    http.get('/api/review', ({ request }) => {
      const q = new URL(request.url).searchParams;
      return HttpResponse.json(world.reviewList({ reason: q.get('reason') ?? undefined, entityId: q.get('entityId'), offset: Number(q.get('offset') ?? 0), limit: Number(q.get('limit') ?? 50) }));
    }),
    http.get('/api/documents', ({ request }) => guard(() => world.search(new URL(request.url).searchParams))()),
    http.get('/api/folders', ({ request }) => {
      const q = new URL(request.url).searchParams;
      const path = (q.get('path') ?? '').split('/').filter(Boolean);
      return guard(() => world.folders(path, q.get('entityId') ?? undefined))();
    }),
    http.get('/api/documents/:id', ({ params }) => guard(() => world.document(String(params.id)))()),
    http.get('/api/documents/:id/pdf', async ({ params }) => {
      try {
        world.document(String(params.id));
      } catch (err) {
        return fail(err);
      }
      const sample = await fetch(bypass('/dev/sample.pdf'));
      return new HttpResponse(await sample.arrayBuffer(), { headers: { 'content-type': 'application/pdf', 'content-disposition': "inline; filename*=UTF-8''document.pdf" } });
    }),
    http.get('/api/documents/:id/original', async ({ params }) => {
      try {
        world.document(String(params.id));
      } catch (err) {
        return fail(err);
      }
      const sample = await fetch(bypass('/dev/sample.pdf'));
      return new HttpResponse(await sample.arrayBuffer(), { headers: { 'content-type': 'application/pdf', 'content-disposition': "attachment; filename*=UTF-8''document.pdf" } });
    }),
    http.get('/api/documents/:id/thumbnail', ({ params }) => {
      try {
        return new HttpResponse(thumbnailSvg(world.thumbnail(String(params.id))), { headers: { 'content-type': 'image/svg+xml' } });
      } catch (err) {
        return fail(err);
      }
    }),
    http.post('/api/documents/:id/confirm', ({ params }) => guard(() => world.confirm(String(params.id)))()),
    http.post('/api/documents/:id/correct', async ({ params, request }) => {
      const body = (await request.json()) as Parameters<World['correct']>[1];
      return guard(() => world.correct(String(params.id), body))();
    }),
    http.post('/api/documents/:id/like-this', ({ params }) => guard(() => world.likeThis(String(params.id)))()),
    http.get('/api/rules/:id/preview', ({ params }) => guard(() => world.previewRule(String(params.id)))()),
    http.post('/api/rules/:id/apply', ({ params }) => guard(() => world.applyRule(String(params.id)))()),

    http.get('/api/activity', ({ request }) => {
      const q = new URL(request.url).searchParams;
      return guard(() =>
        world.activity({ actor: q.get('actor') ?? undefined, entityId: q.get('entityId') ?? undefined, kind: q.get('kind') ?? undefined, q: q.get('q') ?? undefined, cursor: q.get('cursor') ?? undefined, limit: Number(q.get('limit') ?? 30) }),
      )();
    }),
    http.get('/api/journal/groups/:id', ({ params }) => guard(() => world.groupView(String(params.id)))()),
    http.post('/api/journal/groups/:id/undo', ({ params }) => guard(() => world.groupUndo(String(params.id)))()),
    http.post('/api/journal/:id/undo', ({ params }) => guard(() => world.entryUndo(Number(params.id)))()),

    http.get('/api/exports/preview', ({ request }) => {
      const q = new URL(request.url).searchParams;
      return guard(() => world.exports.preview(q.get('entityId') ?? '', Number(q.get('fiscalYear'))))();
    }),
    http.post('/api/exports', async ({ request }) => {
      const body = (await request.json()) as { entityId: string; fiscalYear: number };
      try {
        const { pack, created } = world.exports.start(body.entityId, body.fiscalYear);
        return HttpResponse.json(pack, { status: created ? 201 : 200 });
      } catch (err) {
        return fail(err);
      }
    }),
    http.get('/api/exports/:id', ({ params }) => guard(() => world.exports.get(String(params.id)))()),
    http.get('/api/exports/:id/zip', ({ params }) => {
      try {
        world.exports.get(String(params.id));
      } catch (err) {
        return fail(err);
      }
      return new HttpResponse(new Uint8Array([0x50, 0x4b, 0x05, 0x06, ...new Array(18).fill(0)]), {
        headers: { 'content-type': 'application/zip', 'content-disposition': `attachment; filename="export-${params.id}.zip"` },
      });
    }),
    http.get('/api/exports/:id/csv', ({ params }) => {
      try {
        world.exports.get(String(params.id));
      } catch (err) {
        return fail(err);
      }
      return new HttpResponse('date,counterparty,title,reference\n', { headers: { 'content-type': 'text/csv', 'content-disposition': `attachment; filename="export-${params.id}.csv"` } });
    }),

    http.post('/api/reminders', async ({ request }) => {
      const body = (await request.json()) as Parameters<World['createReminder']>[0];
      try {
        const { created, result } = world.createReminder(body);
        return HttpResponse.json(result, { status: created ? 201 : 200 });
      } catch (err) {
        return fail(err);
      }
    }),
    http.delete('/api/reminders/:id', ({ params }) => {
      try {
        world.cancelReminder(String(params.id));
        return new HttpResponse(null, { status: 204 });
      } catch (err) {
        return fail(err);
      }
    }),

    http.post('/api/chat', async ({ request }) => {
      chatBodies.push((await request.json()) as Record<string, unknown>);
      return chatStream();
    }),
  ];
}
