import React, { useState } from 'react';
import { useI18n } from '../i18n';
import { useGisStore } from '../store/useGisStore';
import { deleteProject } from '../lib/api';
import { useApi } from '../hooks/useApi';
import type { GisProject } from '../types';
import ProjectCard from '../components/projects/ProjectCard';
import NewProjectCard from '../components/projects/NewProjectCard';
import EmptyProjectsState from '../components/projects/EmptyProjectsState';
import ProjectFormModal from '../components/projects/ProjectFormModal';

const ProjectsPage: React.FC = () => {
  const { t } = useI18n();
  const projects = useGisStore(s => s.projects);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const setActiveProject = useGisStore(s => s.setActiveProject);
  const addProject = useGisStore(s => s.addProject);
  const removeProject = useGisStore(s => s.removeProject);
  const setProjects = useGisStore(s => s.setProjects);
  const setSelectedZone = useGisStore(s => s.setSelectedZone);
  const setStepWizard = useGisStore(s => s.setStepWizard);
  const setView = useGisStore(s => s.setView);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<GisProject | null>(null);
  const { call: callDelete, error: deleteError } = useApi<void>();

  const handleOpen = (project: GisProject) => {
    setActiveProject(project.id);
    setSelectedZone(null);
    setStepWizard('proyecto');
    setView('project');
  };

  const handleCreate = () => {
    setEditingProject(null);
    setModalOpen(true);
  };

  const handleEdit = (project: GisProject) => {
    setEditingProject(project);
    setModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm(t('projects.confirmDelete'))) return;
    try {
      await callDelete(signal => deleteProject(id, signal));
      removeProject(id);
    } catch (err) {
      console.error('No se pudo eliminar el proyecto', err);
    }
  };

  const handleSaved = (saved: GisProject) => {
    const exists = projects.some(p => String(p.id) === String(saved.id));
    if (exists) {
      setProjects(projects.map(p => (String(p.id) === String(saved.id) ? saved : p)));
    } else {
      addProject(saved);
    }
  };

  return (
    <main className="flex-1 overflow-y-auto bg-salvi-cream">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-8">
          <h2 className="text-2xl font-semibold text-salvi-black">{t('projects.title')}</h2>
          <p className="mt-1 text-sm text-salvi-muted">{t('projects.subtitle')}</p>
        </div>

        {deleteError && (
          <div className="mb-6 rounded-lg border border-state-danger/25 bg-[#FDECEA] px-4 py-3 text-sm text-state-danger">
            {deleteError}
          </div>
        )}

        {projects.length === 0 ? (
          <EmptyProjectsState onCreate={handleCreate} />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <NewProjectCard onClick={handleCreate} />
            {projects.map(project => (
              <ProjectCard
                key={project.id}
                project={project}
                isOpen={String(activeProjectId) === String(project.id)}
                onOpen={handleOpen}
                onEdit={handleEdit}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>

      <ProjectFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSaved={handleSaved}
        initialProject={editingProject}
      />
    </main>
  );
};

export default ProjectsPage;
