import React, { Suspense, useEffect, useMemo } from 'react';
import { useAuth } from './auth/AuthContext';
import { setAuthFetch } from './lib/api';
import GisLayout from './layouts/GisLayout';
import LoginPage from './pages/LoginPage';

function LoadingScreen() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-salvi-cream">
      <div className="text-center text-salvi-muted">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-salvi-black border-t-transparent" />
        Cargando SALVI GIS...
      </div>
    </main>
  );
}

function App() {
  const { user, loading, authFetch } = useAuth();

  // Expose authFetch to the API layer
  useEffect(() => {
    setAuthFetch(authFetch);
  }, [authFetch]);

  if (loading) return <LoadingScreen />;
  if (!user) return <LoginPage />;

  return (
    <Suspense fallback={<LoadingScreen />}>
      <GisLayout />
    </Suspense>
  );
}

export default App;
