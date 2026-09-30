"""Single source of truth for Mona tokens -> tokens.json (Design System page) + tokens.css (hand-off)."""
import json, sys

# ---------- colour ----------
# (name, light, dark, usage)
COLORS = [
  # brand primitives (theme-independent)
  ("brand-plaster",    "#FBF7F0", None, "Brand primitive. Lime-washed plaster: the lightest ground. Use semantic tokens in UI; primitives are for marketing, print and illustration."),
  ("brand-sand",       "#F3EBDD", None, "Brand primitive. Sand: the page ground of the light theme."),
  ("brand-terracotta", "#A94F33", None, "Brand primitive. Terracotta: the brand colour; the logo symbol and primary actions."),
  ("brand-sea",        "#1F4E5A", None, "Brand primitive. Deep sea: links, information, focus."),
  ("brand-olive",      "#5A5C2E", None, "Brand primitive. Olive: success, work done."),
  ("brand-saffron",    "#D9A441", None, "Brand primitive. Saffron: warm highlight, illustration fills. Never text on light grounds (1.9:1)."),
  ("brand-umber",      "#2B221C", None, "Brand primitive. Umber ink: text and the dark theme's ground family."),

  # grounds
  ("bg",              "#F3EBDD", "#1A1512", "Page background (sand / umber night)."),
  ("surface",         "#FBF7F0", "#241E1A", "Cards, panels, table bodies, inputs."),
  ("surface-raised",  "#FFFDF9", "#2E2621", "Dialogs, drawers, menus, toasts: anything floating above a surface."),
  ("surface-sunken",  "#EFE5D4", "#15110E", "Wells: table header rows, code/filename chips, the track of a meter or switch."),
  ("border",          "#E2D6C3", "#3B322B", "Hairlines between rows and around cards. Decorative only: never the sole edge of a control."),
  ("border-strong",   "#8C7B6B", "#85766A", "Edges of inputs, selects, checkboxes, secondary buttons (3:1 on bg, surface and surface-raised in both themes)."),

  # text
  ("text",            "#2B221C", "#F3EBDD", "Body and headings on bg, surface, surface-raised, surface-sunken."),
  ("text-muted",      "#6B5F55", "#B9AB9B", "Metadata, captions, helper text on bg, surface, surface-raised, surface-sunken (≥4.5:1 on each)."),
  ("text-inverse",    "#FBF7F0", "#1A1512", "Text on inverse grounds (tooltip)."),
  ("inverse",         "#2B221C", "#F3EBDD", "Tooltip and snackbar ground."),

  # accent
  ("accent",          "#A94F33", "#E08A6C", "Primary action fill, selected tab indicator, the brand's one loud colour. As text: on surface and surface-raised only (large or bold)."),
  ("accent-hover",    "#8E3F27", "#EBA088", "Hover/pressed state of an accent fill."),
  ("accent-soft",     "#F4DDD3", "#43261B", "Tinted ground behind accent-strong text (selected rows, active LanguageSwitch segment)."),
  ("accent-strong",   "#8A3C24", "#F2B39D", "Terracotta as small text on accent-soft or surfaces."),
  ("on-accent",       "#FFFDF9", "#1A1512", "Text and icons on an accent fill. In dark, accent is light, so this is dark."),

  # semantic states
  ("info",            "#1F4E5A", "#8FC1C8", "Links and informational text/icons on bg, surface, surface-raised."),
  ("info-soft",       "#DCE8E8", "#17323A", "Tinted ground behind info text."),
  ("success",         "#4E5027", "#C3C685", "Success text/icons on bg, surface, success-soft."),
  ("success-soft",    "#E7E8D5", "#2B2D16", "Tinted ground behind success text."),
  ("warning",         "#7A4F0E", "#E8BC66", "Warning text/icons on bg, surface, warning-soft."),
  ("warning-soft",    "#F6E7C4", "#3B2C0E", "Tinted ground behind warning text."),
  ("danger",          "#8E2A2A", "#F2A7A0", "Destructive actions and errors (C's oxblood, kept apart from terracotta by lightness and always paired with an icon + word)."),
  ("danger-soft",     "#F4DCD8", "#40191A", "Tinted ground behind danger text."),
  ("on-danger",       "#FFFDF9", "#1A1512", "Text on a danger fill (the destructive button)."),
  ("focus",           "#1F4E5A", "#8FC1C8", "Focus ring: solid 2px, 2px offset. ≥3:1 on every ground in both themes."),

  # document status (Mona-specific)
  ("status-filed-fg",       "#3F4120", "#CDD08F", "StatusPill 'Filed by Mona' text + check icon, on status-filed-bg."),
  ("status-filed-bg",       "#E7E8D5", "#2B2D16", "StatusPill 'Filed by Mona' fill (solid tint, no border)."),
  ("status-review-fg",      "#5E400B", "#EDC677", "StatusPill 'Needs review' text + question icon, on status-review-bg."),
  ("status-review-bg",      "#F6E7C4", "#3B2C0E", "StatusPill 'Needs review' fill; also carries a 1px status-review-fg border."),
  ("status-processing-fg",  "#1F4E5A", "#9CCBD2", "StatusPill 'Processing' text, spinner and dashed border (no fill) on any ground."),
  ("status-unreadable-fg",  "#7E3522", "#F0A48C", "StatusPill 'Unreadable' text + crossed-file icon, on status-unreadable-bg."),
  ("status-unreadable-bg",  "#F4DDD3", "#43261B", "StatusPill 'Unreadable' fill; also carries a diagonal hatch."),

  # confidence meter
  ("confidence-high",  "#4E5027", "#C3C685", "ConfidenceMeter filled segments at ≥85%. Always shown with the % and a word."),
  ("confidence-mid",   "#7A4F0E", "#E8BC66", "ConfidenceMeter filled segments at 60–84%."),
  ("confidence-low",   "#8E2A2A", "#F2A7A0", "ConfidenceMeter filled segments below 60%."),
  ("confidence-track", "#E2D6C3", "#3B322B", "ConfidenceMeter empty segments."),
]

# ---------- type ----------
FAMILIES = {
  "display": "\"Fraunces\", \"Iowan Old Style\", Georgia, serif",
  "sans": "\"Instrument Sans\", \"Segoe UI\", system-ui, sans-serif",
  "mono": "ui-monospace, \"SF Mono\", \"Cascadia Mono\", Menlo, monospace",
}
FONTS = [
  {"family": "Fraunces", "file": "fonts/Fraunces-Variable.woff2", "weight": "100 900", "style": "normal"},
  {"family": "Fraunces", "file": "fonts/Fraunces-Italic-Variable.woff2", "weight": "100 900", "style": "italic"},
  {"family": "Instrument Sans", "file": "fonts/InstrumentSans-Variable.woff2", "weight": "400 700", "style": "normal"},
]
TYPE_GROUPS = [
  {"name": "Editorial", "family": "display", "styles": [
    {"name": "display-xl", "fontSize": "64px", "lineHeight": "68px", "fontWeight": 400, "letterSpacing": "-0.02em", "opticalSize": 144, "sample": "Bonjour, Docteur.", "usage": "Marketing and onboarding hero only. One per screen."},
    {"name": "display",    "fontSize": "44px", "lineHeight": "50px", "fontWeight": 400, "letterSpacing": "-0.015em", "opticalSize": 96, "sample": "Trois factures attendent votre avis.", "usage": "Page titles on the web app (Journal, Documents, Rules)."},
    {"name": "title",      "fontSize": "30px", "lineHeight": "36px", "fontWeight": 400, "letterSpacing": "-0.01em", "opticalSize": 48, "sample": "Bună ziua, doamna doctor.", "usage": "Dialog and drawer titles, empty-state headlines."},
    {"name": "voice",      "fontSize": "22px", "lineHeight": "29px", "fontWeight": 400, "opticalSize": 24, "sample": "J’ai trouvé 4 courriers AGIPI. Personnels ou professionnels ?", "usage": "Mona's own question or answer at the top of a card. The editorial moment in the UI: never for labels."},
    {"name": "voice-italic", "fontSize": "18px", "lineHeight": "26px", "fontWeight": 400, "fontStyle": "italic", "opticalSize": 18, "sample": "vu, payé le 12/03 — M.", "usage": "Mona's margin notes (rule explanations, 'why I filed it here'). Sparingly."},
  ]},
  {"name": "Interface", "family": "sans", "styles": [
    {"name": "heading",     "fontSize": "18px", "lineHeight": "26px", "fontWeight": 600, "sample": "Documents to review", "usage": "Card and section headings inside the app."},
    {"name": "body-lg",     "fontSize": "17px", "lineHeight": "26px", "fontWeight": 400, "sample": "I filed 12 documents this morning.", "usage": "Chat messages and long reading."},
    {"name": "body",        "fontSize": "15px", "lineHeight": "22px", "fontWeight": 400, "sample": "Filed to SCM Dr Laurent / Prévoyance / 2026.", "usage": "Default UI text."},
    {"name": "body-strong", "fontSize": "15px", "lineHeight": "22px", "fontWeight": 600, "sample": "Facture EDF — mars 2026", "usage": "Emphasis inside body, document names, button labels."},
    {"name": "label",       "fontSize": "14px", "lineHeight": "20px", "fontWeight": 600, "sample": "Folder", "usage": "Form labels, table headers, pills."},
    {"name": "caption",     "fontSize": "13px", "lineHeight": "18px", "fontWeight": 400, "sample": "à l’instant · Journal #4182", "usage": "Timestamps, helper text, citations. Minimum size for any text."},
    {"name": "overline",    "fontSize": "12px", "lineHeight": "16px", "fontWeight": 600, "letterSpacing": "0.12em", "sample": "NEEDS REVIEW", "usage": "Uppercase section labels. Never for sentences; never in Romanian/French body copy."},
  ]},
  {"name": "Data", "family": "mono", "styles": [
    {"name": "filename", "fontSize": "13px", "lineHeight": "20px", "fontWeight": 400, "sample": "2026-03-14_Dentalia_Facture_F-88412.pdf", "usage": "Original and new filenames, journal IDs. System mono: no webfont."},
  ]},
]

SPACING = [
  ("space-1", "4px", "Icon-to-label gap inside pills."),
  ("space-2", "8px", "Gap between buttons; icon-to-label in buttons."),
  ("space-3", "12px", "Input horizontal padding; tight stacks."),
  ("space-4", "16px", "Default gap between related elements; table cell padding."),
  ("space-5", "20px", "Card gap between blocks."),
  ("space-6", "24px", "Card padding; dialog padding on mobile."),
  ("space-8", "32px", "Dialog padding; gap between cards."),
  ("space-10", "40px", "Section gap within a page."),
  ("space-12", "48px", "Page side margin on desktop."),
  ("space-16", "64px", "Gap between page sections."),
  ("space-20", "80px", "Marketing section rhythm."),
]
RADIUS = [
  ("radius-xs", "4px", "Checkboxes, meter segments, keyboard chips."),
  ("radius-sm", "8px", "Filename chips, tooltips, small tags."),
  ("radius-md", "12px", "Inputs, selects, table containers, toasts."),
  ("radius-lg", "16px", "Moodboard tiles, attachment previews, drawers' inner corners."),
  ("radius-xl", "20px", "Cards and dialogs."),
  ("radius-pill", "999px", "Buttons, StatusPill, LanguageSwitch, Tabs indicator, avatars."),
]
SHADOW = [
  ("shadow-1", "0 1px 0 rgba(43,34,28,0.05), 0 1px 3px rgba(43,34,28,0.08)", "0 1px 0 rgba(0,0,0,0.3), 0 1px 3px rgba(0,0,0,0.4)", "Resting cards on bg."),
  ("shadow-2", "0 2px 4px rgba(43,34,28,0.06), 0 10px 24px -8px rgba(43,34,28,0.22)", "0 2px 4px rgba(0,0,0,0.35), 0 10px 24px -8px rgba(0,0,0,0.6)", "Menus, popovers, toasts, hovered cards."),
  ("shadow-3", "0 4px 8px rgba(43,34,28,0.06), 0 24px 56px -16px rgba(43,34,28,0.38)", "0 4px 8px rgba(0,0,0,0.4), 0 24px 56px -16px rgba(0,0,0,0.75)", "Dialogs and drawers."),
]
ZINDEX = [
  ("z-sticky", "10", "Sticky table headers, app bar."),
  ("z-drawer", "40", "Drawer and its scrim."),
  ("z-dialog", "50", "Dialog and its scrim."),
  ("z-toast", "60", "Toast stack."),
  ("z-tooltip", "70", "Tooltips."),
]
LAYOUT = [
  ("breakpoint-sm", "480px", "Large phones and up. Media queries only (CSS variables don't work inside @media); mirror these numbers."),
  ("breakpoint-md", "768px", "Tablets and up: two-column layouts, container padding space-8."),
  ("breakpoint-lg", "1024px", "Laptops and up: persistent side navigation."),
  ("breakpoint-xl", "1280px", "Desktops: dashboards at full density, container padding space-12 from 1200px."),
  ("container-sm", "640px", "Container size sm: reading width, forms, dialogs' content, settings."),
  ("container-md", "880px", "Container size md: chat, single-column pages with tables."),
  ("container-lg", "1200px", "Container size lg (default): app pages and dashboards."),
  ("container-xl", "1440px", "Container size xl: wide dashboards and marketing pages."),
]
MOTION = [
  ("duration-instant", "80ms", "Hover colour changes, pressed state."),
  ("duration-quick", "160ms", "Tooltips, pills changing status, tab indicator."),
  ("duration-calm", "240ms", "Dialog/drawer enter, toast slide."),
  ("duration-slow", "400ms", "Filing animation (document settles into its folder)."),
  ("ease-standard", "cubic-bezier(0.2, 0, 0, 1)", "Default easing: quick out, soft landing."),
  ("ease-enter", "cubic-bezier(0, 0, 0.2, 1)", "Elements arriving."),
  ("ease-exit", "cubic-bezier(0.4, 0, 1, 1)", "Elements leaving (use duration-quick)."),
]

def tokens_json():
  ctoks=[]
  for n,l,d,u in COLORS:
    ctoks.append({"name":n,"value":(l.lower() if d is None else {"light":l.lower(),"dark":d.lower()}),"usage":u})
  return {
    "name":"Mona","version":1,
    "color":{"themes":[{"id":"light","name":"Light"},{"id":"dark","name":"Dark"}],"tokens":ctoks},
    "type":{"fonts":FONTS,"families":FAMILIES,"groups":TYPE_GROUPS},
    "spacing":{"tokens":[{"name":n,"value":v,"usage":u} for n,v,u in SPACING]},
    "radius":{"tokens":[{"name":n,"value":v,"usage":u} for n,v,u in RADIUS]},
    "shadow":{"note":"Warm umber shadows in light; plain black in dark. Elevation is quiet: most separation comes from surface colour and hairlines.","tokens":[{"name":n,"value":{"light":l,"dark":d},"usage":u} for n,l,d,u in SHADOW]},
    "zIndex":{"tokens":[{"name":n,"value":v,"usage":u} for n,v,u in ZINDEX]},
    "layout":{"note":"Breakpoints and container widths. Breakpoints are for reference in media queries; containers are used by the Container component.","tokens":[{"name":n,"value":v,"usage":u} for n,v,u in LAYOUT]},
  }

def tokens_css():
  L=[]
  L.append("/* Mona design tokens — generated from build/tokens.py. Light is default; dark via [data-theme=\"dark\"] or the OS setting. */\n")
  for f in FONTS:
    L.append(f"@font-face {{ font-family: \"{f['family']}\"; src: url(\"{f['file']}\") format(\"woff2\"); font-weight: {f['weight']}; font-style: {f['style']}; font-display: swap; }}")
  L.append("")
  def block(sel, theme):
    out=[f"{sel} {{"]
    if theme=="light": out.append("  color-scheme: light;")
    else: out.append("  color-scheme: dark;")
    for n,l,d,u in COLORS:
      if theme=="dark" and d is None: continue
      out.append(f"  --{n}: {(l if theme=='light' or d is None else d)};")
    for n,l,d,u in SHADOW:
      out.append(f"  --{n}: {l if theme=='light' else d};")
    out.append("}")
    return out
  L+=block(':root, [data-theme="light"]','light')
  L.append("")
  L+=block('[data-theme="dark"]','dark')
  L.append("")
  dark=block(':root:not([data-theme="light"])','dark')
  L.append("@media (prefers-color-scheme: dark) {")
  L+=["  "+x for x in dark]
  L.append("}")
  L.append("")
  L.append(":root {")
  for k,v in FAMILIES.items(): L.append(f"  --font-{k}: {v};")
  for n,v,u in SPACING+RADIUS+ZINDEX+LAYOUT: L.append(f"  --{n}: {v};")
  for n,v,u in MOTION: L.append(f"  --{n}: {v};")
  L.append("}")
  L.append("")
  L.append("@media (prefers-reduced-motion: reduce) {\n  :root { --duration-quick: 0ms; --duration-calm: 0ms; --duration-slow: 0ms; }\n}")
  L.append("")
  # type classes
  for g in TYPE_GROUPS:
    for s in g["styles"]:
      fam=s.get("family",g["family"])
      decl=[f"font-family: var(--font-{fam})", f"font-size: {s['fontSize']}", f"line-height: {s['lineHeight']}", f"font-weight: {s['fontWeight']}"]
      if "letterSpacing" in s: decl.append(f"letter-spacing: {s['letterSpacing']}")
      if s.get("fontStyle"): decl.append(f"font-style: {s['fontStyle']}")
      if fam=="display": decl.append(f"font-variation-settings: 'SOFT' 100, 'WONK' 0, 'opsz' {s.get('opticalSize',24)}")
      if s["name"]=="overline": decl.append("text-transform: uppercase")
      L.append(f".type-{s['name']} {{ {'; '.join(decl)}; }}")
  return "\n".join(L)+"\n"

# ---------- contrast audit ----------
def lum(h):
  h=h.lstrip('#'); r=[int(h[i:i+2],16)/255 for i in (0,2,4)]
  r=[c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4 for c in r]
  return 0.2126*r[0]+0.7152*r[1]+0.0722*r[2]
def cr(a,b):
  x,y=sorted([lum(a),lum(b)],reverse=True); return (x+.05)/(y+.05)

PAIRS=[ # fg, [grounds], minimum
  ("text",["bg","surface","surface-raised","surface-sunken"],4.5),
  ("text-muted",["bg","surface","surface-raised","surface-sunken"],4.5),
  ("text-inverse",["inverse"],4.5),
  ("accent",["bg","surface","surface-raised"],3.0),
  ("accent-strong",["accent-soft","surface","bg"],4.5),
  ("on-accent",["accent","accent-hover"],4.5),
  ("info",["bg","surface","surface-raised","info-soft"],4.5),
  ("success",["bg","surface","success-soft"],4.5),
  ("warning",["bg","surface","warning-soft"],4.5),
  ("danger",["bg","surface","surface-raised","danger-soft"],4.5),
  ("on-danger",["danger"],4.5),
  ("focus",["bg","surface","surface-raised","surface-sunken"],3.0),
  ("border-strong",["bg","surface","surface-raised"],3.0),
  ("status-filed-fg",["status-filed-bg"],4.5),
  ("status-review-fg",["status-review-bg"],4.5),
  ("status-processing-fg",["bg","surface","surface-raised"],4.5),
  ("status-unreadable-fg",["status-unreadable-bg"],4.5),
  ("confidence-high",["surface","surface-raised"],3.0),
  ("confidence-mid",["surface","surface-raised"],3.0),
  ("confidence-low",["surface","surface-raised"],3.0),
]
def audit():
  vals={n:(l,d or l) for n,l,d,u in COLORS}
  bad=0; rows=[]
  for th in (0,1):
    for fg,grounds,mn in PAIRS:
      for g in grounds:
        c=cr(vals[fg][th],vals[g][th]); ok=c>=mn
        rows.append((['light','dark'][th],fg,g,round(c,2),mn,ok))
        if not ok: bad+=1
  return rows,bad

if __name__=="__main__":
  rows,bad=audit()
  for r in rows:
    if not r[5] or '-v' in sys.argv: print(*r)
  print("failing pairs:",bad, "of", len(rows))
