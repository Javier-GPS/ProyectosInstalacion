import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import { ProjectCard, ProjectFormModal, EmptyProjectsState, NewProjectCard } from '../components/projects';
import {
  listProjects,
  deleteProject,
  type ProjectRecord,
} from '../lib/projects';

const ProjectsListPage: React.FC = () => {
  const { authFetch } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();

  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<ProjectRecord | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await listProjects(authFetch);
      setProjects(data);
    } catch (err: any) {
      setLoadError(err.message || t('errors.unknown'));
    } finally {
      setLoading(false);
    }
  }, [authFetch, t]);

  useEffect(() => {
    load();
  }, [load]);

  const handleOpen = (project: ProjectRecord) => {
    navigate(`/projects/${project.id}`);
  };

  const handleEdit = (project: ProjectRecord) => {
    setEditingProject(project);
    setModalOpen(true);
  };

  const handleCreate = () => {
    setEditingProject(null);
    setModalOpen(true);
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(t('projects.confirmDelete'))) return;
    try {
      await deleteProject(authFetch, id);
      setProjects(current => current.filter(p => p.id !== id));
    } catch (err: any) {
      setLoadError(err.message || t('errors.unknown'));
    }
  };

  const handleSaved = (project: ProjectRecord) => {
    setProjects(current => {
      const exists = current.find(p => p.id === project.id);
      if (exists) {
        return current.map(p => (p.id === project.id ? project : p));
      }
      return [project, ...current];
    });
  };

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <h2 className="text-2xl font-semibold text-[#1E1E1E]">{t('projects.title')}</h2>
          <p className="mt-1 text-sm text-[#A09A91]">{t('projects.subtitle')}</p>
        </div>

        {loadError && (
          <div className="mb-6 rounded-lg border border-[#B42318]/25 bg-[#FDECEA] px-4 py-3 text-sm text-[#B42318]">
            {loadError}
          </div>
        )}

        {loading ? (
          <div className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-12 text-center text-[#6a6a6a]">
            {t('actions.loading')}
          </div>
        ) : projects.length === 0 ? (
          <EmptyProjectsState onCreate={handleCreate} />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <NewProjectCard onClick={handleCreate} />
            {projects.map(project => (
              <ProjectCard
                key={project.id}
                project={project}
                isOpen={false}
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

export default ProjectsListPage;
