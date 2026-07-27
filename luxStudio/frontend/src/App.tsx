import React, { lazy, Suspense, useMemo } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import MainLayout from './layouts/MainLayout';
const ProjectsListPage = lazy(() => import('./pages/ProjectsListPage'));
const ProjectTramosPage = lazy(() => import('./pages/ProjectTramosPage'));
const TramoEditorPage = lazy(() => import('./pages/TramoEditorPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));

function LoadingScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#FCF9F5]">
      <div className="text-center text-[#A09A91]">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-[#1E1E1E] border-t-transparent" />
        Cargando LUX Studio...
      </div>
    </main>
  );
}

function App() {
  const { user, loading } = useAuth();

  const router = useMemo(() => {
    const adminElement = user?.role === 'ADMIN'
      ? <AdminPage />
      : <Navigate to="/projects" replace />;
    return createBrowserRouter([
      {
        path: '/',
        element: <MainLayout />,
        children: [
          { index: true, element: <Navigate to="/projects" replace /> },
          { path: 'projects', element: <ProjectsListPage /> },
          { path: 'projects/:projectId/tramos/new', element: <TramoEditorPage /> },
          { path: 'projects/:projectId/tramos/:tramoId', element: <TramoEditorPage /> },
          { path: 'projects/:id', element: <ProjectTramosPage /> },
          { path: 'admin', element: adminElement },
          { path: '*', element: <Navigate to="/projects" replace /> },
        ],
      },
    ]);
  }, [user?.role]);

  if (loading) {
    return <LoadingScreen />;
  }

  if (!user) {
    return <LoadingScreen />;
  }

  return (
    <Suspense fallback={<LoadingScreen />}>
      <RouterProvider router={router} />
    </Suspense>
  );
}

export default App;
