import createClient from 'openapi-fetch';
import type { paths } from './schema.gen';

export type { components, paths } from './schema.gen';

export const api = createClient<paths>({
  baseUrl: globalThis.location?.origin ?? '',
  fetch: (request) => globalThis.fetch(request),
});
