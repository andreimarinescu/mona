import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Badge,
  Banner,
  Button,
  Card,
  CategoryIcon,
  Citation,
  ConfidenceMeter,
  Dialog,
  Icon,
  Input,
  Menu,
  MonaAvatar,
  Progress,
  ReasonChip,
  Select,
  StatusPill,
  Table,
  Tag,
  Toast,
  format,
} from '@mona/ui';

function Family({ name, children }: { name: string; children: ReactNode }) {
  return (
    <section aria-label={name} data-family={name} className="flex flex-col gap-2">
      <h2 className="font-ui text-text-muted">{name}</h2>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  );
}

const HANDOFF_ICONS = [
  'archive', 'building-2', 'chart-column', 'clock', 'globe', 'hard-drive', 'history', 'house',
  'inbox', 'list-checks', 'menu', 'message-square', 'paperclip', 'route', 'settings', 'upload',
] as const;

const rows = [
  { id: 'a', date: '2026-09-22', name: 'URSSAF appel T3', amount: format.money(1284, 'EUR', 'fr') },
  { id: 'b', date: '2026-09-18', name: 'Facture labo', amount: format.money(312.5, 'EUR', 'fr') },
];

export function DsGallery() {
  const { t } = useTranslation();
  const [dialogOpen, setDialogOpen] = useState(false);
  return (
    <main className="mx-auto flex max-w-lg flex-col gap-6 p-8">
      <h1 className="font-voice text-text">{t('dev.ds.title')}</h1>
      <Family name="Button">
        <Button variant="primary" icon="check">Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="danger" size="sm">Danger</Button>
        <Button iconOnly icon="more" aria-label="More" />
      </Family>
      <Family name="Input">
        <Input label="Supplier" hint="As printed on the document" defaultValue="URSSAF" />
      </Family>
      <Family name="Select">
        <Select
          label="Category"
          options={[
            { value: 'tax', label: 'Tax' },
            { value: 'bank', label: 'Bank' },
          ]}
          defaultValue="tax"
        />
      </Family>
      <Family name="StatusPill">
        <StatusPill status="filed" />
        <StatusPill status="review" />
        <StatusPill status="processing" />
        <StatusPill status="unreadable" />
      </Family>
      <Family name="ConfidenceMeter">
        <ConfidenceMeter value={0.92} />
        <ConfidenceMeter value={72} />
        <ConfidenceMeter value={0.41} />
      </Family>
      <Family name="Card">
        <Card from="mona" eyebrow="Today" title="Three documents filed" voice="I filed the URSSAF demand under Taxes.">
          Body text
        </Card>
      </Family>
      <Family name="Dialog">
        <Button variant="secondary" onClick={() => setDialogOpen(true)}>
          Open dialog
        </Button>
        <Dialog
          open={dialogOpen}
          onClose={() => setDialogOpen(false)}
          title="Delete this document?"
          tone="danger"
          footer={
            <Button variant="danger" onClick={() => setDialogOpen(false)}>
              Delete
            </Button>
          }
        >
          This can’t be undone.
        </Dialog>
      </Family>
      <Family name="Toast">
        <Toast
          tone="success"
          from="mona"
          title="Filed 12 documents"
          action={{ label: 'Undo', onClick: () => {}, icon: 'undo' }}
          onClose={() => {}}
        />
      </Family>
      <Family name="MonaAvatar">
        <MonaAvatar size={40} />
        <MonaAvatar size={40} state="thinking" />
        <MonaAvatar size={40} state="offline" />
      </Family>
      <Family name="Citation">
        <p>
          The URSSAF demand is due on 15 October <Citation n={1} onClick={() => {}} />.
        </p>
      </Family>
      <Family name="Icon">
        <Icon name="search" />
        <Icon name="calendar" />
        <Icon name="loader" spin label="Loading" />
      </Family>
      <Family name="HandoffIcons">
        {HANDOFF_ICONS.map((name) => (
          <Icon key={name} name={name} label={name} />
        ))}
      </Family>
      <Family name="ReasonChip">
        <ReasonChip reason="low" />
        <ReasonChip reason="entity" />
        <ReasonChip reason="conflict" />
        <ReasonChip reason="unreadable" />
      </Family>
      <Family name="CategoryIcon">
        <CategoryIcon category="tax" />
        <CategoryIcon category="bank" />
        <CategoryIcon category="insurance" showTitle />
      </Family>
      <Family name="Banner">
        <Banner tone="info" title="Mona is offline">
          She will catch up when the connection is back.
        </Banner>
      </Family>
      <Family name="Progress">
        <Progress value={40} label="Reading documents" showValue />
      </Family>
      <Family name="Badge">
        <Badge count={3} label="3 to review" />
        <Badge tone="accent">New</Badge>
      </Family>
      <Family name="Tag">
        <Tag icon="calendar">FY 2026</Tag>
        <Tag selected onToggle={() => {}}>
          URSSAF
        </Tag>
      </Family>
      <Family name="Table">
        <Table
          caption="Recent documents"
          rowKey="id"
          columns={[
            { key: 'date', label: 'Date' },
            { key: 'name', label: 'Document' },
            { key: 'amount', label: 'Amount', numeric: true },
          ]}
          rows={rows}
        />
      </Family>
      <Family name="Menu">
        <Menu
          label="Document actions"
          trigger={<Button variant="secondary" iconEnd="chevron-down">Actions</Button>}
          items={[
            { id: 'open', label: 'Open', icon: 'file' },
            { id: 'copy', label: 'Copy name', icon: 'copy' },
            { type: 'separator' },
            { id: 'delete', label: 'Delete', icon: 'trash', danger: true },
          ]}
        />
      </Family>
    </main>
  );
}
