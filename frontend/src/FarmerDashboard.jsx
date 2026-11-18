import { useState } from "react";
import { api, errorText, unwrap } from "./api";
import Orders from "./Orders";
import { Bar, Empty, Field, Notice, Status } from "./ui";
import { kg, money, today, useFetch } from "./helpers";

const blankListing = (district) => ({ crop: "", quantity_kg: "", price_per_kg: "", district, available_from: today() });

function PostProduce({ crops, district, onDone }) {
  const [f, setF] = useState(() => blankListing(district));
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/listings/", f);
      setF(blankListing(district));
      onDone();
    } catch (err) {
      setError(errorText(err));
    }
  }

  return (
    <form className="card form-grid" onSubmit={submit}>
      <h2>Post produce for sale</h2>
      <Field label="Crop">
        <select value={f.crop} onChange={set("crop")} required>
          <option value="">Choose...</option>
          {crops.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </Field>
      <Field label="Quantity (kg)"><input type="number" min="1" step="any" value={f.quantity_kg} onChange={set("quantity_kg")} required /></Field>
      <Field label="Asking price ($ per kg)"><input type="number" min="0.01" step="0.01" value={f.price_per_kg} onChange={set("price_per_kg")} required /></Field>
      <Field label="District"><input value={f.district} onChange={set("district")} /></Field>
      <Field label="Available from"><input type="date" value={f.available_from} onChange={set("available_from")} required /></Field>
      <Notice>{error}</Notice>
      <button className="btn btn-primary">Post listing</button>
    </form>
  );
}

function WhoWantsThis({ listing }) {
  const { data, error, loading } = useFetch(() => api.get(`/listings/${listing.id}/matches/`).then((r) => r.data), [listing.id, listing.quantity_kg]);
  if (loading) return <p className="muted">Finding buyers...</p>;
  if (error) return <Notice>{errorText(error)}</Notice>;
  if (!data.matches.length) return <Empty>No open buy requests fit this listing yet. Check back soon.</Empty>;
  return (
    <div className="stack tight">
      {data.matches.map((m) => (
        <div key={m.request.id} className="match">
          <div className="score"><strong>{Math.round(m.score)}</strong><span>match</span></div>
          <div className="grow">
            <h4>{m.request.buyer_name} wants {kg(m.request.quantity_kg)}</h4>
            <p className="muted">Will pay up to {money(m.request.max_price_per_kg)}/kg{m.request.district ? `, ${m.request.district}` : ""}, needed by {m.request.needed_by}</p>
            <Bar label="Price fit" weight="40%" value={m.price_score} />
            <Bar label="How much of their order you cover" weight="60%" value={m.volume_score} />
          </div>
        </div>
      ))}
    </div>
  );
}

function Listings({ reloadKey }) {
  const { data, error, loading, reload } = useFetch(() => api.get("/listings/?mine=1").then(unwrap), [reloadKey]);
  const [open, setOpen] = useState(null);
  const [msg, setMsg] = useState("");

  async function close(id) {
    setMsg("");
    try {
      await api.patch(`/listings/${id}/`, { status: "closed" });
      reload();
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  if (loading) return <p className="muted">Loading your listings...</p>;
  if (error) return <Notice>{errorText(error)}</Notice>;
  if (!data.length) return <Empty>You have not posted any produce yet.</Empty>;
  return (
    <div className="stack">
      <Notice>{msg}</Notice>
      {data.map((l) => (
        <article key={l.id} className="card">
          <div className="row">
            <div className="grow">
              <h3>{l.crop_name} <Status value={l.status} /></h3>
              <p className="muted">{kg(l.quantity_kg)} remaining at {money(l.price_per_kg)}/kg{l.district ? `, ${l.district}` : ""}</p>
            </div>
            <div className="actions">
              <button className="btn" onClick={() => setOpen(open === l.id ? null : l.id)}>{open === l.id ? "Hide buyers" : "Who wants this?"}</button>
              {l.status === "open" && <button className="btn" onClick={() => close(l.id)}>Close</button>}
            </div>
          </div>
          {open === l.id && <WhoWantsThis listing={l} />}
        </article>
      ))}
    </div>
  );
}

export default function FarmerDashboard({ user }) {
  const [tab, setTab] = useState("produce");
  const [key, setKey] = useState(0);
  const { data: crops } = useFetch(() => api.get("/crops/").then(unwrap), []);
  return (
    <>
      <nav className="tabs">
        <button className={tab === "produce" ? "on" : ""} onClick={() => setTab("produce")}>My produce</button>
        <button className={tab === "orders" ? "on" : ""} onClick={() => setTab("orders")}>Orders</button>
      </nav>
      {tab === "produce" && (
        <div className="stack">
          {crops && <PostProduce crops={crops} district={user.district} onDone={() => setKey((k) => k + 1)} />}
          <h2>Your listings</h2>
          <Listings reloadKey={key} />
        </div>
      )}
      {tab === "orders" && <Orders role="farmer" onChange={() => setKey((k) => k + 1)} />}
    </>
  );
}
