import React from 'react';
import { useI18n } from '../../i18n';
import { useGisStore } from '../../store/useGisStore';

const StepProyecto: React.FC = () => {
  const { t } = useI18n();
  const projects = useGisStore(s => s.projects);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const setActiveProject = useGisStore(s => s.setActiveProject);
  const setSelectedZone = useGisStore(s => s.setSelectedZone);
  const setStepWizard = useGisStore(s => s.setStepWizard);

  return (
    <div className="gis-panel rounded-xl overflow-hidden flex flex-col max-h-full">
      <div className="p-3 border-b border-salvi-line">
        <h2 className="text-sm font-semibold text-salvi-black">{t('nav.projects')}</h2>
        <p className="text-xs text-salvi-muted mt-0.5">Selecciona un proyecto para empezar</p>
      </div>

      <div className="overflow-y-auto flex-1 gis-scroll p-2 space-y-1">
        {projects.length === 0 && (
          <div className="p-6 text-center text-xs text-salvi-muted">No hay proyectos</div>
        )}
        {projects.map(project => (
          <button
            key={project.id}
            onClick={() => {
              setActiveProject(project.id);
              setSelectedZone(null);
              setStepWizard('zona');
            }}
            className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
              activeProjectId === project.id
                ? 'bg-salvi-black text-white'
                : 'text-salvi-black hover:bg-salvi-surface'
            }`}
          >
            <div className="font-medium">{project.name}</div>
            {project.created_at && (
              <div className={`text-xs mt-0.5 ${activeProjectId === project.id ? 'text-white/70' : 'text-salvi-muted'}`}>
                {new Date(project.created_at).toLocaleDateString()}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
};

export default StepProyecto;
