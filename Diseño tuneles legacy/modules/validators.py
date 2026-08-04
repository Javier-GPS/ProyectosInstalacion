import pandas as pd

class DataValidator:
    """Validador de datos para formularios y Excel"""

    def validate_form_data(self, data):
        """Valida datos del formulario manual - FLEXIBLE"""
        errors = []

        # Solo validar campos realmente críticos en Sección 1
        required_fields = [
            ('nombre_proyecto', 'Nombre del proyecto'),
            ('cliente_final', 'Cliente final'),
        ]

        for field, label in required_fields:
            if field not in data or not data[field]:
                errors.append(f'{label} es obligatorio')

        # Si modo es manual, validar lo mínimo de Sección 2
        if data.get('modo') == 'manual':
            # Solo validar si están presentes
            geometry_fields = [
                ('altura_montaje', 'Altura de montaje', 0, 50),
                ('interdistancia', 'Interdistancia', 1, 100),
            ]

            for field, label, min_val, max_val in geometry_fields:
                if field in data and data[field] is not None and str(data[field]).strip():
                    try:
                        value = float(data[field])
                        if value < min_val or value > max_val:
                            errors.append(f'{label} debe estar entre {min_val} y {max_val}')
                    except (ValueError, TypeError):
                        errors.append(f'{label} debe ser un número válido')

            # Sección 3: Luminarias (validar si existen)
            if 'luminarias' in data and data['luminarias'] and len(data['luminarias']) > 0:
                for i, lum in enumerate(data['luminarias']):
                    # Solo validar campos que el usuario ingresó
                    if lum.get('modelo') and not lum.get('optica'):
                        errors.append(f'Luminaria {i+1}: Óptica LDT es obligatoria')
                    if lum.get('optica') and not lum.get('modelo'):
                        errors.append(f'Luminaria {i+1}: Modelo es obligatorio')

        return errors

    def validate_excel_data(self, df):
        """Valida datos del Excel importado"""
        errors = []

        if df.empty:
            errors.append('El Excel no contiene datos')
            return errors

        # Validar columnas requeridas
        required_columns = [
            'Identificador modelo',
            'Disposición de las luminarias',
            'Altura de montaje (h)',
            'Ancho de calzada 1 (W1)',
            'Clase calzada',
            'Modelo luminaria',
            'Óptica / código LDT',
            'Potencia nominal',
        ]

        for col in required_columns:
            if col not in df.columns:
                errors.append(f'Columna faltante: {col}')

        # Validar filas sin datos críticos
        for idx, row in df.iterrows():
            row_errors = []
            if pd.isna(row.get('Identificador modelo')):
                row_errors.append('Falta identificador modelo')
            if pd.isna(row.get('Modelo luminaria')):
                row_errors.append('Falta modelo de luminaria')

            if row_errors:
                errors.append(f'Fila {idx+2}: {", ".join(row_errors)}')

        return errors

    def sanitize_data(self, data):
        """Limpia y normaliza datos"""
        cleaned = {}

        for key, value in data.items():
            if isinstance(value, str):
                cleaned[key] = value.strip()
            elif value is None:
                cleaned[key] = ''
            else:
                cleaned[key] = value

        return cleaned
