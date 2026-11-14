"use client";

import {
  type ButtonHTMLAttributes,
  type KeyboardEvent,
  type ReactNode,
  type SelectHTMLAttributes,
  useId,
  useRef,
} from "react";
import { Icon, type IconName } from "./icons";

export type Tone = "neutral" | "support" | "challenge" | "context" | "warning" | "error" | "info" | "success";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  iconAfter,
  className = "",
  children,
  type = "button",
  ...props
}: {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  icon?: IconName;
  iconAfter?: IconName;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={`btn btn-${variant} btn-${size} ${className}`.trim()}
      {...props}
    >
      {icon && <Icon name={icon} />}
      {children}
      {iconAfter && <Icon name={iconAfter} />}
    </button>
  );
}

export function Chip({
  tone = "neutral",
  icon,
  children,
  className = "",
}: {
  tone?: Tone;
  icon?: IconName;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`chip chip-${tone} ${className}`.trim()}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  );
}

export function Card({
  as: Tag = "section",
  className = "",
  children,
  ...props
}: {
  as?: "section" | "article" | "div" | "li" | "aside";
  className?: string;
  children: ReactNode;
} & Record<string, unknown>) {
  return (
    <Tag className={`card ${className}`.trim()} {...props}>
      {children}
    </Tag>
  );
}

export type TabItem<T extends string> = { id: T; label: string; count?: number };

/** WAI-ARIA tabs with roving focus; panels are rendered by the caller. */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  idPrefix,
}: {
  tabs: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  idPrefix: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = tabs.length - 1;
    const next =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
        : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
          : event.key === "Home" ? 0
            : event.key === "End" ? last
              : null;
    if (next === null) return;
    event.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((tab, index) => (
        <button
          key={tab.id}
          ref={(node) => {
            refs.current[tab.id] = node;
          }}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${tab.id}`}
          aria-controls={`${idPrefix}-panel-${tab.id}`}
          aria-selected={value === tab.id}
          tabIndex={value === tab.id ? 0 : -1}
          className="tab"
          onClick={() => onChange(tab.id)}
          onKeyDown={(event) => onKey(event, index)}
        >
          {tab.label}
          {tab.count != null && <span className="tab-count">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function TabPanel({
  idPrefix,
  id,
  active,
  children,
}: {
  idPrefix: string;
  id: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-tab-${id}`}
      hidden={!active}
      tabIndex={0}
      className="tab-panel"
    >
      {active && children}
    </div>
  );
}

export function Disclosure({
  summary,
  children,
  className = "",
  id,
  open,
  onToggle,
}: {
  summary: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
  open?: boolean;
  onToggle?: (open: boolean) => void;
}) {
  return (
    <details
      className={`disclosure ${className}`.trim()}
      id={id}
      open={open}
      onToggle={onToggle ? (event) => onToggle(event.currentTarget.open) : undefined}
    >
      <summary>
        <Icon name="chevronRight" className="icon disclosure-chevron" />
        <span className="disclosure-summary">{summary}</span>
      </summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}

export function Select({
  label,
  hint,
  className = "",
  id,
  children,
  ...props
}: {
  label: ReactNode;
  hint?: ReactNode;
} & SelectHTMLAttributes<HTMLSelectElement>) {
  const generated = useId();
  const selectId = id ?? generated;
  return (
    <div className={`field ${className}`.trim()}>
      <label htmlFor={selectId}>{label}</label>
      <div className="select">
        <select id={selectId} aria-describedby={hint ? `${selectId}-hint` : undefined} {...props}>
          {children}
        </select>
        <Icon name="chevronDown" />
      </div>
      {hint && <small className="field-hint" id={`${selectId}-hint`}>{hint}</small>}
    </div>
  );
}

/** A labelled switch whose off state is visually distinct (hollow knob, "Off" text). */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
  describedBy,
  hideLabel = false,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  description?: ReactNode;
  disabled?: boolean;
  describedBy?: string;
  hideLabel?: boolean;
}) {
  const id = useId();
  return (
    <div className={`switch-row ${disabled ? "is-disabled" : ""}`}>
      {!hideLabel && (
        <span className="switch-copy">
          <span className="switch-label" id={`${id}-label`}>{label}</span>
          {description && <small id={`${id}-desc`}>{description}</small>}
        </span>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        aria-describedby={describedBy ?? (description && !hideLabel ? `${id}-desc` : undefined)}
        className={`switch ${checked ? "on" : ""}`}
        disabled={disabled}
        onClick={() => onChange(!checked)}
      >
        <span className="switch-track" aria-hidden="true"><i /></span>
        <span className="switch-state" aria-hidden="true">{checked ? "On" : "Off"}</span>
      </button>
    </div>
  );
}

const bannerIcons: Record<Tone, IconName> = {
  neutral: "info", info: "info", success: "check", support: "check", challenge: "info",
  context: "info", warning: "alert", error: "alert",
};

export function Banner({
  tone = "info",
  title,
  children,
  action,
  role,
  className = "",
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  role?: "status" | "alert";
  className?: string;
}) {
  return (
    <div className={`banner banner-${tone} ${className}`.trim()} role={role}>
      <Icon name={bannerIcons[tone]} size={18} />
      <div className="banner-body">
        {title && <strong>{title}</strong>}
        {children}
      </div>
      {action && <div className="banner-action">{action}</div>}
    </div>
  );
}

export function EmptyState({
  icon = "doc",
  title,
  children,
  action,
}: {
  icon?: IconName;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon"><Icon name={icon} size={22} /></span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Skeleton({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`skeleton ${className}`.trim()} aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => <i key={index} />)}
    </div>
  );
}

/** Proportional bar; each segment carries its label so colour is never the only cue. */
export function SegmentBar({
  segments,
  label,
}: {
  segments: { tone: Tone; value: number; label: string }[];
  label: string;
}) {
  const total = segments.reduce((sum, item) => sum + item.value, 0);
  return (
    <div className="segment-bar" role="img" aria-label={label}>
      {total > 0 && segments.filter((item) => item.value > 0).map((item) => (
        <i
          key={item.label}
          className={`seg-${item.tone}`}
          style={{ flexGrow: item.value }}
          title={`${item.label}: ${item.value}`}
        />
      ))}
    </div>
  );
}

export function Meter({ value, max, label }: { value: number; max: number; label: string }) {
  const ratio = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  return (
    <div
      className={`meter ${ratio >= 0.9 ? "meter-high" : ""}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-label={label}
    >
      <i style={{ width: `${ratio * 100}%` }} />
    </div>
  );
}
