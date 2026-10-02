import { useEffect, useState } from "react";

import { warmUp, type SessionPlan } from "./api/sessions";
import { GenerateForm } from "./screens/GenerateForm";
import { SessionView } from "./screens/SessionView";

export function App() {
  const [plan, setPlan] = useState<SessionPlan | null>(null);

  // The free API sleeps when idle: wake it while the user fills the form in.
  useEffect(() => {
    void warmUp();
  }, []);

  return (
    <div className="app-layout">
      <main>
        <h1>CycleBeat</h1>
        {plan ? (
          <SessionView plan={plan} onRestart={() => setPlan(null)} />
        ) : (
          <GenerateForm onGenerated={setPlan} />
        )}
      </main>
    </div>
  );
}
