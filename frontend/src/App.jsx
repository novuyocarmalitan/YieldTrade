import { useEffect, useState } from "react";
import { api, auth } from "./api";
import AuthScreen from "./AuthScreen";
import BuyerDashboard from "./BuyerDashboard";
import FarmerDashboard from "./FarmerDashboard";
import "./App.css";

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(auth.has());

  useEffect(() => {
    if (!auth.has()) return;
    api.get("/auth/me/")
      .then((r) => setUser(r.data))
      .catch(() => auth.clear())
      .finally(() => setChecking(false));
  }, []);

  function logout() {
    auth.clear();
    setUser(null);
  }

  if (checking) return <p className="boot">Loading...</p>;
  if (!user) return <AuthScreen onSignedIn={setUser} />;

  return (
    <div className="shell">
      <header className="top">
        <span className="brand">YIELD-TRADE</span>
        <span className="who">{user.username} <em>{user.role}</em></span>
        <button className="link" onClick={logout}>Log out</button>
      </header>
      <main className="page">
        {user.role === "farmer" ? <FarmerDashboard user={user} /> : <BuyerDashboard user={user} />}
      </main>
    </div>
  );
}
