import { Info } from "lucide-react";

export function PageHeading({ eyebrow, title, children }) {
  return <header className="page-heading">
    <p className="eyebrow">{eyebrow}</p>
    <h1>{title}</h1>
    <p className="description">{children}</p>
  </header>;
}

export function EmptyState({ icon: Icon = Info, title, children, action }) {
  return <div className="empty-state">
    <span className="icon-tile"><Icon size={26} aria-hidden="true" /></span>
    <h2>{title}</h2>
    <div className="muted">{children}</div>
    {action}
  </div>;
}
