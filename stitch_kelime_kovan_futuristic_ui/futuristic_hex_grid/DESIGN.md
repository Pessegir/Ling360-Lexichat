---
name: Futuristic Hex Grid
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#b9cacb'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#849495'
  outline-variant: '#3b494b'
  surface-tint: '#00dbe9'
  primary: '#dbfcff'
  on-primary: '#00363a'
  primary-container: '#00f0ff'
  on-primary-container: '#006970'
  inverse-primary: '#006970'
  secondary: '#ebb2ff'
  on-secondary: '#520072'
  secondary-container: '#b600f8'
  on-secondary-container: '#fff6fc'
  tertiary: '#faf3ff'
  on-tertiary: '#391e70'
  tertiary-container: '#e1d2ff'
  on-tertiary-container: '#6950a2'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#7df4ff'
  primary-fixed-dim: '#00dbe9'
  on-primary-fixed: '#002022'
  on-primary-fixed-variant: '#004f54'
  secondary-fixed: '#f8d8ff'
  secondary-fixed-dim: '#ebb2ff'
  on-secondary-fixed: '#320047'
  on-secondary-fixed-variant: '#74009f'
  tertiary-fixed: '#eaddff'
  tertiary-fixed-dim: '#d1bcff'
  on-tertiary-fixed: '#24005b'
  on-tertiary-fixed-variant: '#503788'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: 0.05em
  body-base:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: 0em
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1.0'
    letterSpacing: 0.15em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  tile-gap: 8px
  panel-padding: 24px
  container-margin: 16px
---

## Brand & Style

This design system establishes a high-fidelity, futuristic atmosphere for a word puzzle experience. The brand personality is intellectually stimulating, sleek, and immersive, targeting users who appreciate cutting-edge aesthetics and digital craftsmanship. 

The visual style merges **Glassmorphism** with **Minimalism**. It relies on deep-space background gradients and translucent "frosted glass" layers to create a sense of infinite depth. The "hive" metaphor is expressed through precise hexagonal geometry, while neon accents provide a rhythmic pulse to the interface. The emotional goal is to make the user feel like they are interacting with a high-end holographic terminal from the near future.

## Colors

The palette is built on a foundation of "Deep Obsidian" and "Midnight Violet." Primary and secondary colors are reserved for high-action states and "neon" illumination.

- **Primary (Neon Cyan):** Used for selected letter tiles, successful word submissions, and primary calls to action.
- **Secondary (Neon Purple):** Used for bonus multipliers, special abilities, and decorative accents.
- **Surface Tones:** Deep blue gradients form the background, while semi-transparent "Glass" layers use a desaturated version of the primary color with low opacity.
- **Contrast:** Text and icons utilize pure white or high-brightness tints of the primary color to ensure legibility against dark, blurred backgrounds.

## Typography

This design system uses **Space Grotesk** for headings and UI labels to reinforce the technical, futuristic aesthetic. Its idiosyncratic letterforms provide the "cutting-edge" personality required for a modern game. **Inter** is utilized for body text and chat boxes to ensure maximum readability during long play sessions. 

All headings should favor a tight tracking or a purposeful wide-spaced uppercase style for labels, creating a contrast between "data-heavy" elements and "playful" geometry.

## Layout & Spacing

The layout follows a **Fixed Grid** logic for the core puzzle arena, utilizing a hexagonal tessellation. For the surrounding UI, a **Fluid Grid** approach is used to ensure the glowing widgets and chat boxes respond to varying screen sizes.

The "Hex-Grid" spacing is the most critical element; tiles must maintain a consistent 8px gap to allow the background neon glow to "bleed" through the negative space. All panels and modals should use generous internal padding to maintain the minimalist, airy feel of the glassmorphic style.

## Elevation & Depth

Hierarchy is achieved through **Glassmorphism** and **Neon Glows** rather than traditional shadows. 

1.  **Base Layer:** Deep gradient background with subtle hexagonal pattern overlays.
2.  **Surface Layer:** Frosted glass panels with a backdrop-blur of 20px-30px and a 1px semi-transparent border (inner glow).
3.  **Active Layer:** Elements currently in use (like a selected hex tile) emit a 15px outer "Neon Blur" in the primary color, suggesting they are floating or energized.
4.  **Overlay Layer:** Modals and tooltips use higher opacity glass with intense border highlights to draw focus.

## Shapes

The dominant shape language is the **Hexagon**. However, to avoid a "dated" look, the design system utilizes **Soft** roundedness (0.25rem - 0.5rem) on the corners of hexagons and panels. This "squircle-hex" approach feels more modern and ergonomic than sharp-edged geometry.

Buttons and input fields should follow a slightly more aggressive rounding for comfort, but always maintaining a hint of the geometric structure found in the main game tiles.

## Components

- **Hexagonal Letter Tiles:** The primary interaction unit. They feature a glassmorphic fill, a thin neon stroke, and a high-contrast character in Space Grotesk. Upon selection, the stroke weight increases and an outer glow is activated.
- **Sleek Panels:** Used for settings and scores. These must have a `backdrop-filter: blur(20px)` and a subtle gradient stroke to simulate a light-refracting glass edge.
- **Glowing Widgets:** Compact data displays (like timer or score) that use monospaced numerals and a constant low-level pulse animation in the secondary color.
- **Transparent Chat Boxes:** Anchored to the side or bottom, these use the highest level of transparency with a simple vertical neon line to denote active focus.
- **Action Buttons:** Pill-shaped or elongated hexagons with a full neon-gradient fill. When hovered, the fill becomes transparent, leaving only the neon border and text.