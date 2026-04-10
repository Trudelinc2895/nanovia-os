# Design System — TK Verse UI

> Palette Titanium/Noir + Bleu primaire · composants React réutilisables · tokens centralisés

---

## Palette

| Token Tailwind | Valeur | Usage |
|---|---|---|
| `bg-bg-base` | `#0D0F12` | Fond de page |
| `bg-ui-surface` | `#13151A` | Cards, sidebars |
| `bg-ui-elevated` | `#1A1C23` | Modals, dropdowns |
| `border-ui-border` | `#1E2130` | Bordures |
| `text-primary` / `bg-primary` | `#4F8CFF` | CTA, liens actifs |
| `bg-primary-muted` | `#4F8CFF1A` | Backgrounds accent |
| `text-text-primary` | `#F1F5F9` | Texte principal |
| `text-text-secondary` | `#8892A4` | Labels, descriptions |
| `text-text-muted` | `#5A6478` | Placeholders |
| `text-success-text` / `bg-success` | `#4ADE80` / `#22C55E` | Succès |
| `text-warning-text` / `bg-warning` | `#FCD34D` / `#F59E0B` | Avertissements |
| `text-danger-text` / `bg-danger` | `#F87171` / `#EF4444` | Erreurs, danger |

---

## Composants

### Button

```tsx
import { Button, buttonVariants } from "@/components/ui";

// Composant complet
<Button variant="primary" size="md" loading={false} fullWidth={false}>
  Souscrire
</Button>

// Pour les liens Next.js <Link>
<Link href="/pricing" className={buttonVariants("primary", "md")}>
  Voir les prix
</Link>
```

**Variants :** `primary` · `secondary` · `ghost` · `danger`  
**Sizes :** `sm` · `md` · `lg`

---

### Card

```tsx
import { Card } from "@/components/ui";

<Card variant="outlined">
  Contenu avec bordure fine
</Card>

<Card variant="solid" className="border-primary/60">
  Carte mise en avant
</Card>
```

**Variants :** `outlined` · `solid`

---

### Input

```tsx
import { Input } from "@/components/ui";

<Input
  label="Email"
  type="email"
  placeholder="vous@exemple.ca"
  error="Email invalide"
  helperText="Utilisé pour les notifications"
/>
```

- Password toggle intégré automatiquement pour `type="password"`
- `forwardRef` compatible avec react-hook-form

---

### Badge

```tsx
import { Badge } from "@/components/ui";

<Badge variant="success" size="sm">Actif</Badge>
<Badge variant="info">PRO</Badge>
<Badge variant="warning">Expiré</Badge>
<Badge variant="danger">Suspendu</Badge>
```

**Variants :** `info` · `success` · `warning` · `danger`  
**Sizes :** `sm` · `md`

---

## Import barrel

```tsx
import { Button, Card, Input, Badge, buttonVariants } from "@/components/ui";
```

---

## Configuration Tailwind

Les tokens sont définis dans `tailwind.config.js` via `theme.extend.colors`.  
Les valeurs source viennent de `components/ui/tokens.ts`.

**Aliases rétrocompat :** `tk-dark`, `tk-card`, `tk-border`, `tk-blue`, `brand` → tous remappés sur la nouvelle palette.

---

## Principes

- Pas de `template literal` dans les className JSX — utiliser la concaténation de strings pour éviter les bugs de build
- Toutes les couleurs via tokens Tailwind — jamais de valeurs hardcodées
- Responsive par défaut — grilles `sm:` et `lg:` systématiques
- Bundle léger — pas d'animation lourde pour VPS OVHcloud
