import { Button, Input } from '@mona/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { CategoryDto, Entity } from '../../data/dto';
import { ApiError } from '../../data/http';
import { patchCategory, previewTemplate } from '../../data/registry';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';
import { errorKey } from '../../data/errors';
import { TemplateField, type TemplateFieldError } from './TemplateField';

const LANGS = ['en', 'fr', 'ro'] as const;
const PREVIEW_DELAY_MS = 300;

function useDebounced<T>(value: T, ms: number): T {
  const [out, setOut] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setOut(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return out;
}

type FieldErrors = Partial<Record<'path' | 'file', TemplateFieldError>>;

export interface CategoryEditorProps {
  category: CategoryDto;
  entities: Entity[];
  documentCount: number;
}

export function CategoryEditor({ category, entities, documentCount }: CategoryEditorProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const qc = useQueryClient();
  const [labels, setLabels] = useState(category.labels);
  const [path, setPath] = useState(category.template.pathTemplate);
  const [file, setFile] = useState(category.template.fileTemplate);
  const [saveErrors, setSaveErrors] = useState<FieldErrors>({});
  const [labelError, setLabelError] = useState<{ lang: string; message: string } | null>(null);
  const debounced = useDebounced({ path, file }, PREVIEW_DELAY_MS);

  const preview = useQuery({
    queryKey: ['template-preview', debounced.path, debounced.file],
    queryFn: ({ signal }) => previewTemplate({ pathTemplate: debounced.path, fileTemplate: debounced.file }, signal),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
  const previewError = preview.data?.error && debounced.path === path && debounced.file === file ? preview.data.error : null;
  const errors: FieldErrors = { ...saveErrors };
  if (previewError) errors[previewError.template] = { offset: previewError.offset, message: previewError.message };

  const dirty = path !== category.template.pathTemplate || file !== category.template.fileTemplate || LANGS.some((l) => labels[l] !== category.labels[l]);

  const save = useMutation({
    mutationFn: () => patchCategory(category.id, { labels, template: { pathTemplate: path, fileTemplate: file } }),
    onSuccess: () => {
      setSaveErrors({});
      setLabelError(null);
      void qc.invalidateQueries({ queryKey: ['categories'] });
      toasts.push({ key: 'category-saved', message: 'entities.categories.saved', tone: 'success' });
    },
    onError: (err) => {
      if (err instanceof ApiError && err.code === 'invalid_template') {
        const d = err.details as { template?: 'path' | 'file'; offset?: number; message?: string } | null;
        setSaveErrors({ [d?.template ?? 'path']: { offset: typeof d?.offset === 'number' ? d.offset : 0, message: typeof d?.message === 'string' ? d.message : undefined } });
      } else if (err instanceof ApiError && err.code === 'invalid_value' && err.field?.startsWith('labels.')) {
        setLabelError({ lang: err.field.slice('labels.'.length), message: t(errorKey(err)) });
      } else {
        toasts.push({ key: 'category-failed', message: errorKey(err), tone: 'danger' });
      }
    },
  });

  const overrides = category.entityTemplates.map((o) => ({ ...o, name: entities.find((e) => e.id === o.entityId)?.displayName ?? o.entityId }));
  const sample = preview.data && !preview.data.error ? [...preview.data.path, preview.data.fileName ?? ''].filter(Boolean).join(' / ') : null;

  return (
    <section aria-labelledby="category-title" className="flex flex-col gap-6 rounded-lg border border-border bg-surface p-6 shadow-1" data-testid="category-editor" data-category-id={category.id}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="category-title" className="m-0 text-text [font:var(--type-title)]">
          {category.labels[lang]}
        </h2>
        <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('entities.categories.documents', { count: documentCount })}</span>
      </header>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (dirty) save.mutate();
        }}
        className="flex flex-col gap-6"
      >
        <fieldset className="m-0 flex flex-col gap-3 border-0 p-0">
          <legend className="mb-2 p-0 font-ui text-[14px] leading-5 font-semibold text-text">{t('entities.categories.labels')}</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {LANGS.map((l) => (
              <Input
                key={l}
                label={t(`language.${l}`)}
                lang={l}
                value={labels[l]}
                error={labelError?.lang === l ? labelError.message : undefined}
                onChange={(e) => setLabels({ ...labels, [l]: e.target.value })}
              />
            ))}
          </div>
          <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('entities.categories.labelsHint')}</p>
        </fieldset>
        <TemplateField kind="path" label={t('entities.categories.path')} value={path} onChange={(v) => { setPath(v); setSaveErrors({}); }} error={errors.path} hint={t('entities.categories.pathHint')} />
        <TemplateField kind="file" label={t('entities.categories.file')} value={file} onChange={(v) => { setFile(v); setSaveErrors({}); }} error={errors.file} suffix=".pdf" hint={t('entities.categories.fileHint')} />
        <div className="flex flex-col gap-1 rounded-md bg-surface-sunken p-4" data-testid="template-preview" aria-live="polite">
          <span className="font-ui text-[13px] leading-[18px] font-semibold text-text">{t('entities.categories.preview')}</span>
          <span className="[font:var(--type-filename)] break-words text-text">{sample ?? t('entities.categories.previewNone')}</span>
        </div>
        {overrides.length > 0 ? (
          <div className="flex flex-col gap-1">
            <span className="font-ui text-[14px] leading-5 font-semibold text-text">{t('entities.categories.overrides')}</span>
            <ul className="m-0 flex list-none flex-col gap-1 p-0 text-text-muted">
              {overrides.map((o) => (
                <li key={o.entityId} className="[font:var(--type-filename)]">
                  {o.name}: {o.pathTemplate} · {o.fileTemplate}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary" icon="check" loading={save.isPending} disabled={!dirty}>
            {t('entities.categories.save')}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={!dirty}
            onClick={() => {
              setLabels(category.labels);
              setPath(category.template.pathTemplate);
              setFile(category.template.fileTemplate);
              setSaveErrors({});
              setLabelError(null);
            }}
          >
            {t('entities.categories.discard')}
          </Button>
          <span className="font-ui text-[13px] leading-[18px] text-text-muted">{dirty ? t('entities.categories.applies') : t('entities.categories.unchanged')}</span>
        </div>
      </form>
    </section>
  );
}
