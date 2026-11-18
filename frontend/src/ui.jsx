export function Notice({ kind = "error", children }) {
  if (!children) return null;
  return <div className={`notice notice-${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

export function Status({ value }) {
  return <span className={`badge badge-${value}`}>{value}</span>;
}

export function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function Bar({ label, weight, value }) {
  return (
    <div className="bar">
      <div className="bar-head">
        <span>{label}</span>
        <span className="muted">{weight} weight, {Math.round(value)}%</span>
      </div>
      <div className="bar-track"><div className="bar-fill" style={{ width: `${Math.min(100, value)}%` }} /></div>
    </div>
  );
}

export function Empty({ children }) {
  return <p className="empty">{children}</p>;
}
