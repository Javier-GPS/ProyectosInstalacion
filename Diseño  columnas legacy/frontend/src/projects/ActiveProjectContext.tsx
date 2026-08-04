import { createContext, useContext, useState, type ReactNode } from "react";
import type { Project } from "../api/projects";

interface ActiveProjectContextValue {
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
}

const ActiveProjectContext = createContext<ActiveProjectContextValue | undefined>(undefined);

export function ActiveProjectProvider({ children }: { children: ReactNode }) {
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  return (
    <ActiveProjectContext.Provider value={{ activeProject, setActiveProject }}>
      {children}
    </ActiveProjectContext.Provider>
  );
}

export function useActiveProject(): ActiveProjectContextValue {
  const ctx = useContext(ActiveProjectContext);
  if (!ctx) {
    throw new Error("useActiveProject debe usarse dentro de ActiveProjectProvider");
  }
  return ctx;
}
