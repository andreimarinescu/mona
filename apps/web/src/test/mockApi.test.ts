import http from 'node:http';
import { describe, expect, it } from 'vitest';
import { useMockApi } from './mockApi';

describe('the mock api over msw', () => {
  useMockApi();

  it('a connection whose request is written late is still mocked, never passed through to the empty jsdom origin', async () => {
    const body = await new Promise<string>((resolve, reject) => {
      const req = http.request(`${location.origin}/api/health`, (res) => {
        let text = '';
        res.setEncoding('utf8');
        res.on('data', (chunk: string) => (text += chunk));
        res.on('end', () => resolve(text));
      });
      req.on('error', reject);
      setTimeout(() => req.end(), 50);
    });
    expect(JSON.parse(body)).toEqual({ status: 'ok', db: 'ok', version: '0.1.0' });
  });
});
