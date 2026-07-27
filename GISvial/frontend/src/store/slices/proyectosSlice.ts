import type { StateCreator } from 'zustand';
import type { GisProject } from '../../types';

export interface ProyectosSlice {
  initialized: boolean;
  projects: GisProject[];
  activeProjectId: string | null;
  setInitialized: (v: boolean) => void;
  setProjects: (projects: GisProject[]) => void;
  setActiveProject: (id: string | null) => void;
  addProject: (project: GisProject) => void;
  removeProject: (id: string) => void;
}

export const createProyectosSlice: StateCreator<ProyectosSlice, [], [], ProyectosSlice> = (set) => ({
  initialized: false,
  projects: [],
  activeProjectId: null,

  setInitialized: (v) => set({ initialized: v }),
  setProjects: (projects) => set({ projects }),
  setActiveProject: (id) => set({ activeProjectId: id }),
  addProject: (project) => set((s) => ({ projects: [...s.projects, project] })),
  removeProject: (id) => set((s) => ({
    projects: s.projects.filter((p) => p.id !== id),
    activeProjectId: s.activeProjectId === id ? null : s.activeProjectId,
  })),
});
