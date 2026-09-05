"""
Configuración de la aplicación de Cálculo Fotométrico
"""

import os
from datetime import timedelta

# Configuración base
DEBUG = True
TESTING = False
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Configuración de archivos
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB máximo
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'downloads')
ASSETS_FOLDER = os.path.join(os.path.dirname(__file__), 'assets')

# Crear directorios si no existen
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(ASSETS_FOLDER, exist_ok=True)

# Configuración de sesión
PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
SESSION_COOKIE_SECURE = False  # True en producción con HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# Validaciones
VALIDATION_CONFIG = {
    'altura_montaje_min': 0,
    'altura_montaje_max': 50,
    'interdistancia_min': 1,
    'interdistancia_max': 100,
    'saliente_brazo_min': 0,
    'saliente_brazo_max': 10,
    'inclinacion_brazo_min': -90,
    'inclinacion_brazo_max': 90,
}

# Opciones para desplegables
DISPOSICIONES = [
    'Unilateral',
    'Bilateral',
    'Bilateral asimétrica',
    'Central',
]

PAVIMENTOS = [
    'Asfalto',
    'Hormigón',
    'Adoquín',
    'Empedrado',
    'Otro',
]

CLASES_ILUMINACION = [
    'ME1',
    'ME2',
    'ME3a',
    'ME3b',
    'ME4a',
    'ME4b',
    'ME5',
    'ME6',
    'S1',
    'S2',
    'S3',
    'S4',
    'S5',
    'S6',
]

NORMAS = [
    'CIE 140',
    'CIE 115',
    'UNE EN 13201',
    'DIN EN 13201',
    'ISO EN 13201',
    'NFPA',
]

ZONAS_AMBIENTALES = [
    'E1',  # Zonas protegidas
    'E2',  # Zonas residenciales
    'E3',  # Zonas comerciales
    'E4',  # Zonas de alta luminancia
]

IDIOMAS = [
    ('es', 'Español'),
    ('en', 'English'),
    ('fr', 'Français'),
    ('de', 'Deutsch'),
    ('it', 'Italiano'),
]

# Configuración de servidor (producción)
if os.environ.get('FLASK_ENV') == 'production':
    DEBUG = False
    SESSION_COOKIE_SECURE = True
