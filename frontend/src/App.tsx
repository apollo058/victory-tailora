import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Check, LayoutGrid, Plus, Sparkles } from "lucide-react";

type Module = {
  id: string;
  name: string;
  description: string;
  accent: "violet" | "blue" | "orange" | "green";
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

const fallbackModules: Module[] = [
  { id: "focus", name: "Focus", description: "A compact view of your most important work.", accent: "violet" },
  { id: "tasks", name: "Tasks", description: "Keep the next actions that move your day forward.", accent: "blue" },
  { id: "calendar", name: "Calendar", description: "See the commitments that shape your week.", accent: "orange" },
  { id: "insights", name: "Insights", description: "Turn activity into lightweight progress signals.", accent: "green" },
];

function App() {
  const [modules, setModules] = useState<Module[]>(fallbackModules);
  const [selectedIds, setSelectedIds] = useState<string[]>(["focus", "tasks", "calendar"]);
  const [status, setStatus] = useState("Ready to personalize");

  useEffect(() => {
    fetch(`${API_BASE_URL}/modules`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error("API unavailable"))))
      .then((data: Module[]) => setModules(data))
      .catch(() => setStatus("Using local preview data"));
  }, []);

  const selectedModules = useMemo(
    () => selectedIds.map((id) => modules.find((module) => module.id === id)).filter(Boolean) as Module[],
    [modules, selectedIds],
  );

  function toggleModule(id: string) {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((moduleId) => moduleId !== id) : [...current, id],
    );
    setStatus("Workspace changed");
  }

  function moveModule(index: number, direction: -1 | 1) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= selectedIds.length) return;
    const next = [...selectedIds];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    setSelectedIds(next);
    setStatus("Layout reordered");
  }

  async function saveLayout() {
    try {
      const response = await fetch(`${API_BASE_URL}/layouts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "My first workspace", module_ids: selectedIds }),
      });
      if (!response.ok) throw new Error("Could not save");
      setStatus("Workspace saved");
    } catch {
      setStatus("Preview saved locally");
    }
  }

  return (
    <main className="shell">
      <nav className="topbar">
        <div className="brand"><span className="brand-mark"><Sparkles size={15} /></span> victory tailora</div>
        <div className="topbar-actions"><span className="status"><span className="status-dot" /> {status}</span><button className="avatar">A</button></div>
      </nav>

      <section className="hero">
        <div className="eyebrow"><LayoutGrid size={14} /> YOUR WORKSPACE, YOUR WAY</div>
        <h1>Build a workspace<br /><em>that feels like you.</em></h1>
        <p className="hero-copy">Choose the tools that matter, arrange them around your rhythm, and leave the rest behind.</p>
      </section>

      <section className="builder">
        <div className="section-heading"><div><span className="step">01</span><h2>Choose your modules</h2></div><span className="count">{selectedIds.length} selected</span></div>
        <div className="module-picker">
          {modules.map((module) => {
            const selected = selectedIds.includes(module.id);
            return <button className={`module-option ${selected ? "is-selected" : ""}`} key={module.id} onClick={() => toggleModule(module.id)}>
              <span className={`module-icon ${module.accent}`}><LayoutGrid size={17} /></span>
              <span className="module-copy"><strong>{module.name}</strong><small>{module.description}</small></span>
              <span className="check">{selected ? <Check size={15} /> : <Plus size={15} />}</span>
            </button>;
          })}
        </div>
      </section>

      <section className="builder layout-section">
        <div className="section-heading"><div><span className="step">02</span><h2>Arrange your flow</h2></div><span className="hint">Move modules up or down</span></div>
        <div className="layout-preview">
          {selectedModules.length === 0 ? <div className="empty-state">Select at least one module to start shaping your workspace.</div> : selectedModules.map((module, index) => <div className="layout-row" key={module.id}>
            <span className="drag-handle">⋮⋮</span><span className={`module-icon ${module.accent}`}><LayoutGrid size={17} /></span><span className="row-name">{module.name}</span><span className="row-actions"><button aria-label={`Move ${module.name} up`} disabled={index === 0} onClick={() => moveModule(index, -1)}><ArrowUp size={15} /></button><button aria-label={`Move ${module.name} down`} disabled={index === selectedModules.length - 1} onClick={() => moveModule(index, 1)}><ArrowDown size={15} /></button></span>
          </div>)}
        </div>
        <button className="save-button" onClick={saveLayout}>Save this workspace <span>↗</span></button>
      </section>

      <footer><span>Victory Tailora / Early foundation</span><span>Make it yours.</span></footer>
    </main>
  );
}

export default App;

