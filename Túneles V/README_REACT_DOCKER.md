# Túneles V · React + Docker

La nueva interfaz de Túneles V está en `frontend/`. El backend Flask conserva
las rutas y motores específicos del proyecto, y expone además el catálogo
persistente de proyectos bajo `/api/tunnel/projects`.

## Arranque local

```powershell
# Terminal 1, backend (API interna de desarrollo)
python app.py

# Terminal 2, frontend
cd frontend
npm install
npm run dev
```

Abrir únicamente `http://127.0.0.1:5173/projects`.

## Arranque con Docker

```powershell
docker compose up --build
```

Abrir únicamente `http://127.0.0.1:5173/projects`.

En Docker solo se publica el puerto `5173`; Flask queda accesible únicamente
para el contenedor frontend a través de la red interna.

El volumen `tunnel_data` conserva los proyectos guardados. El cálculo sigue
ejecutándose mediante `POST /api/tunnel/calculate` y recibe únicamente la
configuración directa del túnel; no necesita mapa, Leaflet, OSM ni coordenadas.
