import { useState } from "react";
import { api, auth, errorText } from "./api";
import { Field, Notice } from "./ui";

export default function AuthScreen({ onSignedIn }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", role: "farmer", district: "", phone: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = mode === "login" ? { username: form.username, password: form.password } : form;
      const { data } = await api.post(mode === "login" ? "/auth/login/" : "/auth/register/", body);
      auth.save(data.token);
      onSignedIn(data.user);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <section className="auth-card">
        <p className="brand">YIELD-TRADE</p>
        <h1>Sell the harvest. Fill the order.</h1>
        <p className="lede">A marketplace that matches smallholder farmers with buyers by price and by how much of the order they can actually cover.</p>
        <form onSubmit={submit}>
          <Field label="Username"><input value={form.username} onChange={set("username")} autoComplete="username" required /></Field>
          <Field label="Password"><input type="password" value={form.password} onChange={set("password")} autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 8 : undefined} required /></Field>
          {mode === "register" && (
            <>
              <Field label="I am a">
                <select value={form.role} onChange={set("role")}>
                  <option value="farmer">Farmer (selling produce)</option>
                  <option value="buyer">Buyer (looking for produce)</option>
                </select>
              </Field>
              <Field label="District"><input value={form.district} onChange={set("district")} placeholder="e.g. Gwanda" /></Field>
              <Field label="Phone (optional)"><input value={form.phone} onChange={set("phone")} /></Field>
            </>
          )}
          <Notice>{error}</Notice>
          <button className="btn btn-primary" disabled={busy}>{busy ? "Please wait..." : mode === "login" ? "Log in" : "Create account"}</button>
        </form>
        <button className="link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
          {mode === "login" ? "New here? Create an account" : "Have an account? Log in"}
        </button>
      </section>
    </main>
  );
}
