import { describe, expect, it } from 'vitest';
import { pageContext } from './pageContext';

const doc = 'doc_01j9zq3k8e6y4v2m7c5r1t0b9a';

describe('pageContext', () => {
  it.each([
    ['/', 'Home'],
    ['/chat', 'Chat page'],
    [`/chat/cnv_01j9zq3k8e6y4v2m7c5r1t0b9a`, 'Chat page'],
    ['/intake', 'Intake'],
    ['/review', 'Review queue'],
    [`/review/${doc}`, `Review queue, document ${doc}`],
    ['/archive', 'Archive'],
    ['/archive/folders/Cabinet%20Marchand/2026', 'Archive, folder view, depth 2'],
    [`/documents/${doc}`, `Document ${doc}`],
    ['/rules', 'Rules'],
    ['/rules/rul_01j9zq3k8e6y4v2m7c5r1t0b9a', 'Rules, rule rul_01j9zq3k8e6y4v2m7c5r1t0b9a'],
    ['/entities', 'Entities and taxonomy'],
    ['/entities/categories/tax', 'Entities and taxonomy, category tax'],
    ['/activity', 'Activity log'],
    ['/settings', 'Settings'],
    ['/unlock', 'Unlock screen'],
    ['/dev/chat', 'Developer page'],
    ['/reports', 'Unknown page'],
  ])('%s -> %s', (pathname, summary) => {
    expect(pageContext({ pathname }).summary).toBe(summary);
  });

  it('adds the page number of a document and the section of settings', () => {
    expect(pageContext({ pathname: `/documents/${doc}`, search: '?page=2' })).toEqual({
      route: `/documents/${doc}?page=2`,
      summary: `Document ${doc}, page 2`,
    });
    expect(pageContext({ pathname: '/settings', hash: 'profile' }).summary).toBe('Settings, profile section');
    expect(pageContext({ pathname: '/settings', hash: '#about' }).summary).toBe('Settings, about section');
  });

  it('names the entity scope on the screens it filters', () => {
    expect(pageContext({ pathname: '/archive', scope: 'ent_x1' }).summary).toBe('Archive, filtered to entity ent_x1');
    expect(pageContext({ pathname: '/archive', scope: 'all' }).summary).toBe('Archive');
    expect(pageContext({ pathname: '/chat', scope: 'ent_x1' }).summary).toBe('Chat page');
    expect(pageContext({ pathname: '/settings', scope: 'ent_x1' }).summary).toBe('Settings');
  });

  it('never echoes ids or text that are not id-shaped, and caps the lengths', () => {
    expect(pageContext({ pathname: '/documents/URSSAF%20appel%20T3' }).summary).toBe('Document unknown');
    expect(pageContext({ pathname: '/rules/a b' }).summary).toBe('Rules');
    expect(pageContext({ pathname: '/archive', scope: 'line\nbreak' }).summary).toBe('Archive');
    const long = pageContext({ pathname: `/archive/${'x'.repeat(400)}` });
    expect(long.route).toHaveLength(200);
    expect(long.summary.length).toBeLessThanOrEqual(300);
  });
});
