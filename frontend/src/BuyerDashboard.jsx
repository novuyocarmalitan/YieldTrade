import { useState } from "react";
import { api, errorText, unwrap } from "./api";
import Orders from "./Orders";
import { Bar, Empty, Field, Notice, Status } from "./ui";
import { inDays, kg, money, useFetch } from "./helpers";

const blankRequest = (district) => ({ crop: "", quantity_kg: "", max_price_per_kg: "", district, needed_by: inDays(14) });

function PostRequest({ crops, district, onDone }) {
  const [f, setF] = useState(() => blankRequest(district));
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/requests/", f);
      setF(blankRequest(district));
      onDone();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form className="card form-grid" onSubmit={submit}>
      <h2>Post what you need</h2>
      <Field label="Crop">
        <select value={f.crop} onChange={set("crop")} required>
          <option value="">Choose...</option>
          {crops.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </Field>
      <Field label="Quantity needed (kg)"><input type="number" min="1" step="any" value={f.quantity_kg} onChange={set("quantity_kg")} required /></Field>
      <Field label="Most you will pay ($ per kg)"><input type="number" min="0.01" step="0.01" value={f.max_price_per_kg} onChange={set("max_price_per_kg")} required /></Field>
      <Field label="District"><input value={f.district} onChange={set("district")} /></Field>
      <Field label="Needed by"><input type="date" value={f.needed_by} onChange={set("needed_by")} required /></Field>
      <Notice>{error}</Notice>
      <button className="btn btn-primary">Post request</button>
    </form>
  );
}

function PlanCard({ title, blurb, plan, onOrder, busy }) {
  const covered = plan.lines.length > 0;
  return (
    <div className="plan">
      <h4>{title}</h4>
      <p className="muted">{blurb}</p>
      {covered ? (
        <>
          <p><strong>{plan.covered_pct}%</strong> covered from {plan.sellers} seller{plan.sellers === 1 ? "" : "s"}</p>
          <p>Average {money(plan.avg_price_per_kg)}/kg, total <strong>{money(plan.total_cost)}</strong>{Number(plan.shortfall_kg) > 0 && <>, short by {kg(plan.shortfall_kg)}</>}</p>
          <button className="btn btn-primary" onClick={onOrder} disabled={busy}>{busy ? "Ordering..." : "Order this plan"}</button>
        </>
      ) : (
        <p className="muted">Nothing to plan yet.</p>
      )}
    </div>
  );
}

function Matches({ request, onOrdered }) {
  const { data, error, loading, reload } = useFetch(() => api.get(`/requests/${request.id}/matches/`).then((r) => r.data), [request.id, request.ordered_kg]);
  const [qty, setQty] = useState({});
  const [msg, setMsg] = useState({ kind: "error", text: "" });
  const [busy, setBusy] = useState("");

  const remaining = Math.max(0, Number(request.quantity_kg) - Number(request.ordered_kg));

  async function order(listing, amount, tag) {
    setBusy(tag);
    setMsg({ kind: "error", text: "" });
    try {
      await api.post("/orders/", { listing: listing.id, quantity_kg: amount, request: request.id });
      return true;
    } catch (e) {
      setMsg({ kind: "error", text: `${listing.farmer_name}: ${errorText(e)}` });
      return false;
    } finally {
      setBusy("");
    }
  }

  async function orderOne(m) {
    const amount = qty[m.listing.id] ?? Math.min(Number(m.listing.quantity_kg), remaining || Number(m.listing.quantity_kg));
    if (await order(m.listing, amount, `l${m.listing.id}`)) {
      setMsg({ kind: "ok", text: `Order sent to ${m.listing.farmer_name}.` });
      reload();
      onOrdered();
    }
  }

  async function orderPlan(plan, tag) {
    setBusy(tag);
    let done = 0;
    for (const line of plan.lines) {
      const listing = data.matches.find((m) => m.listing.id === line.listing)?.listing;
      if (!listing) continue;
      if (!(await order(listing, line.take_kg, tag))) break;
      done += 1;
    }
    setBusy("");
    if (done) setMsg({ kind: "ok", text: `${done} order${done === 1 ? "" : "s"} sent.` });
    reload();
    onOrdered();
  }

  if (loading) return <p className="muted">Finding sellers...</p>;
  if (error) return <Notice>{errorText(error)}</Notice>;
  if (!data.matches.length) return <Empty>No open listings fit this request yet. Sellers priced more than 25% over your maximum are not shown.</Empty>;

  return (
    <div className="stack tight">
      <p className="muted">Each seller is scored out of 100: <strong>40%</strong> how well their price fits your budget, <strong>60%</strong> how much of your order they can cover.</p>
      <div className="plans">
        <PlanCard title="Best match first" blurb="Fewest sellers and the most complete order." plan={data.plan} busy={busy === "plan"} onOrder={() => orderPlan(data.plan, "plan")} />
        <PlanCard title="Lowest cost" blurb="Cheapest sellers first. May mean more of them." plan={data.cheapest_plan} busy={busy === "cheap"} onOrder={() => orderPlan(data.cheapest_plan, "cheap")} />
      </div>
      <Notice kind={msg.kind === "ok" ? "ok" : "error"}>{msg.text}</Notice>
      {data.matches.map((m, i) => (
        <div key={m.listing.id} className="match">
          <div className="score"><strong>{Math.round(m.score)}</strong><span>#{i + 1}</span></div>
          <div className="grow">
            <h4>{m.listing.farmer_name}: {kg(m.listing.quantity_kg)} at {money(m.listing.price_per_kg)}/kg</h4>
            <p className="muted">{m.listing.district || "District not given"}, available from {m.listing.available_from}</p>
            <Bar label="Price fit" weight="40%" value={m.price_score} />
            <Bar label="Volume covered" weight="60%" value={m.volume_score} />
            <div className="order-row">
              <input aria-label="Kilograms to order" type="number" min="1" max={m.listing.quantity_kg} step="any"
                value={qty[m.listing.id] ?? Math.min(Number(m.listing.quantity_kg), remaining || Number(m.listing.quantity_kg))}
                onChange={(e) => setQty({ ...qty, [m.listing.id]: e.target.value })} />
              <span className="muted">kg</span>
              <button className="btn" disabled={busy === `l${m.listing.id}`} onClick={() => orderOne(m)}>Order</button>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function Requests({ reloadKey, onOrdered }) {
  const { data, error, loading, reload } = useFetch(() => api.get("/requests/?mine=1").then(unwrap), [reloadKey]);
  const [open, setOpen] = useState(null);
  const [msg, setMsg] = useState("");

  async function cancel(id) {
    setMsg("");
    try {
      await api.delete(`/requests/${id}/`);
      reload();
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  if (loading) return <p className="muted">Loading your requests...</p>;
  if (error) return <Notice>{errorText(error)}</Notice>;
  if (!data.length) return <Empty>You have not posted a request yet.</Empty>;
  return (
    <div className="stack">
      <Notice>{msg}</Notice>
      {data.map((r) => (
        <article key={r.id} className="card">
          <div className="row">
            <div className="grow">
              <h3>{kg(r.quantity_kg)} of {r.crop_name} <Status value={r.status} /></h3>
              <p className="muted">Up to {money(r.max_price_per_kg)}/kg, by {r.needed_by}. Ordered so far: {kg(r.ordered_kg)}</p>
            </div>
            <div className="actions">
              {r.status === "open" && <button className="btn btn-primary" onClick={() => setOpen(open === r.id ? null : r.id)}>{open === r.id ? "Hide sellers" : "Find sellers"}</button>}
              {r.status !== "cancelled" && <button className="btn" onClick={() => cancel(r.id)}>Cancel</button>}
            </div>
          </div>
          {open === r.id && <Matches request={r} onOrdered={() => { reload(); onOrdered(); }} />}
        </article>
      ))}
    </div>
  );
}

function Market() {
  const [crop, setCrop] = useState("");
  const { data: crops } = useFetch(() => api.get("/crops/").then(unwrap), []);
  const { data, error, loading } = useFetch(() => api.get(`/listings/?status=open${crop ? `&crop=${crop}` : ""}`).then(unwrap), [crop]);
  return (
    <div className="stack">
      <Field label="Filter by crop">
        <select value={crop} onChange={(e) => setCrop(e.target.value)}>
          <option value="">All crops</option>
          {crops?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </Field>
      {loading && <p className="muted">Loading...</p>}
      {error && <Notice>{errorText(error)}</Notice>}
      {data && !data.length && <Empty>Nothing for sale here right now.</Empty>}
      {data?.map((l) => (
        <article key={l.id} className="card">
          <h3>{l.crop_name}</h3>
          <p className="muted">{kg(l.quantity_kg)} at {money(l.price_per_kg)}/kg from {l.farmer_name}{l.district ? `, ${l.district}` : ""}</p>
        </article>
      ))}
    </div>
  );
}

export default function BuyerDashboard({ user }) {
  const [tab, setTab] = useState("requests");
  const [key, setKey] = useState(0);
  const { data: crops } = useFetch(() => api.get("/crops/").then(unwrap), []);
  const bump = () => setKey((k) => k + 1);
  return (
    <>
      <nav className="tabs">
        <button className={tab === "requests" ? "on" : ""} onClick={() => setTab("requests")}>My requests</button>
        <button className={tab === "orders" ? "on" : ""} onClick={() => setTab("orders")}>Orders</button>
        <button className={tab === "market" ? "on" : ""} onClick={() => setTab("market")}>Browse market</button>
      </nav>
      {tab === "requests" && (
        <div className="stack">
          {crops && <PostRequest crops={crops} district={user.district} onDone={bump} />}
          <h2>Your requests</h2>
          <Requests reloadKey={key} onOrdered={bump} />
        </div>
      )}
      {tab === "orders" && <Orders key={key} role="buyer" onChange={bump} />}
      {tab === "market" && <Market />}
    </>
  );
}
