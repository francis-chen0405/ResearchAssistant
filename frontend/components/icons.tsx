import type { SVGProps } from "react";

// Small, stroke-based icon set. Icons are decorative unless a label is given;
// meaning is always carried by adjacent text as well.
const paths = {
  check: "M4 10.5l4 4 8-9",
  x: "M5 5l10 10M15 5L5 15",
  arrowRight: "M4 10h12M11 5l5 5-5 5",
  arrowLeft: "M16 10H4M9 5l-5 5 5 5",
  external: "M11 4h5v5M16 4l-7 7M14 11v4a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h4",
  plus: "M10 4v12M4 10h12",
  minus: "M4 10h12",
  info: "M10 9v5M10 6.5v.01M10 2.5a7.5 7.5 0 100 15 7.5 7.5 0 000-15z",
  alert: "M10 7v4M10 13.5v.01M8.7 3.2L2.4 14.5A1.5 1.5 0 003.7 16.7h12.6a1.5 1.5 0 001.3-2.2L11.3 3.2a1.5 1.5 0 00-2.6 0z",
  search: "M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM13 13l4 4",
  chevronDown: "M5 8l5 5 5-5",
  chevronRight: "M8 5l5 5-5 5",
  clock: "M10 6v4l2.5 2.5M10 2.5a7.5 7.5 0 100 15 7.5 7.5 0 000-15z",
  history: "M3 10a7 7 0 107-7 7 7 0 00-5.6 2.8M3 3v3.5h3.5M10 6.5V10l2.5 1.5",
  settings: "M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5zM16 10a6 6 0 00-.1-1l1.6-1.3-1.5-2.6-2 .7a6 6 0 00-1.7-1L12 2.8H9l-.4 2a6 6 0 00-1.7 1l-2-.7-1.5 2.6L5 9a6 6 0 000 2l-1.6 1.3 1.5 2.6 2-.7a6 6 0 001.7 1l.4 2h3l.4-2a6 6 0 001.7-1l2 .7 1.5-2.6L15.9 11a6 6 0 00.1-1z",
  doc: "M6 2.5h5.5L15 6v11a.5.5 0 01-.5.5h-8.5A.5.5 0 015.5 17V3a.5.5 0 01.5-.5zM11 2.5V6.5h4M8 10h5M8 13h5",
  copy: "M7 7h9v9H7zM4 13V4h9",
  download: "M10 3v10M6 9l4 4 4-4M4 16h12",
  stop: "M6 6h8v8H6z",
  sun: "M10 13.5a3.5 3.5 0 100-7 3.5 3.5 0 000 7zM10 2v1.5M10 16.5V18M2 10h1.5M16.5 10H18M4.3 4.3l1 1M14.7 14.7l1 1M4.3 15.7l1-1M14.7 5.3l1-1",
  moon: "M16 12.5A6.5 6.5 0 017.5 4a6.5 6.5 0 108.5 8.5z",
  circle: "M10 3a7 7 0 100 14 7 7 0 000-14z",
  dot: "M10 8a2 2 0 100 4 2 2 0 000-4z",
  refresh: "M16 10a6 6 0 11-1.8-4.3M16 3.5V7h-3.5",
  key: "M12.5 3a4.5 4.5 0 00-4.3 5.9L3 14.1V17h2.9v-1.5h1.6V14h1.5l1.1-1.1A4.5 4.5 0 1012.5 3zM13.5 6.5v.01",
} as const;

export type IconName = keyof typeof paths;

export function Icon({
  name,
  size = 16,
  label,
  ...props
}: { name: IconName; size?: number; label?: string } & SVGProps<SVGSVGElement>) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
      focusable="false"
      className="icon"
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}
