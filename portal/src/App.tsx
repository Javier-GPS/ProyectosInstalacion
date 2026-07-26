import { FormEvent, useEffect, useRef, useState } from 'react';

type User = {
  name: string;
  email: string;
  role: string;
};

type Service = {
  id: 'luxstudio' | 'gisvial';
  eyebrow: string;
  name: string;
  description: string;
  detail: string;
  url: string;
  accent: string;
};

const TOKEN_KEY = 'salvi-portal-token';
const keycloakUrl = (import.meta.env.VITE_KEYCLOAK_URL || '/keycloak').replace(/\/$/, '');
const keycloakClient = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'portal';

const services: Service[] = [
  {
    id: 'gisvial',
    eyebrow: '01 / TERRITORIO',
    name: 'GISVial',
    description: 'Planificación geográfica del alumbrado público.',
    detail: 'Mapas, zonas, inventario y trazados',
    url: import.meta.env.VITE_GISVIAL_URL || 'http://localhost:5174',
    accent: 'mint',
  },
  {
    id: 'luxstudio',
    eyebrow: '02 / CÁLCULO',
    name: 'LUX Studio',
    description: 'Diseño y cálculo fotométrico de instalaciones.',
    detail: 'Proyectos, tramos, luminarias y optimización',
    url: import.meta.env.VITE_LUXSTUDIO_URL || 'http://localhost:5173',
    accent: 'amber',
  },
];

const serviceOrigin = (url: string) => new URL(url, window.location.href).origin;

function PortalMark() {
  return (
    <div className="brand-mark" aria-label="SALVI Lighting">
      <span className="brand-dot" />
      <span>SALVI</span>
      <small>LIGHTING</small>
    </div>
  );
}

function Login({ onLogin }: { onLogin: (username: string, password: string) => Promise<void> }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se ha podido iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-aside">
        <PortalMark />
        <div className="aside-copy">
          <p className="kicker">PLATAFORMA DE OPERACIONES</p>
          <h1>La luz empieza<br /><em>en un solo lugar.</em></h1>
          <p className="aside-text">Accede a tus herramientas de diseño y planificación desde un único espacio de trabajo.</p>
        </div>
        <p className="aside-footer">SALVI LIGHTING · PORTAL DE SERVICIOS</p>
      </section>
      <section className="login-card-wrap">
        <div className="login-card">
          <div className="mobile-brand"><PortalMark /></div>
          <p className="kicker">ACCESO DE USUARIO</p>
          <h2>Bienvenido</h2>
          <p className="login-intro">Introduce tus credenciales para continuar.</p>
          <form onSubmit={submit}>
            <label>
              Usuario o email
              <input value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" autoFocus required />
            </label>
            <label>
              Contraseña
              <input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required />
            </label>
            {error && <p className="form-error" role="alert">{error}</p>}
            <button className="primary-button" type="submit" disabled={loading}>
              {loading ? 'Comprobando…' : 'Entrar al portal'}
              {!loading && <span aria-hidden="true">→</span>}
            </button>
          </form>
          <p className="security-note"><span>●</span> Acceso protegido por SALVI Identity</p>
        </div>
      </section>
    </main>
  );
}

function ServiceCard({ service, onOpen }: { service: Service; onOpen: () => void }) {
  return (
    <button className={`service-card ${service.accent}`} onClick={onOpen}>
      <span className="service-number">{service.eyebrow}</span>
      <span className="service-icon" aria-hidden="true">{service.id === 'luxstudio' ? '✦' : '⌖'}</span>
      <span className="service-name">{service.name}</span>
      <span className="service-description">{service.description}</span>
      <span className="service-detail">{service.detail}</span>
      <span className="service-open">Abrir servicio <strong>↗</strong></span>
    </button>
  );
}

function Workspace({ user, token, onLogout }: { user: User; token: string; onLogout: () => void }) {
  const [activeService, setActiveService] = useState<Service | null>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);

  const sendToken = () => {
    if (!frameRef.current?.contentWindow || !activeService) return;
    frameRef.current.contentWindow.postMessage(
      { type: 'salvi:auth', token },
      serviceOrigin(activeService.url),
    );
  };

  useEffect(() => {
    sendToken();
  }, [activeService, token]);

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <PortalMark />
        <div className="topbar-right">
          <div className="user-chip"><span className="avatar">{(user.name || user.email).charAt(0).toUpperCase()}</span><span>{user.name || user.email}</span></div>
          <button className="logout-button" onClick={onLogout}>Salir</button>
        </div>
      </header>
      {!activeService ? (
        <section className="launcher">
          <div className="launcher-heading">
            <div>
              <p className="kicker">CENTRO DE CONTROL</p>
              <h1>¿Dónde quieres trabajar?</h1>
              <p>Elige una herramienta. Tu sesión ya está activa en ambas.</p>
            </div>
            <div className="session-status"><span /> SESIÓN ACTIVA</div>
          </div>
          <div className="services-grid">
            {services.map(service => <ServiceCard key={service.id} service={service} onOpen={() => setActiveService(service)} />)}
          </div>
          <p className="launcher-footer">Puedes cambiar de herramienta en cualquier momento desde este portal.</p>
        </section>
      ) : (
        <section className="service-view">
          <div className="service-toolbar">
            <button className="back-button" onClick={() => setActiveService(null)}>← Volver al portal</button>
            <span className="service-toolbar-title">{activeService.name}</span>
            <button className="logout-button" onClick={onLogout}>Cerrar sesión</button>
          </div>
          <iframe
            ref={frameRef}
            title={activeService.name}
            src={activeService.url}
            onLoad={() => {
              sendToken();
              window.setTimeout(sendToken, 250);
            }}
            className="service-frame"
          />
        </section>
      )}
    </main>
  );
}

export default function App() {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);

  const getUser = async (accessToken: string) => {
    const response = await fetch('/api/auth/me', { headers: { Authorization: `Bearer ${accessToken}` } });
    if (!response.ok) throw new Error('La sesión ha caducado');
    return response.json() as Promise<User>;
  };

  useEffect(() => {
    if (!token) {
      setChecking(false);
      return;
    }
    getUser(token)
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => setChecking(false));
  }, [token]);

  const login = async (username: string, password: string) => {
    const clients = [keycloakClient, ...(keycloakClient === 'portal' ? ['luxstudio'] : [])];
    let data: { access_token?: string; error?: string; error_description?: string } | null = null;
    for (const clientId of clients) {
      const response = await fetch(`${keycloakUrl}/realms/salvi/protocol/openid-connect/token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ grant_type: 'password', client_id: clientId, username, password }),
      });
      data = await response.json().catch(() => null);
      if (response.ok && data?.access_token) break;
      const missingClient = data?.error === 'invalid_client' || data?.error_description?.toLowerCase().includes('client');
      if (!missingClient) break;
    }
    if (!data?.access_token) throw new Error('Usuario o contraseña incorrectos');
    const accessToken = data.access_token as string;
    const loggedUser = await getUser(accessToken);
    localStorage.setItem(TOKEN_KEY, accessToken);
    setUser(loggedUser);
    setToken(accessToken);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  if (checking) return <div className="loading-screen"><span />Cargando portal</div>;
  if (!token || !user) return <Login onLogin={login} />;
  return <Workspace user={user} token={token} onLogout={logout} />;
}
