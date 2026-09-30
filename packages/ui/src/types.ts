import type * as React from 'react';

export type Lang = 'en' | 'fr' | 'ro';
export type DocStatus = 'filed' | 'review' | 'processing' | 'unreadable';
export type Category = 'bank' | 'invoice' | 'tax' | 'insurance' | 'payroll' | 'training' | 'travel' | 'personal';
export type ExtraIconName = 'archive' | 'building-2' | 'chart-column' | 'clock' | 'globe' | 'hard-drive' | 'history' | 'house' | 'inbox' | 'list-checks' | 'menu' | 'message-square' | 'paperclip' | 'route' | 'settings' | 'upload';
export type IconName = 'chevron-left' | 'chevron-right' | 'more' | 'pencil' | 'copy' | 'download' | 'filter' | 'check' | 'circle-check' | 'help' | 'loader' | 'file-x' | 'file' | 'folder' | 'x' | 'chevron-down' | 'undo' | 'sun' | 'moon' | 'monitor' | 'info' | 'alert' | 'bell' | 'search' | 'arrow-right' | 'trash' | 'calendar' | 'lock' | 'external' | 'send' | Category | ExtraIconName;

/** Pill-shaped button. One `primary` per view. */
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'quiet' | 'danger';
  size?: 'md' | 'sm';
  /** Leading icon name. */
  icon?: IconName;
  iconEnd?: IconName;
  /** Icon-only square button: pass `aria-label`. */
  iconOnly?: boolean;
  loading?: boolean;
}

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode;
  /** Shown after the label, e.g. "optional" / "facultatif" / "opțional". */
  optional?: string; icon?: IconName;
}

export interface SelectOption { value: string; label: string }
export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; optional?: string;
  options: Array<SelectOption | { label: string; options: SelectOption[] }>;
  placeholder?: string;
}

export interface TabItem { id: string; label: React.ReactNode; count?: number; panelId?: string }
export interface TabsProps { tabs: TabItem[]; value?: string; defaultValue?: string; onChange?: (id: string) => void; label?: string; className?: string }

/** Document status. Always icon + word; `compact` shows the icon with a tooltip. */
export interface StatusPillProps { status: DocStatus; lang?: Lang; label?: string; size?: 'md' | 'sm'; compact?: boolean; className?: string }

/** Five segments + percentage + word. value: 0–1 or 0–100. Default bands: ≥85% high, ≥60% medium, else low. */
export interface ConfidenceThresholds { high?: number; medium?: number }
export interface ConfidenceMeterProps { value: number; lang?: Lang; hideLabel?: boolean; hideWord?: boolean; className?: string; /** Band cut-offs as fractions (0–1) or percentages; defaults 0.85 and 0.6. */ thresholds?: ConfidenceThresholds }

export interface CardProps {
  /** 'mona' adds her avatar and name in the header. */
  from?: 'mona';
  avatarState?: 'idle' | 'thinking' | 'offline';
  eyebrow?: React.ReactNode; meta?: React.ReactNode;
  status?: DocStatus | React.ReactElement;
  title?: React.ReactNode;
  /** Mona's own sentence, set in the editorial `voice` style. */
  voice?: React.ReactNode;
  actions?: React.ReactNode; footer?: React.ReactNode; children?: React.ReactNode;
  variant?: 'default' | 'flat'; lang?: Lang; onClick?: () => void; as?: string; className?: string; style?: React.CSSProperties;
}

export interface TableColumn<R = any> { key: string; label: React.ReactNode; numeric?: boolean; align?: 'start' | 'end'; render?: (row: R) => React.ReactNode }
export interface TableProps<R = any> { columns: TableColumn<R>[]; rows: R[]; footer?: Partial<Record<string, React.ReactNode>>; caption?: React.ReactNode; rowKey?: string; maxHeight?: number | string; className?: string }

export interface ToastProps {
  tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger'; from?: 'mona';
  title: React.ReactNode; message?: React.ReactNode;
  action?: { label: string; onClick: () => void; icon?: IconName };
  onClose?: () => void; lang?: Lang; className?: string;
}
export interface ToastStackProps { children?: React.ReactNode; inline?: boolean }

export interface DialogProps { open: boolean; onClose?: () => void; title: React.ReactNode; children?: React.ReactNode; footer?: React.ReactNode; size?: 'default' | 'wide'; tone?: 'default' | 'danger'; persistent?: boolean; lang?: Lang; className?: string }

export interface DrawerProps { open: boolean; onClose?: () => void; title: React.ReactNode; children?: React.ReactNode; footer?: React.ReactNode; side?: 'right' | 'bottom'; lang?: Lang; className?: string }

export interface TooltipProps { content: React.ReactNode; children: React.ReactElement; side?: 'top' | 'bottom'; defaultOpen?: boolean }

export interface MonaAvatarProps { size?: 20 | 28 | 32 | 40 | 56 | number; state?: 'idle' | 'thinking' | 'offline'; label?: string; className?: string }

export interface LanguageSwitchProps { value?: Lang; defaultValue?: Lang; onChange?: (lang: Lang) => void; label?: string; className?: string }

export interface ThemeToggleProps { value?: 'light' | 'dark' | 'system'; defaultValue?: 'light' | 'dark' | 'system'; onChange?: (theme: 'light' | 'dark' | 'system') => void; system?: boolean; showLabels?: boolean; lang?: Lang; className?: string }

/** Numbered source marker inside Mona's answers. */
export interface CitationProps { n: number; href?: string; onClick?: () => void; label?: string }
export interface SourceItem { n?: number; id?: string; title: React.ReactNode; detail?: React.ReactNode; href?: string }
export interface SourceListProps { sources: SourceItem[]; label?: string; className?: string }

export interface EmptyStateProps { art?: string | React.ReactNode; title: React.ReactNode; children?: React.ReactNode; action?: React.ReactNode; className?: string }

export interface IconProps { name: IconName; size?: number; strokeWidth?: number; label?: string; spin?: boolean; className?: string }
export interface CategoryIconProps { category: Category; size?: number; iconSize?: number; lang?: Lang; label?: string; showTitle?: boolean }


/* ---------------- Batch 2: shared primitives ---------------- */
export type Space = 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | 20;
export type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export interface FieldA11y { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }
export interface FormFieldProps { label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; optional?: boolean | string; id?: string; lang?: Lang; className?: string; children: React.ReactElement | ((a11y: FieldA11y) => React.ReactNode) }

export interface CheckboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> { label?: React.ReactNode; description?: React.ReactNode; indeterminate?: boolean; error?: boolean }

export interface RadioOption { value: string; label: React.ReactNode; description?: React.ReactNode; meta?: React.ReactNode; disabled?: boolean }
export interface RadioGroupProps { legend?: React.ReactNode; options: RadioOption[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; variant?: 'default' | 'cards'; orientation?: 'vertical' | 'horizontal'; hint?: React.ReactNode; error?: React.ReactNode; name?: string; className?: string }

export interface SwitchProps { label: React.ReactNode; description?: React.ReactNode; checked?: boolean; defaultChecked?: boolean; onChange?: (checked: boolean) => void; disabled?: boolean; id?: string; className?: string }

export interface TextareaProps extends Omit<React.TextareaHTMLAttributes<HTMLTextAreaElement>, 'onChange'> { label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; optional?: boolean | string; autoResize?: boolean; showCount?: boolean; lang?: Lang; onChange?: React.ChangeEventHandler<HTMLTextAreaElement> }

export interface SegmentedOption { value: string; label: string; icon?: IconName }
export interface SegmentedControlProps { options: SegmentedOption[]; value?: string; defaultValue?: string; onChange?: (value: string) => void; label: string; iconOnly?: boolean; className?: string }

export interface ComboboxOption { value: string; label: string; description?: string; group?: string; disabled?: boolean }
export interface ComboboxProps { 'aria-describedby'?: string; options: ComboboxOption[]; multiple?: boolean; value?: string | string[] | null; defaultValue?: string | string[] | null; onChange?: (value: any) => void; label?: React.ReactNode; 'aria-label'?: string; placeholder?: string; hint?: React.ReactNode; error?: React.ReactNode; optional?: boolean | string; emptyText?: string; disabled?: boolean; id?: string; lang?: Lang; className?: string }

export interface SearchFieldProps { value?: string; defaultValue?: string; onChange?: (value: string) => void; onSearch?: (value: string) => void; label?: string; placeholder?: string; size?: 'md' | 'sm'; lang?: Lang; className?: string }

export interface FileInputProps { onFiles?: (files: File[]) => void; label?: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; optional?: boolean | string; accept?: string; acceptLabel?: string; multiple?: boolean; lang?: Lang; className?: string }

export interface LinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> { variant?: 'inline' | 'standalone' | 'muted'; external?: boolean }

export type Placement = 'bottom-start' | 'bottom-end' | 'top-start' | 'top-end';
export interface PopoverProps { trigger: React.ReactElement | ((api: { open: boolean; toggle: () => void; id: string }) => React.ReactNode); children: React.ReactNode | ((api: { close: () => void }) => React.ReactNode); open?: boolean; onOpenChange?: (open: boolean) => void; placement?: Placement; label?: string; width?: number | string; matchWidth?: boolean; className?: string }

export type MenuItem = { id: string; label: React.ReactNode; icon?: IconName; shortcut?: string; danger?: boolean; disabled?: boolean; onSelect?: (id: string) => void } | { type: 'separator' } | { type: 'label'; label: React.ReactNode };
export interface MenuProps { trigger: React.ReactElement; items: MenuItem[]; label?: string; placement?: Placement; open?: boolean; onOpenChange?: (open: boolean) => void }

export interface BannerProps { tone?: Tone; title?: React.ReactNode; children?: React.ReactNode; actions?: React.ReactNode; onDismiss?: () => void; variant?: 'inline' | 'page'; from?: 'mona'; icon?: IconName; lang?: Lang; className?: string }

export interface ProgressProps { value?: number; max?: number; label?: React.ReactNode; valueText?: string; showValue?: boolean; size?: 'md' | 'sm'; lang?: Lang; className?: string }
export interface SpinnerProps { size?: 16 | 20 | 24 | 32; label?: React.ReactNode; lang?: Lang; className?: string }
export interface SkeletonProps { variant?: 'text' | 'rect' | 'circle'; lines?: number; width?: number | string; height?: number | string; className?: string }

export interface BadgeProps { count?: number; max?: number; children?: React.ReactNode; tone?: Tone | 'accent'; label?: string; className?: string }
export interface TagProps { children: React.ReactNode; icon?: IconName; onRemove?: () => void; onToggle?: (selected: boolean) => void; selected?: boolean; size?: 'md' | 'sm'; lang?: Lang; className?: string }

export interface Crumb { label: React.ReactNode; href?: string; onClick?: React.MouseEventHandler }
export interface BreadcrumbsProps { items: Crumb[]; maxItems?: number; label?: string; lang?: Lang; className?: string }
export interface PaginationProps { page: number; pageCount: number; onChange?: (page: number) => void; total?: number; pageSize?: number; variant?: 'default' | 'compact'; label?: string; lang?: Lang; className?: string }
export interface AccordionItem { id: string; title: React.ReactNode; content: React.ReactNode; meta?: React.ReactNode }
export interface AccordionProps { items: AccordionItem[]; multiple?: boolean; defaultOpen?: string[]; open?: string[]; onChange?: (open: string[]) => void; variant?: 'default' | 'card'; headingLevel?: 2 | 3 | 4 | 5 | 6; className?: string }

export interface AvatarProps { name: string; src?: string; size?: 24 | 32 | 40 | 56 | number; tone?: 'sea' | 'olive' | 'saffron' | 'sand' | 'umber'; showTitle?: boolean; className?: string }
export interface AvatarGroupProps { people: Array<{ name: string; src?: string }>; max?: number; size?: number; label?: string; lang?: Lang; className?: string }

export interface DescriptionItem { term: React.ReactNode; detail: React.ReactNode; numeric?: boolean; mono?: boolean }
export interface DescriptionListProps { items: DescriptionItem[]; layout?: 'rows' | 'stacked' | 'grid'; columns?: number; className?: string }
export interface ListProps { children?: React.ReactNode; variant?: 'default' | 'card'; dividers?: boolean; ordered?: boolean; label?: string; className?: string }
export interface ListItemProps { title: React.ReactNode; description?: React.ReactNode; leading?: React.ReactNode; meta?: React.ReactNode; href?: string; onClick?: () => void; action?: React.ReactNode; selected?: boolean; className?: string }

type Align = 'start' | 'center' | 'end' | 'stretch' | 'baseline' | 'between';
interface LayoutBase extends React.HTMLAttributes<HTMLElement> { as?: string; gap?: Space | string; align?: Align; justify?: Align }
export type StackProps = LayoutBase;
export type InlineProps = LayoutBase & { wrap?: boolean };
export type GridProps = LayoutBase & { columns?: number; minItemWidth?: number | string };
export interface ContainerProps extends React.HTMLAttributes<HTMLElement> { as?: string; size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'; padded?: boolean }

export type ReasonKind = 'low' | 'entity' | 'conflict' | 'unreadable';
/** Why a document is in the review queue: icon + word + outline pattern. */
export interface ReasonChipProps { reason: ReasonKind; lang?: Lang; label?: string; className?: string }

export interface MonaFormat {
  number(n: number, lang?: Lang, opts?: Intl.NumberFormatOptions): string;
  money(amount: number, currency?: 'EUR' | 'RON' | string, lang?: Lang): string;
  percent(fraction: number, lang?: Lang, digits?: number): string;
  date(d: Date | string | number, lang?: Lang, style?: 'long' | 'medium' | 'short' | 'dayMonth'): string;
  time(d: Date | string | number, lang?: Lang): string;
  relative(d: Date | string | number, lang?: Lang, now?: Date): string;
  fileSize(bytes: number, lang?: Lang): string;
}

