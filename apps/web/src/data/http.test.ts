import { describe, expect, it } from 'vitest';
import { useMockApi } from '../test/mockApi';
import { ApiError, get, post, withQuery } from './http';

describe('withQuery', () => {
  it('skips empty values and repeats arrays', () => {
    expect(withQuery('/api/x', { a: 1, b: undefined, c: '', d: null, e: ['x', 'y'], f: false })).toBe('/api/x?a=1&e=x&e=y&f=false');
    expect(withQuery('/api/x')).toBe('/api/x');
  });
});

describe('request', () => {
  const api = useMockApi();

  it('turns the C2 error envelope into an ApiError', async () => {
    const err = await get('/api/documents/doc_00000000000000000000009999').catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: 'not_found' });
  });

  it('keeps the offending field of a domain refusal', async () => {
    const world = api.world();
    const img = world.reviewList({}).items.find((d) => d.title === 'IMG_2231.jpg')!;
    world.correct(img.id, { entityId: world.entityList().items[0]!.id, categoryId: 'tax' });
    const err = await post(`/api/documents/${img.id}/like-this`).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 422, code: 'invalid_value', field: 'counterparty' });
  });

  it('sends the session CSRF token on writes and on no read', async () => {
    const headers: Record<string, string | null> = {};
    api.server.events.on('request:start', ({ request }) => {
      headers[`${request.method} ${new URL(request.url).pathname}`] = request.headers.get('x-csrf-token');
    });
    const doc = api.world().reviewList({}).items[0]!;
    await get('/api/review');
    await post(`/api/documents/${doc.id}/confirm`);
    api.server.events.removeAllListeners();
    expect(headers['GET /api/review']).toBeNull();
    expect(headers[`POST /api/documents/${doc.id}/confirm`]).toBe('mock-csrf');
  });
});
