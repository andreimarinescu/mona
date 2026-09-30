import { describe, expect, it } from 'vitest';
import i18n from '../i18n';
import { ERROR_CODES, errorKey, errorValues } from './errors';
import { ApiError } from './http';

describe('C2 error codes', () => {
  it('has the 25 codes of C2 §1.2', () => {
    expect(ERROR_CODES).toHaveLength(25);
  });

  it.each(['en', 'fr', 'ro'])('%s has an errors.<code> string for every code', (lng) => {
    for (const code of ERROR_CODES) {
      const text = i18n.getFixedT(lng)(`errors.${code}`, { offset: 3, message: 'm' });
      expect(text, code).not.toBe(`errors.${code}`);
      expect(text.length, code).toBeGreaterThan(5);
    }
  });

  it('maps an ApiError to its key, and anything else to errors.internal', () => {
    expect(errorKey(new ApiError(409, 'superseded', 'x'))).toBe('errors.superseded');
    expect(errorKey(new ApiError(418, 'teapot', 'x'))).toBe('errors.internal');
    expect(errorKey(new Error('boom'))).toBe('errors.internal');
  });

  it('passes the offset and the validator message through for the two codes that show them', () => {
    const err = new ApiError(422, 'invalid_template', 'x', null, { offset: 7, message: 'bad' });
    expect(i18n.t(errorKey(err), errorValues(err))).toBe('The template has a mistake at character 7.');
  });
});
