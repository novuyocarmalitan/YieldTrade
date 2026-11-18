import { useState } from "react";
import { api, errorText, unwrap } from "./api";
import { Empty, Notice, Status } from "./ui";
import { kg, money, useFetch } from "./helpers";

export default function Orders({ role, onChange }) {
  const { data, error, loading, reload } = useFetch(() => api.get("/orders/").then(unwrap), []);
  const [msg, setMsg] = useState("");

  async function act(id, verb) {
    setMsg("");
    try {
      await api.post(`/orders/${id}/${verb}/`);
      reload();
      onChange?.();
    } catch (e) {
      setMsg(errorText(e));
    }
  }

  if (loading) return <p className="muted">Loading orders...</p>;
  if (error) return <Notice>{errorText(error)}</Notice>;
  if (!data.length) return <Empty>No orders yet.</Empty>;

  return (
    <div className="stack">
      <Notice>{msg}</Notice>
      {data.map((o) => (
        <article key={o.id} className="card row">
          <div className="grow">
            <h3>{kg(o.quantity_kg)} of {o.crop_name} <Status value={o.status} /></h3>
            <p className="muted">
              {role === "farmer" ? `Buyer: ${o.buyer_name}` : `Seller: ${o.farmer_name}`}
              {o.district ? `, ${o.district}` : ""} | {money(o.price_per_kg)}/kg | Total <strong>{money(o.total)}</strong>
            </p>
          </div>
          <div className="actions">
            {role === "farmer" && o.status === "pending" && (
              <>
                <button className="btn btn-primary" onClick={() => act(o.id, "accept")}>Accept</button>
                <button className="btn" onClick={() => act(o.id, "reject")}>Reject</button>
              </>
            )}
            {role === "farmer" && o.status === "accepted" && (
              <button className="btn btn-primary" onClick={() => act(o.id, "complete")}>Mark delivered</button>
            )}
            {role === "buyer" && o.status === "pending" && (
              <button className="btn" onClick={() => act(o.id, "cancel")}>Cancel</button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}
