# Data access

Components read through the hooks in `hooks.ts`; once C2 freezes, swap the stub entries in `providers.ts` (`stubProviders`) for the generated API client and nothing else changes.
