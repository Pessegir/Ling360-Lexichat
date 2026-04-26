---
name: Dark Luxury & Precision
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#3a3939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#c4c7c8'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#8e9192'
  outline-variant: '#444748'
  surface-tint: '#c6c6c7'
  primary: '#ffffff'
  on-primary: '#2f3131'
  primary-container: '#e2e2e2'
  on-primary-container: '#636565'
  inverse-primary: '#5d5f5f'
  secondary: '#d3fbff'
  on-secondary: '#00363a'
  secondary-container: '#00eefc'
  on-secondary-container: '#00686f'
  tertiary: '#ffffff'
  on-tertiary: '#313030'
  tertiary-container: '#e5e2e1'
  on-tertiary-container: '#656464'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e2e2e2'
  primary-fixed-dim: '#c6c6c7'
  on-primary-fixed: '#1a1c1c'
  on-primary-fixed-variant: '#454747'
  secondary-fixed: '#7df4ff'
  secondary-fixed-dim: '#00dbe9'
  on-secondary-fixed: '#002022'
  on-secondary-fixed-variant: '#004f54'
  tertiary-fixed: '#e5e2e1'
  tertiary-fixed-dim: '#c8c6c5'
  on-tertiary-fixed: '#1c1b1b'
  on-tertiary-fixed-variant: '#474746'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  headline-xl:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: 0em
  body-md:
    fontFamily: Space Grotesk
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: 0em
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1'
    letterSpacing: 0.1em
  mono-data:
    fontFamily: Space Grotesk
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1'
    letterSpacing: -0.02em
spacing:
  unit: 4px
  gutter: 16px
  margin: 32px
  container-max: 1440px
  stack-sm: 8px
  stack-md: 24px
  stack-lg: 48px
---

## Brand & Style

The design system is built upon the concept of "Surgical Stealth"—a high-end, technical aesthetic that prioritizes absolute clarity and professional restraint. It evokes the feeling of aerospace instrumentation and luxury horology, where every element exists for a specific purpose. 

The visual style is a fusion of **Minimalism** and **Glassmorphism**, characterized by deep, light-absorbing surfaces punctuated by razor-thin light-emitting strokes. The emotional response is one of authority, exclusivity, and technological superiority. There is no room for decoration; beauty is derived from the precision of the grid and the quality of the typography.

## Colors

The palette is anchored in the "Obsidian" spectrum: a series of near-black neutrals that provide depth without losing the stealth aesthetic. 

- **Primary:** A crisp, high-contrast white used exclusively for essential information and primary actions.
- **Secondary (Accent):** A surgical cyan glow, used sparingly for active states or critical "live" data points. 
- **Surface Layers:** The base is a true obsidian black (#050505). Elevated surfaces use deep charcoal (#0A0A0A) and graphite (#121212) to create a sense of physical layering.
- **Stroke/Border:** A muted grey (#222222) is used for structural lines, while a higher-brightness white (#FFFFFF) at low opacity is used for the signature "glowing edge" effect.

## Typography

This design system utilizes **Space Grotesk** across all levels to maintain a technical, geometric rigor. The typography reflects a "form follows function" philosophy.

Headlines are set with tight tracking and aggressive line heights to create a commanding presence. Labels and secondary data points use uppercase styling with increased letter spacing to emulate industrial marking and cockpit instrumentation. Body text remains clean and legible, ensuring that high-density professional information is easily digestible.

## Layout & Spacing

The layout is governed by a **strict 12-column fixed grid** that emphasizes mathematical alignment and density. 

A 4px baseline grid ensures that every element, from an icon to a card, is positioned with surgical precision. Margins are generous at the edges of the screen to maintain the "luxury" feel of whitespace, while internal gutters remain tight (16px) to keep related data components feeling integrated and technical. Components should prioritize vertical stacking with consistent "rhythm" units of 8px, 24px, and 48px.

## Elevation & Depth

Depth is not communicated through traditional ambient shadows, which feel too organic for this aesthetic. Instead, the design system utilizes **Tonal Layers** and **Glassmorphism**.

1.  **Base Surface:** The darkest obsidian black (#050505).
2.  **Raised Surfaces:** Subtle increases in value (#0A0A0A) combined with a 1px internal "light leak" border at the top edge.
3.  **Overlays:** Semi-transparent charcoal layers (opacity 60-80%) with a heavy backdrop blur (20px - 40px) to create a frosted-glass effect that feels like polished obsidian.
4.  **Glowing Borders:** Instead of shadows, active or focused elements use a 1px border with a soft outer glow (0-2px blur) to simulate a light-emissive edge.

## Shapes

The design system rejects all curves. A **0px border radius (Sharp)** policy is applied to every single UI element, including buttons, inputs, cards, and modals. 

This sharp geometry reinforces the professional, "no-nonsense" technical narrative. Intersecting lines should meet at perfect 90-degree angles. This severity is offset by the softness of the glassmorphic blurs and the thinness of the strokes, creating a sophisticated balance between hardness and light.

## Components

### Buttons
Primary buttons are solid white with black text. Secondary buttons are transparent with a 1px white border. On hover, buttons should exhibit a subtle outer glow or a slight increase in border thickness to 1.5px. All edges must remain perfectly sharp.

### Cards & Containers
Containers use the "Glassmorphism" treatment—dark semi-transparent backgrounds with a 1px border (Color: White, Opacity: 10%). For luxury emphasis, use a subtle linear gradient on the border to simulate light hitting a sharp edge.

### Input Fields
Inputs are minimalist, consisting of a 1px bottom border that glows when focused. Placeholder text should be set in the "label-caps" style at 40% opacity.

### Chips & Tags
Small, rectangular boxes with 1px borders. Use the "mono-data" typography for the content. Tags for "Active" or "Live" states may use the secondary accent cyan glow.

### Precision Dividers
Dividers should be 1px thick, often utilizing a "fading" gradient at the ends so they don't abruptly hit container edges, maintaining the stealth aesthetic.

### Navigation
Top navigation should be fixed with a heavy backdrop blur, creating a "HUD" (Heads-Up Display) effect where content slides underneath the translucent dark glass.