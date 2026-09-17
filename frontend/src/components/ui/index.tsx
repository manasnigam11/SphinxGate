import React from "react";

// ─── Badge ───────────────────────────────────────────────────────────────────

type BadgeVariant = "default" | "success" | "warning" | "error" | "info" | "muted";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  dot?: boolean;
  className?: string;
}

const badgeStyles: Record<BadgeVariant, string> = {
  default: "bg-[var(--muted)] text-[var(--secondary-foreground)]",
  success: "bg-[var(--success-subtle)] text-[var(--success)]",
  warning: "bg-[var(--warning-subtle)] text-[var(--warning)]",
  error:   "bg-[var(--error-subtle)] text-[var(--error)]",
  info:    "bg-[var(--info-subtle)] text-[var(--info)]",
  muted:   "bg-[var(--muted)] text-[var(--muted-foreground)]",
};

export function Badge({ children, variant = "default", dot, className = "" }: BadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium ${badgeStyles[variant]} ${className}`}>
      {dot && (
        <span className={`w-1.5 h-1.5 rounded-full ${
          variant === "success" ? "bg-green-500 animate-pulse-dot" :
          variant === "warning" ? "bg-amber-500 animate-pulse-dot" :
          variant === "error" ? "bg-red-500 animate-pulse-dot" :
          variant === "info" ? "bg-blue-500" : "bg-current"
        }`} />
      )}
      {children}
    </span>
  );
}

// ─── Button ───────────────────────────────────────────────────────────────────

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type ButtonSize = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: React.ReactNode;
  loading?: boolean;
}

const btnVariant: Record<ButtonVariant, string> = {
  primary:   "bg-[var(--primary)] text-[var(--primary-foreground)] hover:opacity-90 focus:ring-2 focus:ring-[var(--ring)] focus:ring-offset-2 focus:ring-offset-[var(--background)]",
  secondary: "bg-[var(--secondary)] text-[var(--foreground)] hover:bg-[var(--muted)] border border-[var(--border)]",
  ghost:     "text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--secondary)]",
  danger:    "bg-[var(--error-subtle)] text-[var(--error)] hover:opacity-90 border border-[var(--error)]/20",
  outline:   "border border-[var(--border)] text-[var(--foreground)] hover:bg-[var(--secondary)]",
};

const btnSize: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs gap-1.5",
  md: "px-3.5 py-2 text-sm gap-2",
  lg: "px-4 py-2.5 text-sm gap-2",
};

export function Button({ variant = "secondary", size = "md", children, loading, className = "", disabled, ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center font-medium rounded-[var(--radius)] transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${btnVariant[variant]} ${btnSize[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <svg className="animate-spin w-3.5 h-3.5" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>}
      {children}
    </button>
  );
}

// ─── Card ─────────────────────────────────────────────────────────────────────

interface CardProps {
  children: React.ReactNode;
  className?: string;
  onClick?: () => void;
  hover?: boolean;
}

export function Card({ children, className = "", onClick, hover }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`bg-[var(--card)] border border-[var(--border)] rounded-[var(--radius-lg)] ${hover ? "hover:border-[var(--accent)]/30 cursor-pointer transition-colors" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

// ─── Input ────────────────────────────────────────────────────────────────────

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ReactNode;
  label?: string;
}

export function Input({ icon, label, className = "", ...props }: InputProps) {
  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && <label className="text-xs font-medium text-[var(--muted-foreground)]">{label}</label>}
      <div className="relative flex items-center">
        {icon && <span className="absolute left-3 text-[var(--muted-foreground)] flex items-center">{icon}</span>}
        <input
          className={`w-full bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--ring)] transition-colors ${icon ? "pl-9" : ""} ${className}`}
          {...props}
        />
      </div>
    </div>
  );
}

// ─── Select ───────────────────────────────────────────────────────────────────

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  options: { value: string; label: string }[];
}

export function Select({ label, options, className = "", ...props }: SelectProps) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && <label className="text-xs font-medium text-[var(--muted-foreground)]">{label}</label>}
      <select
        className={`bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] px-3 py-2 text-sm text-[var(--foreground)] focus:outline-none focus:border-[var(--accent)] cursor-pointer ${className}`}
        {...props}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

// ─── Tabs ─────────────────────────────────────────────────────────────────────

interface TabsProps {
  tabs: string[];
  active: string;
  onChange: (tab: string) => void;
  className?: string;
}

export function Tabs({ tabs, active, onChange, className = "" }: TabsProps) {
  return (
    <div className={`flex items-center gap-1 border-b border-[var(--border)] ${className}`}>
      {tabs.map(tab => (
        <button
          key={tab}
          onClick={() => onChange(tab)}
          className={`px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px cursor-pointer ${
            active === tab
              ? "border-[var(--accent)] text-[var(--accent)]"
              : "border-transparent text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          }`}
        >
          {tab}
        </button>
      ))}
    </div>
  );
}

// ─── StatusIndicator ─────────────────────────────────────────────────────────

type StatusType = "healthy" | "degraded" | "down" | "closed" | "half-open" | "open";

export function StatusIndicator({ status, size = "sm" }: { status: StatusType; size?: "sm" | "md" }) {
  const colors: Record<StatusType, string> = {
    healthy: "bg-green-500",
    closed: "bg-green-500",
    degraded: "bg-amber-500",
    "half-open": "bg-amber-500",
    down: "bg-red-500",
    open: "bg-red-500",
  };
  const pulse = status === "down" || status === "open" || status === "degraded" || status === "half-open";
  const sz = size === "sm" ? "w-2 h-2" : "w-2.5 h-2.5";
  return (
    <span className={`inline-block ${sz} rounded-full ${colors[status]} ${pulse ? "animate-pulse-dot" : ""}`} />
  );
}

// ─── Tooltip ─────────────────────────────────────────────────────────────────

export function Tooltip({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="relative group">
      {children}
      <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2 py-1 bg-[var(--foreground)] text-[var(--background)] text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-50">
        {label}
      </div>
    </div>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`bg-[var(--muted)] rounded animate-pulse ${className}`} />;
}

// ─── Empty State ──────────────────────────────────────────────────────────────

export function EmptyState({ icon, title, description, action }: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
      {icon && <div className="text-[var(--muted-foreground)] mb-1">{icon}</div>}
      <p className="text-sm font-medium text-[var(--foreground)]">{title}</p>
      {description && <p className="text-xs text-[var(--muted-foreground)] max-w-xs">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

// ─── Code Block ──────────────────────────────────────────────────────────────

export function CodeBlock({ children, className = "" }: { children: string; className?: string }) {
  return (
    <pre className={`mono text-xs bg-[var(--secondary)] border border-[var(--border)] rounded-[var(--radius)] p-4 overflow-auto leading-relaxed text-[var(--foreground)] ${className}`}>
      {children}
    </pre>
  );
}

// ─── Divider ─────────────────────────────────────────────────────────────────

export function Divider({ className = "" }: { className?: string }) {
  return <div className={`border-t border-[var(--border)] ${className}`} />;
}

// ─── Section Header ───────────────────────────────────────────────────────────

export function SectionHeader({ title, description, actions }: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--foreground)]">{title}</h1>
        {description && <p className="text-sm text-[var(--muted-foreground)] mt-1">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </div>
  );
}

// ─── Toggle ──────────────────────────────────────────────────────────────────

export function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex w-9 h-5 rounded-full transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:ring-offset-1 focus:ring-offset-[var(--background)] ${checked ? "bg-[var(--accent)]" : "bg-[var(--muted)]"}`}
    >
      <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
    </button>
  );
}
