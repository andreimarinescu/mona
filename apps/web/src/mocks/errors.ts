export class MockError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly field: string | null = null,
    readonly details: Record<string, unknown> | null = null,
    readonly headers: Record<string, string> = {},
  ) {
    super(message);
  }
}
