/**
 * Monochrome line icons.
 *
 * Drawn on a 16-unit grid with a single stroke weight so they sit together as
 * one set, and they inherit `currentColor` so a caller decides meaning through
 * the palette rather than through a coloured glyph. This is what replaced the
 * emoji: an emoji carries someone else's illustration style and renders
 * differently on every platform, which is the opposite of instrument software.
 */

interface IconProps {
  size?: number
  strokeWidth?: number
  style?: React.CSSProperties
}

function Svg({
  size = 16,
  strokeWidth = 1.25,
  style,
  children,
}: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ display: 'block', flexShrink: 0, ...style }}
    >
      {children}
    </svg>
  )
}

/** Vessel architecture: connected pressure volumes. */
export const IconVessel = (p: IconProps) => (
  <Svg {...p}>
    <rect x="1.5" y="4.5" width="5" height="7" rx="1" />
    <rect x="9.5" y="4.5" width="5" height="7" rx="1" />
    <path d="M6.5 8h3" />
  </Svg>
)

/** A charted route through nodes — the product's own visual language. */
export const IconConstellation = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.5 12.5 L6 6.5 L10 9.5 L13.5 3.5" />
    <circle cx="2.5" cy="12.5" r="1.1" />
    <circle cx="6" cy="6.5" r="1.1" />
    <circle cx="10" cy="9.5" r="1.1" />
    <circle cx="13.5" cy="3.5" r="1.1" />
  </Svg>
)

/** Hazard. Used only once an emergency actually exists. */
export const IconHazard = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 1.6 L14.6 13.2 H1.4 Z" />
    <path d="M8 6v3.2" />
    <path d="M8 11.4v.01" />
  </Svg>
)

/** Evidence / provenance: a document with a traced line. */
export const IconEvidence = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3.5 1.8h6l3 3v9.4h-9z" />
    <path d="M9.3 1.8v3.2h3.2" />
    <path d="M5.6 8.4h4.8M5.6 11h3.2" />
  </Svg>
)

/** Futures: diverging trajectories from one decision point. */
export const IconFutures = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="2.6" cy="8" r="1.2" />
    <path d="M3.9 8h2.3" />
    <path d="M6.2 8c3 0 3-4.6 6-4.6" />
    <path d="M6.2 8c3 0 3 4.6 6 4.6" />
    <path d="M6.2 8h6" />
  </Svg>
)

/** Advisory: counsel offered, not imposed. */
export const IconAdvisory = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 1.8a5.2 5.2 0 0 0-3 9.45v1.55a.7.7 0 0 0 .7.7h4.6a.7.7 0 0 0 .7-.7v-1.55A5.2 5.2 0 0 0 8 1.8z" />
    <path d="M6.4 14.2h3.2" />
  </Svg>
)

/** A single module. */
export const IconModule = (p: IconProps) => (
  <Svg {...p}>
    <rect x="2.5" y="3.5" width="11" height="9" rx="1.4" />
    <path d="M2.5 6.4h11" />
  </Svg>
)

/** A pathway between modules. */
export const IconPath = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="3.4" cy="8" r="1.6" />
    <circle cx="12.6" cy="8" r="1.6" />
    <path d="M5 8h6" />
  </Svg>
)

export const IconCrew = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="8" cy="5.4" r="2.4" />
    <path d="M3 13.4a5 5 0 0 1 10 0" />
  </Svg>
)

export const IconSystem = (p: IconProps) => (
  <Svg {...p}>
    <rect x="2.4" y="5.6" width="11.2" height="6.4" rx="1" />
    <path d="M5.2 5.6V3.4M10.8 5.6V3.4M5.6 8.6h4.8" />
  </Svg>
)

export const IconRemove = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.8 4.4h10.4" />
    <path d="M6.4 4.4V2.9h3.2v1.5" />
    <path d="M4.2 4.4l.7 8.4a.9.9 0 0 0 .9.8h4.4a.9.9 0 0 0 .9-.8l.7-8.4" />
  </Svg>
)

export const IconArrowRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2.8 8h10" />
    <path d="M9.2 4.4 12.8 8l-3.6 3.6" />
  </Svg>
)

export const IconPlay = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4.6 2.9 12.6 8l-8 5.1z" />
  </Svg>
)

export const IconPause = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5.6 3.2v9.6M10.4 3.2v9.6" />
  </Svg>
)

export const IconRewind = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 3.4v9.2" />
    <path d="M13 3.6 6.2 8l6.8 4.4z" />
  </Svg>
)

export const IconClose = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4l8 8M12 4l-8 8" />
  </Svg>
)
