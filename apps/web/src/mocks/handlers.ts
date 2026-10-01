import { HttpResponse, bypass, http, type HttpHandler } from 'msw';
import { ChatError, createChat, type ChatRequestBody, type MockChat } from './chat';
import { ExportError } from './exports';
import { InterviewError } from './interviews';
import { MockError } from './errors';
import type { World, WorldOptions } from './world';

function fail(err: unknown) {
  if (err instanceof MockError) return HttpResponse.json({ error: { code: err.code, message: err.message, field: err.field, details: err.details } }, { status: err.status, headers: err.headers });
  if (err instanceof ExportError) return HttpResponse.json({ error: { code: err.code, message: err.message, field: err.field } }, { status: err.status });
  if (err instanceof InterviewError) return HttpResponse.json({ error: { code: err.code, message: err.message, details: err.details } }, { status: err.status });
  if (err instanceof ChatError) return HttpResponse.json({ error: { code: err.code, message: err.message } }, { status: err.status });
  throw err;
}

async function bodyOf(request: Request): Promise<Record<string, unknown>> {
  const text = await request.text();
  return text ? (JSON.parse(text) as Record<string, unknown>) : {};
}

const conversationOf = (body: Record<string, unknown>) => (typeof body.conversationId === 'string' ? body.conversationId : undefined);

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

export const chatBodies: Record<string, unknown>[] = [];

export function createHandlers(world: World, options: Pick<WorldOptions, 'chatDelayMs' | 'draftMs'> = {}, chat: MockChat = createChat(world, { chunkDelayMs: options.chatDelayMs, draftMs: options.draftMs })): HttpHandler[] {
  return [
    http.all('/api/*', ({ request }) => {
      const path = new URL(request.url).pathname;
      const err = world.account.gate(request.method, path);
      if (err) return fail(err);
      const write = request.method !== 'GET' && request.method !== 'HEAD' && path !== '/api/auth/unlock';
      if (write && request.headers.get('x-csrf-token') !== world.account.view().csrfToken) return fail(new MockError(403, 'csrf_failed', 'Missing or invalid CSRF token.'));
      return undefined;
    }),
    http.get('/api/health', () => HttpResponse.json({ status: 'ok', db: 'ok', version: '0.1.0' })),
    http.get('/api/auth/state', () => HttpResponse.json(world.account.view())),
    http.post('/api/auth/unlock', async ({ request }) => {
      const body = (await request.json()) as { password?: string };
      return guard(() => world.account.unlock(String(body.password ?? '')))();
    }),
    http.post('/api/auth/lock', () => {
      world.account.lock();
      return new HttpResponse(null, { status: 204 });
    }),
    http.post('/api/auth/heartbeat', () => {
      try {
        world.account.heartbeat();
        return new HttpResponse(null, { status: 204 });
      } catch (err) {
        return fail(err);
      }
    }),
    http.post('/api/auth/logout', () => new HttpResponse(null, { status: 204 })),
    http.put('/api/auth/password', async ({ request }) => {
      const body = (await request.json()) as { currentPassword: string; newPassword: string };
      try {
        world.account.changePassword(body.currentPassword, body.newPassword);
        return new HttpResponse(null, { status: 204 });
      } catch (err) {
        return fail(err);
      }
    }),
    http.get('/api/shell', guard(() => world.shell())),
    http.get('/api/settings', () => HttpResponse.json(world.account.settings())),
    http.patch('/api/settings', async ({ request }) => {
      const body = (await request.json()) as Parameters<World['account']['patch']>[0];
      return guard(() => world.account.patch(body))();
    }),
    http.get('/api/system/status', () => HttpResponse.json(world.account.systemStatus())),
    http.get('/api/home', ({ request }) => guard(() => world.registry.home(new URL(request.url).searchParams))()),
    http.get('/api/entities', guard(() => world.entityList())),
    http.get('/api/entities/:id', ({ params }) => guard(() => world.registry.entityDetail(String(params.id)))()),
    http.get('/api/people', guard(() => world.registry.people())),
    http.get('/api/categories', guard(() => world.registry.categoryList())),
    http.patch('/api/categories/:id', async ({ params, request }) => {
      const body = (await request.json()) as Parameters<World['registry']['patchCategory']>[1];
      return guard(() => world.registry.patchCategory(String(params.id), body))();
    }),
    http.post('/api/templates/preview', async ({ request }) => {
      const body = (await request.json()) as Parameters<World['registry']['previewTemplate']>[0];
      return guard(() => world.registry.previewTemplate(body))();
    }),
    http.get('/api/rules', ({ request }) => guard(() => world.registry.listRules(new URL(request.url).searchParams))()),
    http.get('/api/rules/learned', ({ request }) => guard(() => world.registry.learned(new URL(request.url).searchParams.get('since')))()),
    http.get('/api/rules/:id', ({ params }) => guard(() => world.registry.rule(String(params.id)))()),
    http.patch('/api/rules/:id', async ({ params, request }) => {
      const body = (await request.json()) as Parameters<World['registry']['patchRule']>[1];
      return guard(() => world.registry.patchRule(String(params.id), body))();
    }),

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
    http.post('/api/rules/:id/apply', async ({ params, request }) => {
      const body = await bodyOf(request);
      return guard(() => world.applyRule(String(params.id), conversationOf(body)))();
    }),

    http.get('/api/activity', ({ request }) => {
      const q = new URL(request.url).searchParams;
      return guard(() =>
        world.activity({ actor: q.get('actor') ?? undefined, entityId: q.get('entityId') ?? undefined, kind: q.get('kind') ?? undefined, q: q.get('q') ?? undefined, cursor: q.get('cursor') ?? undefined, limit: Number(q.get('limit') ?? 30) }),
      )();
    }),
    http.get('/api/journal/groups/:id', ({ params }) => guard(() => world.groupView(String(params.id)))()),
    http.post('/api/journal/groups/:id/undo', async ({ params, request }) => {
      const body = await bodyOf(request);
      return guard(() => world.groupUndo(String(params.id), conversationOf(body)))();
    }),
    http.post('/api/journal/:id/undo', async ({ params, request }) => {
      const body = await bodyOf(request);
      return guard(() => world.entryUndo(Number(params.id), conversationOf(body)))();
    }),

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

    http.patch('/api/deadlines/:id', async ({ params, request }) => {
      const body = (await bodyOf(request)) as { status: 'open' | 'done' | 'dismissed' };
      return guard(() => world.markDeadline(String(params.id), body.status))();
    }),

    http.get('/api/interviews/:id', ({ params }) => guard(() => world.interviews.get(String(params.id)))()),
    http.post('/api/interviews/:id/questions/:qid/answer', async ({ params, request }) => {
      const body = (await bodyOf(request)) as { optionId?: string; freeText?: string; conversationId?: string };
      return guard(() => world.interviews.answer(String(params.id), String(params.qid), body))();
    }),
    http.post('/api/interviews/:id/questions/:qid/skip', async ({ params, request }) => {
      const body = await bodyOf(request);
      return guard(() => world.interviews.skip(String(params.id), String(params.qid), conversationOf(body)))();
    }),
    http.post('/api/interviews/:id/questions/:qid/apply', async ({ params, request }) => {
      const body = await bodyOf(request);
      return guard(() => world.interviews.applyAll(String(params.id), String(params.qid), conversationOf(body)))();
    }),

    http.get('/api/drafts/:id', ({ params }) => guard(() => chat.draft(String(params.id)))()),
    http.get('/api/drafts/:id/docx', ({ params, request }) => {
      try {
        const { bytes, name } = chat.docx(String(params.id), new URL(request.url).searchParams.get('conversationId') ?? undefined);
        return new HttpResponse(bytes, {
          headers: { 'content-type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'content-disposition': `attachment; filename*=UTF-8''${encodeURIComponent(name)}` },
        });
      } catch (err) {
        return fail(err);
      }
    }),

    http.get('/api/conversations', ({ request }) => {
      const q = new URL(request.url).searchParams;
      return HttpResponse.json(chat.list(q.get('q') ?? '', q.get('cursor'), Number(q.get('limit') ?? 30)));
    }),
    http.get('/api/conversations/:id/messages', ({ params }) => guard(() => chat.messages(String(params.id)))()),
    http.post('/api/chat', async ({ request }) => {
      const body = (await request.json()) as ChatRequestBody;
      chatBodies.push(body as unknown as Record<string, unknown>);
      try {
        return chat.stream(body, request.signal);
      } catch (err) {
        return fail(err);
      }
    }),
  ];
}
