from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
from time import perf_counter
from datetime import datetime
from modules.excel_handler import ExcelHandler
from modules.validators import DataValidator
from modules.tunnel.engine import run_tunnel_calculation
from config import (
    DEBUG, UPLOAD_FOLDER, DOWNLOAD_FOLDER, ALLOWED_EXTENSIONS,
    MAX_CONTENT_LENGTH, VALIDATION_CONFIG
)

app = Flask(__name__)

# Cargar configuración
app.config['DEBUG'] = DEBUG
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
app.config['VALIDATION_CONFIG'] = VALIDATION_CONFIG

# Crear directorios si no existen
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

excel_handler = ExcelHandler()
validator = DataValidator()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _luminaire_cache_matches_request(cached_luminaire, request_data) -> bool:
    """Only reuse a photometric cache when its maintenance factor is current.

    A cached CIE 140 result is evidence of the exact calculation previously
    shown to the user.  It must not be attached to a report if the current
    luminaire configuration requests another maintenance factor: both the
    reported factor and the calculated luminances would otherwise be
    inconsistent.
    """
    if not isinstance(cached_luminaire, dict) or not isinstance(request_data, dict):
        return False
    requested_luminaire = (
        request_data.get('luminaire')
        or request_data.get('lum_config')
        or {}
    )
    if not isinstance(requested_luminaire, dict):
        return False
    requested_mf = requested_luminaire.get('maintenance_factor')
    # No factor supplied in the new request: the cache is the only declared
    # value, so it remains the valid source for the generated report.
    if requested_mf in (None, ''):
        return True
    cached_spec = cached_luminaire.get('luminaire') or {}
    cached_mf = cached_spec.get('maintenance_factor') if isinstance(cached_spec, dict) else None
    try:
        return abs(float(cached_mf) - float(requested_mf)) < 1e-9
    except (TypeError, ValueError):
        # A requested factor without a traceable factor in the cache requires
        # a new calculation; silently assuming the legacy default is unsafe.
        return False


@app.route('/api/tunnel/input-template', methods=['GET'])
def tunnel_input_template():
    """Descarga la planilla editable de entradas del motor de túneles."""
    try:
        import io
        from modules.tunnel.input_excel import create_tunnel_input_template

        return send_file(
            io.BytesIO(create_tunnel_input_template()),
            as_attachment=True,
            download_name='plantilla_entradas_tunel_brisco_arguayo_actualizada.xlsx',
            mimetype=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        )
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/tunnel/export-inputs-excel', methods=['POST'])
def tunnel_export_inputs_excel():
    """Exporta la configuraciÃ³n vigente del tubo a la planilla SALVI."""
    try:
        import io
        from modules.tunnel.input_excel import create_tunnel_input_workbook

        payload = request.get_json(silent=True) or {}
        form = payload.get('form', payload) if isinstance(payload, dict) else {}
        if not isinstance(form, dict):
            return jsonify({
                'success': False,
                'error': 'La configuraciÃ³n del tubo no es vÃ¡lida.',
            }), 400
        tube_id = str(form.get('tube_id') or 'T1').strip() or 'T1'
        return send_file(
            io.BytesIO(create_tunnel_input_workbook(form)),
            as_attachment=True,
            download_name=f'configuracion_tunel_{tube_id}.xlsx',
            mimetype=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        )
    except Exception as exc:
        app.logger.exception('Error exportando configuraciÃ³n Excel de tÃºnel: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}), 500


@app.route('/api/tunnel/import-inputs-excel', methods=['POST'])
def tunnel_import_inputs_excel():
    """Lee la planilla SALVI y devuelve únicamente los valores editables."""
    try:
        from modules.tunnel.input_excel import parse_tunnel_input_workbook

        upload = request.files.get('file')
        if not upload or not upload.filename:
            return jsonify({'success': False, 'error': 'Selecciona un archivo Excel.'}), 400
        if not upload.filename.lower().endswith('.xlsx'):
            return jsonify({'success': False, 'error': 'El archivo debe ser .xlsx.'}), 400
        parsed = parse_tunnel_input_workbook(upload.stream)
        return jsonify({'success': True, **parsed})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        app.logger.exception('Error importando entradas Excel de túnel: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}), 500

@app.route('/')
def index():
    """Página principal con formulario"""
    return render_template('index.html')

@app.route('/debug')
def debug():
    """Página de debug para diagnosticar problemas"""
    return render_template('debug.html')

@app.route('/api/submit-form', methods=['POST'])
def submit_form():
    """Recibe datos del formulario en modo manual y genera Excel"""
    try:
        data = request.get_json()
        print(f"DEBUG: Datos recibidos: {list(data.keys())}")

        errors = validator.validate_form_data(data)
        if errors:
            print(f"DEBUG: Errores de validación: {errors}")
            error_message = " | ".join(errors)
            return jsonify({
                'success': False,
                'error': f'Errores en el formulario: {error_message}',
                'errors': errors
            }), 200

        filename = f"estudio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filepath = os.path.join(DOWNLOAD_FOLDER, filename)

        print(f"DEBUG: Creando archivo en: {filepath}")
        excel_handler.create_study_from_form(data, filepath)

        if not os.path.exists(filepath):
            print(f"ERROR: Archivo no fue creado en {filepath}")
            return jsonify({'success': False, 'error': f'Archivo no fue creado'}), 500

        file_size = os.path.getsize(filepath)
        print(f"DEBUG: Archivo creado exitosamente. Tamaño: {file_size} bytes")

        return jsonify({
            'success': True,
            'message': f'Excel generado correctamente ({file_size} bytes)',
            'download_url': f'/api/download/{filename}',
            'filename': filename
        }), 200

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR en submit_form: {str(e)}")
        print(f"Traceback: {error_trace}")
        return jsonify({'success': False, 'error': str(e), 'traceback': error_trace}), 500

@app.route('/api/upload-excel', methods=['POST'])
def upload_excel():
    """Recibe Excel con múltiples estudios y lo procesa"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Only .xlsx and .xls files allowed'}), 400

        filename = secure_filename(file.filename)
        upload_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(upload_path)

        results = excel_handler.process_imported_excel(upload_path)

        output_filename = f"resultados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        output_path = os.path.join(DOWNLOAD_FOLDER, output_filename)

        excel_handler.create_results_excel(results, output_path)

        os.remove(upload_path)

        return jsonify({
            'success': True,
            'message': f'Excel procesado: {len(results)} estudios encontrados',
            'download_url': f'/api/download/{output_filename}'
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/download-template', methods=['GET'])
def download_template():
    """Descarga la plantilla Excel vacía para múltiples estudios"""
    try:
        filename = 'plantilla_app_salvilux.xlsx'
        assets_folder = getattr(app.config, 'ASSETS_FOLDER', os.path.join(os.path.dirname(__file__), 'assets'))
        filepath = os.path.join(assets_folder, filename)

        if not os.path.exists(filepath):
            alt_paths = [
                os.path.join(os.path.dirname(__file__), 'assets', filename),
                os.path.join(os.getcwd(), 'assets', filename),
                filename
            ]
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    filepath = alt_path
                    break
            else:
                return jsonify({'success': False, 'error': f'Template not found in {assets_folder}'}), 404

        return send_file(filepath, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        return jsonify({'success': False, 'error': f'Error downloading template: {str(e)}'}), 500

@app.route('/api/download-ldts', methods=['GET'])
def download_ldts():
    """Descarga la librería de LDTs comprimida"""
    try:
        filename = 'LDTs_luminarias.zip'
        assets_folder = getattr(app.config, 'ASSETS_FOLDER', os.path.join(os.path.dirname(__file__), 'assets'))
        filepath = os.path.join(assets_folder, filename)

        if not os.path.exists(filepath):
            alt_paths = [
                os.path.join(os.path.dirname(__file__), 'assets', filename),
                os.path.join(os.getcwd(), 'assets', filename),
                filename
            ]
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    filepath = alt_path
                    break
            else:
                return jsonify({'success': False, 'error': f'LDT library not found in {assets_folder}'}), 404

        return send_file(filepath, as_attachment=True, download_name=filename, mimetype='application/zip')

    except Exception as e:
        return jsonify({'success': False, 'error': f'Error downloading LDTs: {str(e)}'}), 500

@app.route('/api/download/<filename>', methods=['GET'])
def download_file(filename):
    """Descarga archivos generados"""
    try:
        safe_filename = secure_filename(filename)
        filepath = os.path.join(DOWNLOAD_FOLDER, safe_filename)

        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': f'File not found: {filepath}'}), 404

        file_size = os.path.getsize(filepath)
        return send_file(filepath, as_attachment=True, download_name=filename, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        return jsonify({'success': False, 'error': str(e), 'traceback': error_trace}), 500

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200


# ══════════════════════════════════════════════════════════════════
# SALVI TUNNEL ENGINE — Rutas API (CIE 88:2004)
# ══════════════════════════════════════════════════════════════════

@app.route('/tunnel')
def tunnel_index():
    """Página principal del módulo de túneles.
    Se sirve directamente (sin Jinja2) para preservar la sintaxis JSX {{ }}."""
    import os
    from flask import send_from_directory
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    return send_from_directory(templates_dir, 'tunnel.html')


@app.route('/api/tunnel/calculate', methods=['POST'])
def tunnel_calculate():
    """
    Calcula el diseño completo de un túnel según CIE 88:2004.
    Body JSON: ver run_tunnel_calculation() en modules/tunnel/engine.py
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos JSON'}), 400

        result = run_tunnel_calculation(data)
        status_code = 200 if result.get('success') else 422
        if not result.get('success') and not result.get('error'):
            errors = result.get('errors') or []
            result['error'] = (
                ' · '.join(str(item) for item in errors)
                if errors
                else 'Los datos de entrada no son válidos.'
            )
        return jsonify(result), status_code

    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/tunnel/classify', methods=['POST'])
def tunnel_classify():
    """
    Solo clasifica el túnel (TUN-CLS-001 a 003).
    Útil para feedback rápido mientras el usuario rellena el formulario.
    """
    try:
        data = request.get_json()
        from modules.tunnel.classification import classify_tunnel
        from modules.tunnel.design_speed import calculate_design_speed

        length_m  = float(data.get('length_m', 300))
        speed_kmh = float(data.get('speed_kmh', 80))
        gradient  = float(data.get('gradient_pct', 0.0))
        exit_vis  = bool(data.get('exit_visible', False))
        daylight  = data.get('daylight_penetration', 'poor')
        traffic   = int(data.get('traffic_veh_h', 500))
        has_ped   = bool(data.get('has_pedestrians', False))
        curv      = data.get('curvature_radius_m', None)

        speed_r = calculate_design_speed(speed_kmh, gradient)
        SD = speed_r.stopping_distance_m

        cls = classify_tunnel(
            length_m=length_m,
            stopping_distance_m=SD,
            exit_visible=exit_vis,
            daylight_penetration=daylight,
            traffic_veh_h=traffic,
            has_pedestrians=has_ped,
            speed_kmh=speed_kmh,
            curvature_radius_m=float(curv) if curv else None,
            gradient_pct=gradient
        )

        return jsonify({
            'success': True,
            'geometric': cls.geometric_category.value,
            'optical': cls.optical_category.value,
            'daylighting': cls.daylighting_need.value,
            'SD_m': SD,
            'justification': cls.justification
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tunnel/lth', methods=['POST'])
def tunnel_lth():
    """
    Calcula L20, Lseq y Lth para preview rápido.
    """
    try:
        data = request.get_json()
        from modules.tunnel.l20_lseq_lth import (
            calculate_L20_model, calculate_L20_table,
            calculate_Lseq, calculate_Lth
        )
        from modules.tunnel.design_speed import (
            calculate_design_speed, default_friction_coefficient
        )
        from modules.tunnel.models import PortalOrientation, SkyCondition

        def optional_float(key):
            value = data.get(key)
            return None if value in (None, '') else float(value)

        speed_kmh = float(data.get('speed_kmh', 80))
        traffic   = int(data.get('traffic_veh_h', 500))
        num_lanes = max(1, int(data.get('num_lanes', 1)))
        direction = data.get('traffic_direction', 'one_way')
        orient    = PortalOrientation(data.get('portal_orientation', 'S'))
        sky       = SkyCondition(data.get('sky_condition', 'clear'))
        env_type  = data.get('environment_type', 'open_country_flat')
        method    = data.get('l20_method', 'model')

        if method == 'table':
            l20_r = calculate_L20_table(env_type, orient)
        else:
            l20_r = calculate_L20_model(env_type, orient, sky)

        l20_override = optional_float('l20_override')
        if l20_override is not None:
            l20_r.L20 = l20_override
            l20_r.method = 'override'

        mu = optional_float('mu_friction')
        if mu is None:
            mu = default_friction_coefficient(speed_kmh)
        speed_r = calculate_design_speed(
            speed_kmh=speed_kmh,
            gradient_pct=float(data.get('gradient_pct', 0) or 0),
            reaction_time_s=float(data.get('t_reaction', 2.5) or 2.5),
            friction_coefficient=mu,
        )
        stopping_distance = (
            optional_float('stopping_distance_override_m')
            or speed_r.stopping_distance_m
        )
        lseq_r = calculate_Lseq(
            l20_r.L20, override=optional_float('lseq_override')
        )
        lth_method = data.get('lth_method', 'k_factor')
        lth_r = calculate_Lth(
            l20_r,
            speed_kmh,
            traffic,
            method=lth_method,
            Lseq_result=lseq_r if lth_method == 'lseq' else None,
            qc_override=optional_float('qc_override'),
            stopping_distance_m=stopping_distance,
            tunnel_class=data.get('tunnel_class', 'auto'),
            num_lanes=num_lanes,
            traffic_direction=direction,
            mixed_traffic=bool(data.get('has_pedestrians', False)),
            standard=data.get('lth_standard', 'oc36_2015'),
            k_override=optional_float('k_lth_override'),
            contrast_observation=float(
                data.get('contrast_observation', 0.04) or 0.04
            ),
        )

        return jsonify({
            'success': True,
            'L20': round(l20_r.L20, 0),
            'Lseq': round(lseq_r.Lseq, 0),
            'Lth': round(lth_r.Lth, 1),
            'k_factor': round(lth_r.k_factor, 4),
            'qc': round(lth_r.qc, 3),
            'qc_used': lth_r.qc_used,
            'stopping_distance_m': round(stopping_distance, 1),
            'tunnel_class': lth_r.tunnel_class,
            'calculated_tunnel_class': lth_r.calculated_tunnel_class,
            'standard': lth_r.standard,
            'k_source': lth_r.k_source,
            'l20_note': l20_r.note
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tunnel/control', methods=['POST'])
def tunnel_control():
    """
    Genera el plan de control completo (escenas, grupos, curvas, DALI/Smartec).
    Puede llamarse de forma independiente con los parámetros del diseño,
    o los datos vienen del resultado de /api/tunnel/calculate.

    Body JSON mínimo:
        L20_design, Lth_design, Lin, L_night, k_factor,
        speed_kmh, zones (dict), n_transition_groups, protocol
    """
    try:
        data = request.get_json()
        from modules.tunnel.control import build_control_plan, export_dali, export_smartec
        from modules.tunnel.zones import build_zones
        from modules.tunnel.models import TrafficDirection

        # Si llegan los parámetros completos, recalcular todo con el engine
        if data.get('recalculate'):
            from modules.tunnel.engine import run_tunnel_calculation
            result = run_tunnel_calculation(data)
            if not result.get('success'):
                return jsonify(result), 422
            ctrl = result['control']
        else:
            # Usar parámetros pre-calculados
            from modules.tunnel.engine import run_tunnel_calculation
            result = run_tunnel_calculation(data)
            if not result.get('success'):
                return jsonify(result), 422
            ctrl = result['control']

        # Export según protocolo solicitado
        protocol = data.get('protocol', data.get('control_protocol', 'DALI'))
        from modules.tunnel.control import TunnelControlPlan, ControlProtocol, ControlScene, ControlGroup, RegulationCurve, SceneType, ZoneType as CZoneType
        # El export ya está en el resultado del engine — lo devolvemos enriquecido
        return jsonify({
            'success': True,
            'control': ctrl,
            'summary': result.get('summary', {})
        })

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e),
                        'traceback': traceback.format_exc()}), 500


@app.route('/api/tunnel/export-excel', methods=['POST'])
def tunnel_export_excel():
    """
    Genera y devuelve el libro Excel completo del cálculo de túnel.
    Body JSON:
        <parámetros normales del túnel>  +
        luminaires_result: { ... }  (preferido — resultado CIE 140 ya validado)
        luminaire: { ... }  (opcional — recálculo si no existe resultado validado)
        road_width_m: float (opcional)
    """
    try:
        import io
        from modules.tunnel.excel_export import generate_excel

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos JSON'}), 400

        # Cálculo completo del túnel
        result = run_tunnel_calculation(data)
        if not result.get('success'):
            return jsonify(result), 422

        # Luminarias (opcionales)
        lum_dict = data.get('luminaires_result')
        if not isinstance(lum_dict, dict) or not lum_dict.get('zones'):
            lum_dict = None
        if lum_dict is None and (data.get('luminaire') or data.get('lum_config')):
            try:
                from modules.tunnel.luminaires import calculate_luminaire_layout
                zones_raw    = result.get('zones', {})
                zones_list   = list(zones_raw.values()) if isinstance(zones_raw, dict) else zones_raw
                road_width_m = float(data.get('road_width_m', data.get('width_m', 7.0)))
                tube_length  = float(result['summary'].get('length_m', 300))
                tube_id      = result['summary'].get('tube_id', 'T1')
                luminaire_params = dict(data.get('luminaire') or data.get('lum_config') or {})
                luminaire_params.update({
                    'speed_kmh': float(data.get('speed_kmh', 80)),
                    'Lth': float(result['summary'].get('Lth', 0)),
                    'Lin': float(result['summary'].get('Lin', 0)),
                    'L_night': float(result['summary'].get('L_night', 1.0)),
                    'Lth_b': float(result.get('lth', {}).get('Lth_b', result['summary'].get('Lth', 0))),
                    'control_architecture': str(data.get('control_architecture', 'permanent_base_plus_portal_reinforcement')),
                    'tilt_overrides': data.get('tilt_overrides', {}) or {},
                    'tandem_overrides': data.get('tandem_overrides', {}) or {},
                    'height_m': float(data.get('height_m', 5.5)),
                    'tunnel_shape': str(data.get('tunnel_shape', 'horseshoe')),
                    'H_pared_m': float(data.get('H_pared_m', 3.0)),
                    'num_lanes': max(1, int(data.get('num_lanes', 1) or 1)),
                    'lane_width_m': float(data.get('lane_width_m', data.get('width_m', 7.0))),
                    'shoulder_left_m': float(data.get('shoulder_left_m', 0.0) or 0.0),
                    'shoulder_right_m': float(data.get('shoulder_right_m', 0.0) or 0.0),
                    'sidewalk_left_m': float(data.get('sidewalk_left_m', 0.0) or 0.0),
                    'sidewalk_right_m': float(data.get('sidewalk_right_m', 0.0) or 0.0),
                    # CIE 140: sólo los carriles de circulación entran en
                    # L, U0 y Ul. Aceras y arcenes se conservan como geometría.
                    'include_shoulders_in_luminance_grid': False,
                    'traffic_direction': str(data.get('traffic_direction', 'one_way')),
                })
                lum_r = calculate_luminaire_layout(
                    zones_list       = zones_list,
                    luminaire_params = luminaire_params,
                    road_width_m     = road_width_m,
                    tube_length_m    = tube_length,
                    tube_id          = tube_id,
                )
                lum_dict = lum_r.to_dict()
            except Exception:
                pass  # Si falla la hoja de luminarias, el Excel sigue generándose

        xls_bytes = generate_excel(result, data, lum_dict)

        tube_id  = result.get('summary', {}).get('tube_id', 'T1')
        filename = f"calculo_tunel_{tube_id}.xlsx"

        return send_file(
            io.BytesIO(xls_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/tunnel/export-excel-combined', methods=['POST'])
def tunnel_export_excel_combined():
    """
    Genera un Excel con todos los tubos, cada uno en sus propias hojas.
    Body JSON:
        tubes: { T1: { form: {...} }, T2: { form: {...} }, ... }
    """
    try:
        import io
        from modules.tunnel.excel_export import generate_excel_combined

        data = request.get_json()
        if not data or not data.get('tubes'):
            return jsonify({'success': False, 'error': 'Se requiere "tubes"'}), 400

        tubes_data = []
        for tube_id, tube in data['tubes'].items():
            form   = tube.get('form', {})
            result = run_tunnel_calculation(form)
            if not result.get('success'):
                return jsonify({'success': False,
                                'error': f'Error calculando tubo {tube_id}: {result.get("errors")}'}), 422
            cached_luminaires = form.get('luminaires_result')
            tubes_data.append({
                'result': result,
                'params': form,
                'lum_result': cached_luminaires if isinstance(cached_luminaires, dict) and cached_luminaires.get('zones') else None,
            })

        xls_bytes = generate_excel_combined(tubes_data)
        project   = (data.get('project_name') or 'tunel').replace(' ', '_')[:40]
        filename  = f"calculo_{project}_completo.xlsx"

        return send_file(
            io.BytesIO(xls_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e),
                        'traceback': traceback.format_exc()}), 500


@app.route('/api/tunnel/report-combined', methods=['POST'])
def tunnel_report_combined():
    """
    Genera un informe Word combinado con todos los tubos del proyecto.
    Body JSON:
        tubes: { T1: { form: {...} }, T2: { form: {...} }, ... }
        project_name: str (opcional)
    """
    try:
        import io

        data = request.get_json()
        if not data or not data.get('tubes'):
            return jsonify({'success': False, 'error': 'Se requiere "tubes"'}), 400

        report_version = str(data.get('report_version', 'v1')).lower()
        if report_version == 'v2':
            from modules.tunnel.report_v2 import generate_combined_report_v2 as generate_combined_report
        else:
            from modules.tunnel.report import generate_combined_report

        tubes_raw    = data['tubes']
        project_name = data.get('project_name', '')

        tubes_data = []
        for tube_id, tube in tubes_raw.items():
            form = tube.get('form', {})
            result = run_tunnel_calculation(form)
            if not result.get('success'):
                return jsonify({'success': False,
                                'error': f'Error calculando tubo {tube_id}: {result.get("errors")}'}), 422

            # ── Verificación fotométrica CIE 140 por tubo ──────────────────
            photometric = None
            luminaire_result = None
            cached_photometric = form.get('photometric_result')
            cached_luminaire = form.get('luminaires_result')
            if (
                isinstance(cached_photometric, dict)
                and isinstance(cached_luminaire, dict)
                and cached_luminaire.get('zones')
                and _luminaire_cache_matches_request(cached_luminaire, form)
            ):
                tubes_data.append({
                    'result': result,
                    'params': form,
                    'photometric': cached_photometric,
                    'luminaire': cached_luminaire,
                })
                continue
            try:
                from modules.tunnel.luminaires import calculate_luminaire_layout
                from modules.tunnel.photometric_verify import (
                    compute_real_luminance_profile,
                    unify_zone_verification_with_profile,
                    verify_luminaire_result,
                )
                luminaire_raw = (
                    form.get('luminaire')
                    or form.get('lum_config')
                    or {}
                )
                if luminaire_raw.get('I_max_mA') or luminaire_raw.get('cct'):
                    lum_params = dict(luminaire_raw)
                    lum_params['speed_kmh'] = float(form.get('speed_kmh', 80))
                    lum_params['Lth']       = float(result['summary'].get('Lth', 0))
                    lum_params['Lin']       = float(result['summary'].get('Lin', 0))
                    lum_params['L_night']   = float(result['summary'].get('L_night', 1.0))
                    lum_params['L_night_normal'] = float(result['summary'].get(
                        'L_night_normal', result['summary'].get('Lin', 0),
                    ))
                    lum_params['L_night_reduced'] = float(result['summary'].get(
                        'L_night_reduced', result['summary'].get('L_night', 1.0),
                    ))
                    lum_params['Lth_b']     = float(result.get('lth', {}).get('Lth_b', lum_params['Lth']))
                    lum_params['control_architecture'] = str(form.get(
                        'control_architecture',
                        'permanent_base_plus_portal_reinforcement',
                    ))
                    lum_params['tandem_overrides'] = (
                        form.get('tandem_overrides', {}) or {}
                    )
                    lum_params['ta_design_c'] = float(form.get('ta_design_c', 20.0))
                    lum_params['height_m'] = float(form.get('height_m', 5.5))
                    lum_params['tunnel_shape'] = str(form.get('tunnel_shape', 'horseshoe'))
                    lum_params['H_pared_m'] = float(form.get('H_pared_m', 3.0))
                    lum_params['num_lanes'] = max(
                        1, int(form.get('num_lanes', 1) or 1),
                    )
                    lum_params['lane_width_m'] = float(form.get(
                        'lane_width_m',
                        form.get('road_width_m', form.get('width_m', 7.0)),
                    ))
                    lum_params['shoulder_left_m'] = float(
                        form.get('shoulder_left_m', 0.0) or 0.0
                    )
                    lum_params['shoulder_right_m'] = float(
                        form.get('shoulder_right_m', 0.0) or 0.0
                    )
                    lum_params['sidewalk_left_m'] = float(
                        form.get('sidewalk_left_m', 0.0) or 0.0
                    )
                    lum_params['sidewalk_right_m'] = float(
                        form.get('sidewalk_right_m', 0.0) or 0.0
                    )
                    lum_params['include_shoulders_in_luminance_grid'] = False
                    lum_params['traffic_direction'] = str(
                        form.get('traffic_direction', 'one_way')
                    )
                    lum_params['tilt_overrides'] = (
                        form.get('tilt_overrides', {}) or {}
                    )
                    zones_raw  = result.get('zones', {})
                    zones_list = list(zones_raw.values()) if isinstance(zones_raw, dict) else zones_raw
                    road_width = float(
                        form.get('road_width_m', form.get('width_m', 7.0))
                    )
                    tube_length = float(
                        result['summary'].get('length_m', 300)
                    )
                    lum_r = calculate_luminaire_layout(
                        zones_list       = zones_list,
                        luminaire_params = lum_params,
                        road_width_m     = road_width,
                        tube_length_m    = tube_length,
                        tube_id          = tube_id,
                    )
                    luminaire_result = lum_r.to_dict()
                    photometric = verify_luminaire_result(lum_r, lum_params)
                    profile = compute_real_luminance_profile(
                        lum_r,
                        lum_params,
                        road_width,
                        step_size=1.0 if tube_length <= 500 else 2.0,
                    )
                    photometric['real_profile'] = profile
                    photometric = unify_zone_verification_with_profile(
                        photometric,
                        profile,
                        lum_r,
                        lum_params,
                    )
            except Exception as exc:
                app.logger.exception(
                    'No se ha podido recalcular CIE 140 para el informe combinado (%s): %s',
                    tube_id, exc,
                )
                photometric = None

            tubes_data.append({
                'result': result,
                'params': form,
                'photometric': photometric,
                'luminaire': luminaire_result,
            })

        doc_bytes = generate_combined_report(tubes_data, project_name=project_name)

        safe_name = (project_name or 'tunel').replace(' ', '_').replace('/', '_')[:40]
        suffix = '_v2' if report_version == 'v2' else ''
        filename  = f"informe_{safe_name}_completo{suffix}.docx"

        return send_file(
            io.BytesIO(doc_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e),
                        'traceback': traceback.format_exc()}), 500


@app.route('/api/tunnel/portal-analyze', methods=['POST'])
def tunnel_portal_analyze():
    """
    Recibe 1-2 imagenes de una boca de tunel (multipart/form-data, campo
    'images') + 'lane_width_ref_m' opcional, y devuelve una propuesta de
    geometria via vision de Claude. Ver
    Especificacion_implementacion_geometria_tuneles_desde_imagenes.docx.

    Los valores devueltos son SIEMPRE "Propuestos" — la validacion final
    la hace el usuario en el frontend, nunca este endpoint.
    """
    try:
        from modules.tunnel.portal_vision import analyze_portal_images

        files = request.files.getlist('images')
        files = [f for f in files if f and f.filename]
        if not files:
            return jsonify({'success': False, 'error': 'No se recibió ninguna imagen.'}), 400
        if len(files) > 2:
            return jsonify({'success': False, 'error': 'Máximo 2 imágenes por boca.'}), 400

        lane_width_ref_m = float(request.form.get('lane_width_ref_m', 3.5))

        portal_dir = os.path.join(UPLOAD_FOLDER, 'portal_images',
                                   datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
        os.makedirs(portal_dir, exist_ok=True)

        saved_paths = []
        try:
            for f in files:
                fname = secure_filename(f.filename) or 'imagen.jpg'
                path = os.path.join(portal_dir, fname)
                f.save(path)
                saved_paths.append(path)

            result = analyze_portal_images(saved_paths, lane_width_ref_m)
            return jsonify({'success': True, **result}), 200
        finally:
            # No conservamos las imagenes subidas mas alla del analisis en
            # esta fase (sin almacenamiento persistente/S3 todavia — ver
            # seccion 17 del documento, pendiente para una fase posterior).
            for p in saved_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            try:
                os.rmdir(portal_dir)
            except OSError:
                pass

    except RuntimeError as e:
        # Errores esperados (p.ej. falta ANTHROPIC_API_KEY) -> mensaje claro
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e),
                         'traceback': traceback.format_exc()}), 500


@app.route('/api/tunnel/ai-assistant', methods=['POST'])
def tunnel_ai_assistant():
    """Responde dudas del proyecto con contexto fotomÃ©trico acotado.

    El modelo solo devuelve un informe y propuestas. No se modifica el estado
    del cÃ¡lculo ni se aplican cambios desde esta ruta.
    """
    try:
        from modules.tunnel.ai_assistant import ask, build_context

        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return jsonify({'success': False, 'error': 'La consulta no es vÃ¡lida.'}), 400
        supplied_context = payload.get('context')
        context = supplied_context if isinstance(supplied_context, dict) else build_context(
            payload.get('form') or {},
            payload.get('result') or {},
        )
        answer = ask(payload.get('question', ''), context)
        return jsonify({'success': True, 'answer': answer}), 200
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 503
    except Exception as exc:
        app.logger.exception('Error en el asistente de tÃºneles: %s', exc)
        return jsonify({
            'success': False,
            'error': 'No se pudo consultar el asistente. Revisa la configuraciÃ³n de IA.',
        }), 502


@app.route('/api/tunnel/recalc-scene', methods=['POST'])
def tunnel_recalc_scene():
    """Recalcula la verificacion CIE 140 de una sola escena con las
    consignas actuales (incluidas las manuales) sin re-optimizar
    corrientes. Es el flujo «edito mA en la lista y recalculo solo
    Crepuscular»: los datos de corriente del usuario no se mueven.
    """
    try:
        from modules.tunnel.luminaires import (
            tunnel_luminaire_result_from_dict,
            apply_scene_current_overrides,
        )
        from modules.tunnel.photometric_verify import (
            verify_layered_operating_scenario,
            verify_night_base_scenario,
        )
        data = request.get_json(silent=True) or {}
        scene_key = str(data.get('scene', 'dusk') or 'dusk').lower()
        lum_data = data.get('luminaires_result')
        if not isinstance(lum_data, dict) or not lum_data.get('zones'):
            return jsonify({
                'success': False,
                'error': 'Falta el resultado de luminarias calculado.',
            }), 400

        cie88 = run_tunnel_calculation(data)
        if not cie88.get('success'):
            return jsonify(cie88), 422

        lum_result = tunnel_luminaire_result_from_dict(lum_data)
        params = dict(data.get('luminaire', {}) or {})
        params['speed_kmh'] = float(data.get('speed_kmh', 80) or 80)
        params['Lth'] = float(cie88['summary'].get('Lth', 0) or 0)
        params['Lin'] = float(cie88['summary'].get('Lin', 0) or 0)
        params['L_night'] = float(
            cie88['summary'].get('L_night', 1.0) or 1.0,
        )
        params['Lth_b'] = float(
            cie88.get('lth', {}).get('Lth_b', params['Lth'])
            or params['Lth']
        )
        params['road_width_m'] = float(
            lum_data.get('road_width_m', data.get('road_width_m', 7.0))
            or 7.0
        )
        params['calc_mode'] = (
            'radiosity' if data.get('calc_mode', 'direct') == 'radiosity'
            else 'direct'
        )
        params['rho_wall'] = float(data.get('rho_wall', 0.40) or 0.40)
        params['rho_ceiling'] = float(
            data.get('rho_ceiling', 0.25) or 0.25,
        )

        warnings = apply_scene_current_overrides(
            lum_result,
            data.get('scene_current_overrides', {}) or {},
            I_min_pct=params.get('I_min_pct', 0.30),
        )
        if scene_key.startswith('night_'):
            verification = verify_night_base_scenario(
                lum_result, params, scene_key=scene_key,
            )
        else:
            verification = verify_layered_operating_scenario(
                lum_result, params, scene_key,
                include_ti=False,
                include_profile=True,
            )
        return jsonify({
            'success': True,
            'scene': scene_key,
            'verification': verification,
            'warnings': warnings,
        })
    except Exception as exc:
        import traceback
        app.logger.exception('Error recalculando escena: %s', exc)
        return jsonify({
            'success': False,
            'error': str(exc),
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/tunnel/luminaires', methods=['POST'])
def tunnel_luminaires():
    """
    Calcula el diseño de luminarias por zona (espaciado, nº, potencia).
    Body JSON:
        <parámetros normales del túnel>  +
        luminaire: { flux_lm, power_w, efficiency, mounting_height_m,
                     arrangement, maintenance_factor, name, road_surface }
        road_width_m: float
    """
    request_started = perf_counter()
    performance = {"stages_s": {}, "scenarios_s": {}, "counters": {}}
    try:
        from modules.tunnel.luminaires import (
            calculate_luminaire_layout,
            apply_manual_luminaire_overrides,
            apply_scene_current_overrides,
        )

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos JSON'}), 400

        # Calcular el túnel completo para obtener las zonas
        stage_started = perf_counter()
        result = run_tunnel_calculation(data)
        performance["stages_s"]["cie88"] = round(
            perf_counter() - stage_started, 4,
        )
        if not result.get('success'):
            return jsonify(result), 422

        zones_raw   = result.get('zones', {})
        zones_list  = list(zones_raw.values()) if isinstance(zones_raw, dict) else zones_raw

        luminaire_params = dict(data.get('luminaire', {}))
        # Pasar velocidad y luminancias CIE 88 al módulo de luminarias
        # para que pueda calcular el perfil exacto de la zona de transición
        luminaire_params['speed_kmh']      = float(data.get('speed_kmh', 80))
        luminaire_params['Lth']             = float(result['summary'].get('Lth', 0))
        luminaire_params['Lin']             = float(result['summary'].get('Lin', 0))
        luminaire_params['L_night']         = float(result['summary'].get('L_night', 1.0))
        luminaire_params['L_night_normal']  = float(result['summary'].get(
            'L_night_normal', result['summary'].get('Lin', 0),
        ))
        luminaire_params['L_night_reduced'] = float(result['summary'].get(
            'L_night_reduced', result['summary'].get('L_night', 1.0),
        ))
        luminaire_params['Lth_b']           = float(result.get('lth', {}).get('Lth_b', luminaire_params['Lth']))
        luminaire_params['tunnel_class']    = int(result.get('lth', {}).get('tunnel_class', 2) or 2)
        luminaire_params['wall_ratio_override'] = data.get('wall_ratio_override', '')
        luminaire_params['wall_luminance_height_m'] = float(
            data.get('wall_luminance_height_m', 2.0) or 2.0
        )
        luminaire_params['control_architecture'] = str(data.get(
            'control_architecture',
            'permanent_base_plus_portal_reinforcement',
        ))
        auto_physical_reoptimization = data.get(
            'auto_physical_reoptimization',
            luminaire_params.get('auto_physical_reoptimization', True),
        )
        if isinstance(auto_physical_reoptimization, str):
            auto_physical_reoptimization = (
                auto_physical_reoptimization.strip().lower()
                not in ('0', 'false', 'no', 'off')
            )
        luminaire_params['auto_physical_reoptimization'] = bool(
            auto_physical_reoptimization,
        )
        # Las ediciones de una posición o de una consigna describen un
        # proyecto que el usuario quiere conservar. La contingencia automática
        # nunca puede sustituir esas luminarias por otras ni moverlas.
        luminaire_params['_physical_layout_locked'] = bool(
            data.get('manual_luminaire_overrides', {})
            or data.get('scene_current_overrides', {})
            or luminaire_params.get('d_fixed') not in (None, '', 0, '0')
        )
        calculation_phase = str(
            data.get('calculation_phase', 'full') or 'full'
        ).lower()
        if calculation_phase not in ('base', 'full'):
            calculation_phase = 'full'
        luminaire_params['calculation_phase'] = calculation_phase
        luminaire_params['tilt_overrides']   = data.get('tilt_overrides', {}) or {}
        luminaire_params['tandem_overrides'] = data.get('tandem_overrides', {}) or {}
        luminaire_params['ta_design_c']      = float(data.get('ta_design_c', 20.0))
        # También se entregan al diseñador para que las comprobaciones
        # multiescena y la reoptimización física utilicen la misma modalidad
        # fotométrica que la validación final.
        luminaire_params['calc_mode'] = (
            'radiosity' if data.get('calc_mode', 'direct') == 'radiosity'
            else 'direct'
        )
        luminaire_params['rho_wall'] = float(data.get('rho_wall', 0.40))
        luminaire_params['rho_ceiling'] = float(data.get('rho_ceiling', 0.25))
        # d_min: viene del campo en LumConfigPanel, dentro de 'luminaire'
        if 'd_min' not in luminaire_params:
            luminaire_params['d_min'] = float(data.get('luminaire', {}).get('d_min', 1.0))
        # Parámetros de sección transversal — necesarios antes de calculate_luminaire_layout
        # para la validación is_inside_tunnel y para el flujo de wall_offset al optimizador
        luminaire_params['height_m']     = float(data.get('height_m',   5.5))
        luminaire_params['tunnel_shape'] = str(data.get('tunnel_shape', 'horseshoe'))
        luminaire_params['H_pared_m']    = float(data.get('H_pared_m',  3.0))
        luminaire_params['num_lanes'] = max(1, int(data.get('num_lanes', 1) or 1))
        luminaire_params['traffic_direction'] = str(data.get('traffic_direction', 'one_way'))
        luminaire_params['lane_width_m'] = float(
            data.get('lane_width_m', data.get('road_width_m', data.get('width_m', 7.0)))
        )
        luminaire_params['shoulder_left_m'] = float(data.get('shoulder_left_m', 0.0) or 0.0)
        luminaire_params['shoulder_right_m'] = float(data.get('shoulder_right_m', 0.0) or 0.0)
        luminaire_params['sidewalk_left_m'] = float(data.get('sidewalk_left_m', 0.0) or 0.0)
        luminaire_params['sidewalk_right_m'] = float(data.get('sidewalk_right_m', 0.0) or 0.0)
        luminaire_params['include_shoulders_in_luminance_grid'] = False
        # wall_offset_m viene dentro del objeto luminaire (LumConfigPanel)
        if 'wall_offset_m' not in luminaire_params:
            luminaire_params['wall_offset_m'] = float(data.get('luminaire', {}).get('wall_offset_m', 0.30))
        road_width_m     = float(data.get('road_width_m', data.get('width_m', 7.0)))
        tube_length_m    = float(result['summary'].get('length_m', 300))
        tube_id          = result['summary'].get('tube_id', 'T1')

        stage_started = perf_counter()
        lum_result = calculate_luminaire_layout(
            zones_list       = zones_list,
            luminaire_params = luminaire_params,
            road_width_m     = road_width_m,
            tube_length_m    = tube_length_m,
            tube_id          = tube_id,
        )
        manual_warnings = apply_manual_luminaire_overrides(
            lum_result,
            data.get('manual_luminaire_overrides', {}) or {},
        )
        if manual_warnings:
            lum_result.warnings.extend(manual_warnings)
        scene_current_warnings = apply_scene_current_overrides(
            lum_result,
            data.get('scene_current_overrides', {}) or {},
            I_min_pct=luminaire_params.get('I_min_pct', 0.30),
        )
        if scene_current_warnings:
            lum_result.warnings.extend(scene_current_warnings)
        performance["stages_s"]["luminaire_design"] = round(
            perf_counter() - stage_started, 4,
        )
        performance["design"] = getattr(
            lum_result, "performance", {},
        )
        performance["counters"]["physical_luminaires"] = sum(
            len(zone.setpoints or []) for zone in lum_result.zones
        )

        # ── Verificación fotométrica CIE 140:2019 ──────────────────────────
        photometric = {}
        try:
            from modules.tunnel.photometric_verify import (
                verify_luminaire_result, compute_real_luminance_profile,
                verify_layered_operating_scenario,
                verify_night_base_scenario,
                unify_zone_verification_with_profile,
            )
            use_rad = data.get('calc_mode', 'direct') == 'radiosity'
            luminaire_params['calc_mode'] = 'radiosity' if use_rad else 'direct'
            luminaire_params['rho_wall']    = float(data.get('rho_wall',    0.40))
            luminaire_params['rho_ceiling'] = float(data.get('rho_ceiling', 0.25))
            # height_m, wall_offset_m, tunnel_shape, H_pared_m ya están en luminaire_params
            stage_started = perf_counter()
            # La radiosidad que gobierna los resultados se calcula después por
            # cada campo CIE 140 y escena operativa. Esta verificación auxiliar
            # se mantiene directa para no sumar el antiguo promedio zonal.
            photometric = verify_luminaire_result(
                lum_result,
                luminaire_params,
                use_radiosity=False,
            )
            performance["stages_s"]["zone_verification"] = round(
                perf_counter() - stage_started, 4,
            )
            photometric['calc_mode'] = 'radiosity' if use_rad else 'direct'
            step_size = 1.0 if tube_length_m <= 500 else 2.0
            stage_started = perf_counter()
            sunny_verification = None
            if lum_result.architecture == (
                'permanent_base_plus_portal_reinforcement'
            ):
                # La gráfica debe ser la operación DALI soleada, no la suma de
                # todas las luminarias instaladas. En particular, la capa de
                # adaptación se mantiene apagada fuera de crepúsculo.
                sunny_verification = verify_layered_operating_scenario(
                    lum_result,
                    luminaire_params,
                    'sunny',
                    include_profile=True,
                )
                photometric['real_profile'] = sunny_verification.get(
                    'profile',
                )
                if photometric['real_profile'] is None:
                    photometric['real_profile'] = compute_real_luminance_profile(
                        lum_result, luminaire_params, road_width_m,
                        step_size=step_size,
                    )
            else:
                photometric['real_profile'] = compute_real_luminance_profile(
                    lum_result, luminaire_params, road_width_m,
                    step_size=step_size,
                )
            photometric = unify_zone_verification_with_profile(
                photometric,
                photometric['real_profile'],
                lum_result,
                luminaire_params,
            )
            performance["stages_s"]["sunny_profile"] = round(
                perf_counter() - stage_started, 4,
            )
            performance["sunny_profile"] = photometric[
                "real_profile"
            ].get("performance", {})
            if (
                lum_result.architecture == (
                    'permanent_base_plus_portal_reinforcement'
                )
                and calculation_phase == 'full'
            ):
                from concurrent.futures import ThreadPoolExecutor

                photometric.setdefault('scenarios', {})
                scenario_started = perf_counter()
                scenario_results = {
                    'sunny': sunny_verification or verify_layered_operating_scenario(
                        lum_result, luminaire_params, 'sunny',
                        existing_profile=photometric['real_profile'],
                    )
                }
                performance["scenarios_s"]["sunny"] = round(
                    perf_counter() - scenario_started, 4,
                )

                def _timed_day_scene(scene_key):
                    scene_started = perf_counter()
                    scene_result = verify_layered_operating_scenario(
                        lum_result,
                        luminaire_params,
                        scene_key,
                        include_profile=True,
                        include_ti=False,
                    )
                    return (
                        scene_result,
                        round(perf_counter() - scene_started, 4),
                    )

                def _timed_night_scene(scene_key):
                    scene_started = perf_counter()
                    scene_result = verify_night_base_scenario(
                        lum_result,
                        luminaire_params,
                        scene_key=scene_key,
                    )
                    return (
                        scene_result,
                        round(perf_counter() - scene_started, 4),
                    )

                # Las tres mallas intermedias y la nocturna son independientes.
                # Ejecutarlas en paralelo reduce sensiblemente el tiempo de
                # respuesta sin alterar la aritmética fotométrica.
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {
                        scene_key: executor.submit(
                            _timed_day_scene,
                            scene_key,
                        )
                        for scene_key in ('normal', 'overcast', 'dusk')
                    }
                    night_future = executor.submit(
                        _timed_night_scene, 'night',
                    )
                    night_normal_future = executor.submit(
                        _timed_night_scene, 'night_normal',
                    )
                    for scene_key, future in futures.items():
                        (
                            scenario_results[scene_key],
                            performance["scenarios_s"][scene_key],
                        ) = future.result()
                    (
                        night_verification,
                        performance["scenarios_s"]["night"],
                    ) = night_future.result()
                    (
                        night_normal_verification,
                        performance["scenarios_s"]["night_normal"],
                    ) = night_normal_future.result()

                for scene_key in ('sunny', 'normal', 'overcast', 'dusk'):
                    scene_verification = scenario_results[scene_key]
                    photometric['scenarios'][scene_key] = scene_verification
                    scene_summary = {
                        key: value
                        for key, value in scene_verification.items()
                        if key != 'profile'
                    }
                    lum_result.scenarios.setdefault(scene_key, {}).update({
                        'photometric': scene_summary,
                    })
                    if (
                        scene_verification.get('available')
                        and not scene_verification.get('compliant')
                    ):
                        lum_result.warnings.append(
                            f"Escena {scene_key}: la regulación con el "
                            "hardware máximo instalado no conserva todas "
                            "las restricciones "
                            f"(L/Lreq={scene_verification.get('minimum_L_ratio')}, "
                            f"Uo={scene_verification.get('minimum_U0')}, "
                            f"Ul={scene_verification.get('minimum_Ul')}). "
                            "Requiere escalonamiento de encendido validado "
                            "o un circuito de menor flujo."
                        )
                photometric['scenarios']['night'] = (
                    night_verification
                )
                photometric['scenarios']['night_reduced'] = (
                    night_verification
                )
                photometric['scenarios']['night_normal'] = (
                    night_normal_verification
                )
                night_summary = {
                    key: value
                    for key, value in night_verification.items()
                    if key not in ('profile', 'verification')
                }
                lum_result.scenarios.setdefault('night', {}).update(
                    {'photometric': night_summary}
                )
                lum_result.scenarios.setdefault('night_reduced', {}).update(
                    {'photometric': night_summary}
                )
                night_normal_summary = {
                    key: value
                    for key, value in night_normal_verification.items()
                    if key not in ('profile', 'verification')
                }
                lum_result.scenarios.setdefault('night_normal', {}).update(
                    {'photometric': night_normal_summary}
                )
                performance["scenario_profiles"] = {
                    scene_key: scenario_results[scene_key].get(
                        "profile_performance", {},
                    )
                    for scene_key in (
                        "sunny", "normal", "overcast", "dusk"
                    )
                }
                performance["scenario_profiles"]["night"] = (
                    night_verification.get("profile", {}).get(
                        "performance", {},
                    )
                )
                performance["scenario_profiles"]["night_normal"] = (
                    night_normal_verification.get("profile", {}).get(
                        "performance", {},
                    )
                )
            elif lum_result.architecture == (
                'permanent_base_plus_portal_reinforcement'
            ):
                photometric['control_validation_pending'] = True
                photometric.setdefault('scenarios', {})['status'] = {
                    'pending': True,
                    'message': (
                        'Diseño físico y escenario soleado calculados. '
                        'Falta la optimización y verificación DALI '
                        'multiescenario.'
                    ),
                }
        except Exception as pe:
            photometric = {"available": False, "error": str(pe)}

        performance["total_s"] = round(
            perf_counter() - request_started, 4,
        )
        photometric["performance"] = performance
        return jsonify({
            'success': True,
            'luminaires': lum_result.to_dict(),
            'photometric': photometric,
            'summary': result.get('summary', {}),
            'performance': performance,
        })

    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


def _quality_sensitivity_axis(raw_values, defaults, *, minimum, maximum):
    """Validate one editable U0/Ul sensitivity axis."""
    values = raw_values if isinstance(raw_values, list) else defaults
    if not 1 <= len(values) <= 5:
        raise ValueError('Cada eje de sensibilidad debe contener entre 1 y 5 valores.')
    parsed = []
    for raw in values:
        value = float(raw)
        if not minimum <= value <= maximum:
            raise ValueError(
                f'Los valores deben estar entre {minimum:.2f} y {maximum:.2f}.'
            )
        if value not in parsed:
            parsed.append(value)
    if not parsed:
        raise ValueError('El eje de sensibilidad no contiene valores válidos.')
    return parsed


@app.route('/api/tunnel/luminaires/sensitivity', methods=['POST'])
def tunnel_luminaire_quality_sensitivity():
    """Matrix of installed power and physical luminaire count by U0/Ul."""
    request_started = perf_counter()
    try:
        from modules.tunnel.luminaires import calculate_quality_sensitivity

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No se recibieron datos JSON',
            }), 400

        u0_values = _quality_sensitivity_axis(
            data.get('u0_values'),
            [0.40, 0.50, 0.60],
            minimum=0.10,
            maximum=0.90,
        )
        ul_values = _quality_sensitivity_axis(
            data.get('ul_values'),
            [0.60, 0.70, 0.80],
            minimum=0.10,
            maximum=0.95,
        )

        cie_result = run_tunnel_calculation(data)
        if not cie_result.get('success'):
            return jsonify(cie_result), 422
        zones_raw = cie_result.get('zones', {})
        zones_list = (
            list(zones_raw.values())
            if isinstance(zones_raw, dict)
            else zones_raw
        )

        luminaire_params = dict(data.get('luminaire', {}))
        luminaire_params.update({
            'speed_kmh': float(data.get('speed_kmh', 80)),
            'Lth': float(cie_result['summary'].get('Lth', 0)),
            'Lin': float(cie_result['summary'].get('Lin', 0)),
            'L_night': float(cie_result['summary'].get('L_night', 1.0)),
            'L_night_normal': float(cie_result['summary'].get(
                'L_night_normal', cie_result['summary'].get('Lin', 0),
            )),
            'L_night_reduced': float(cie_result['summary'].get(
                'L_night_reduced',
                cie_result['summary'].get('L_night', 1.0),
            )),
            'Lth_b': float(cie_result.get('lth', {}).get(
                'Lth_b', cie_result['summary'].get('Lth', 0),
            )),
            'control_architecture': str(data.get(
                'control_architecture',
                'permanent_base_plus_portal_reinforcement',
            )),
            'calculation_phase': 'base',
            'tilt_overrides': data.get('tilt_overrides', {}) or {},
            'tandem_overrides': data.get('tandem_overrides', {}) or {},
            'manual_luminaire_overrides': data.get(
                'manual_luminaire_overrides', {},
            ) or {},
            'ta_design_c': float(data.get('ta_design_c', 20.0)),
            'height_m': float(data.get('height_m', 5.5)),
            'tunnel_shape': str(data.get('tunnel_shape', 'horseshoe')),
            'H_pared_m': float(data.get('H_pared_m', 3.0)),
            'num_lanes': max(1, int(data.get('num_lanes', 1) or 1)),
            'traffic_direction': str(data.get(
                'traffic_direction', 'one_way',
            )),
            'lane_width_m': float(data.get(
                'lane_width_m',
                data.get('road_width_m', data.get('width_m', 7.0)),
            )),
            'shoulder_left_m': float(
                data.get('shoulder_left_m', 0.0) or 0.0
            ),
            'shoulder_right_m': float(
                data.get('shoulder_right_m', 0.0) or 0.0
            ),
            'sidewalk_left_m': float(data.get('sidewalk_left_m', 0.0) or 0.0),
            'sidewalk_right_m': float(data.get('sidewalk_right_m', 0.0) or 0.0),
            'include_shoulders_in_luminance_grid': False,
        })
        luminaire_params.setdefault(
            'd_min',
            float(data.get('luminaire', {}).get('d_min', 1.0)),
        )
        luminaire_params.setdefault(
            'wall_offset_m',
            float(data.get('luminaire', {}).get('wall_offset_m', 0.30)),
        )

        road_width_m = float(
            data.get('road_width_m', data.get('width_m', 7.0))
        )
        tube_length_m = float(
            cie_result['summary'].get('length_m', 300)
        )
        tube_id = cie_result['summary'].get('tube_id', 'T1')
        matrix = calculate_quality_sensitivity(
            zones_list=zones_list,
            luminaire_params=luminaire_params,
            road_width_m=road_width_m,
            tube_length_m=tube_length_m,
            tube_id=tube_id,
            u0_values=u0_values,
            ul_values=ul_values,
            reference_layout=data.get('luminaires_result', {}) or {},
            # Las celdas son diseños independientes. Ejecutarlas en paralelo
            # evita que una matriz de 3x3 bloquee la interfaz durante varios
            # ciclos secuenciales del optimizador.
            max_workers=min(9, len(u0_values) * len(ul_values)),
        )
        matrix['active'] = {
            'U0': round(float(
                data.get('luminaire', {}).get('U0_obj', 0.40)
            ), 3),
            'Ul': round(float(
                data.get('luminaire', {}).get('Ul_obj', 0.60)
            ), 3),
        }
        matrix['optimization_goal'] = str(
            luminaire_params.get('optimization_goal', 'min_luminaires')
        )
        matrix['request_elapsed_s'] = round(
            perf_counter() - request_started, 3,
        )
        return jsonify({'success': True, 'sensitivity': matrix})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:
        import traceback
        return jsonify({
            'success': False,
            'error': str(exc),
            'traceback': traceback.format_exc(),
        }), 500


@app.route('/api/tunnel/report', methods=['POST'])
def tunnel_report():
    """
    Genera el informe técnico Word (CIE 88:2004 + CIE 140:2019) y lo devuelve como descarga.
    Body JSON: mismos parámetros que /api/tunnel/calculate, más opcionalmente
    los parámetros de luminarias (luminaire.*) para incluir verificación CIE 140.
    """
    try:
        import io

        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No se recibieron datos JSON'}), 400

        report_version = str(data.get('report_version', 'v1')).lower()
        if report_version == 'v2':
            from modules.tunnel.report_v2 import generate_report_v2 as generate_report
        else:
            from modules.tunnel.report import generate_report

        # Calcular resultado CIE 88 completo
        result = run_tunnel_calculation(data)
        if not result.get('success'):
            return jsonify(result), 422

        # ── Verificación fotométrica CIE 140 (si hay parámetros de luminaria) ──
        photometric = None
        luminaire_result = None

        # El botón de informe recibe el último cálculo validado por el usuario.
        # Reutilizarlo garantiza que el Word documenta exactamente las mallas,
        # escenarios y reglajes que se ven en pantalla, y evita volver a lanzar
        # un cálculo completo de varios escenarios al descargar el archivo.
        cached_photometric = data.get('photometric_result')
        cached_luminaire = data.get('luminaires_result')
        if (
            isinstance(cached_photometric, dict)
            and isinstance(cached_luminaire, dict)
            and cached_luminaire.get('zones')
            and _luminaire_cache_matches_request(cached_luminaire, data)
        ):
            photometric = cached_photometric
            luminaire_result = cached_luminaire
            docx_bytes = generate_report(
                result,
                data,
                photometric=photometric,
                luminaire=luminaire_result,
            )
            tube_id = result.get('summary', {}).get('tube_id', 'T1')
            return send_file(
                io.BytesIO(docx_bytes),
                as_attachment=True,
                download_name=f"informe_tunel_{tube_id}{'_v2' if report_version == 'v2' else ''}.docx",
                mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
        try:
            from modules.tunnel.luminaires import calculate_luminaire_layout
            from modules.tunnel.photometric_verify import (
                compute_real_luminance_profile,
                unify_zone_verification_with_profile,
                verify_luminaire_result,
            )

            luminaire_raw = (
                data.get('luminaire')
                or data.get('lum_config')
                or {}
            )
            if luminaire_raw.get('I_max_mA') or luminaire_raw.get('cct'):
                luminaire_params = dict(luminaire_raw)
                luminaire_params['speed_kmh'] = float(data.get('speed_kmh', 80))
                luminaire_params['Lth']       = float(result['summary'].get('Lth', 0))
                luminaire_params['Lin']       = float(result['summary'].get('Lin', 0))
                luminaire_params['L_night']   = float(result['summary'].get('L_night', 1.0))
                luminaire_params['L_night_normal'] = float(result['summary'].get(
                    'L_night_normal', result['summary'].get('Lin', 0),
                ))
                luminaire_params['L_night_reduced'] = float(result['summary'].get(
                    'L_night_reduced', result['summary'].get('L_night', 1.0),
                ))
                luminaire_params['Lth_b']     = float(result.get('lth', {}).get('Lth_b', luminaire_params['Lth']))
                luminaire_params['control_architecture'] = str(data.get(
                    'control_architecture',
                    'permanent_base_plus_portal_reinforcement',
                ))
                luminaire_params['tandem_overrides'] = (
                    data.get('tandem_overrides', {}) or {}
                )
                luminaire_params['ta_design_c'] = float(data.get('ta_design_c', 20.0))
                luminaire_params['height_m'] = float(data.get('height_m', 5.5))
                luminaire_params['tunnel_shape'] = str(data.get('tunnel_shape', 'horseshoe'))
                luminaire_params['H_pared_m'] = float(data.get('H_pared_m', 3.0))
                luminaire_params['mounting_height_m'] = float(
                    luminaire_params.get(
                        'mounting_height_m',
                        data.get('mounting_height_m', 5.0),
                    )
                )
                luminaire_params['num_lanes'] = max(
                    1, int(data.get('num_lanes', 1) or 1),
                )
                luminaire_params['lane_width_m'] = float(
                    data.get(
                        'lane_width_m',
                        data.get('road_width_m', data.get('width_m', 7.0)),
                    )
                )
                luminaire_params['shoulder_left_m'] = float(
                    data.get('shoulder_left_m', 0.0) or 0.0
                )
                luminaire_params['shoulder_right_m'] = float(
                    data.get('shoulder_right_m', 0.0) or 0.0
                )
                luminaire_params['sidewalk_left_m'] = float(
                    data.get('sidewalk_left_m', 0.0) or 0.0
                )
                luminaire_params['sidewalk_right_m'] = float(
                    data.get('sidewalk_right_m', 0.0) or 0.0
                )
                luminaire_params['include_shoulders_in_luminance_grid'] = False
                luminaire_params['traffic_direction'] = str(
                    data.get('traffic_direction', 'one_way')
                )
                luminaire_params['tilt_overrides'] = (
                    data.get('tilt_overrides', {}) or {}
                )
                luminaire_params['rho_wall'] = float(data.get('rho_wall', 0.40))
                luminaire_params['rho_ceiling'] = float(data.get('rho_ceiling', 0.25))
                # El informe debe reconstruir exactamente el mismo modo que
                # gobierna las curvas de la fase Luminarias, no sólo marcarlo
                # en la cabecera de resultados.
                luminaire_params['calc_mode'] = (
                    'radiosity'
                    if data.get('calc_mode', 'direct') == 'radiosity'
                    else 'direct'
                )
                luminaire_params['U0_obj'] = float(
                    luminaire_params.get(
                        'U0_obj', data.get('U0_obj', 0.40),
                    ) or 0.40
                )
                luminaire_params['Ul_obj'] = float(
                    luminaire_params.get(
                        'Ul_obj', data.get('Ul_obj', 0.60),
                    ) or 0.60
                )
                luminaire_params['TI_max'] = float(
                    luminaire_params.get(
                        'TI_max', data.get('TI_max', 15.0),
                    ) or 15.0
                )

                zones_raw  = result.get('zones', {})
                zones_list = list(zones_raw.values()) if isinstance(zones_raw, dict) else zones_raw
                road_width = float(data.get('road_width_m', data.get('width_m', 7.0)))
                tube_len   = float(result['summary'].get('length_m', 300))
                tube_id_l  = result['summary'].get('tube_id', 'T1')

                lum_result = calculate_luminaire_layout(
                    zones_list       = zones_list,
                    luminaire_params = luminaire_params,
                    road_width_m     = road_width,
                    tube_length_m    = tube_len,
                    tube_id          = tube_id_l,
                )
                luminaire_result = lum_result.to_dict()
                use_radiosity = data.get('calc_mode', 'direct') == 'radiosity'
                # El perfil físico posterior resuelve la radiosidad por campo;
                # no usar aquí el atajo zonal heredado del informe.
                photometric = verify_luminaire_result(
                    lum_result,
                    luminaire_params,
                    use_radiosity=False,
                )
                photometric['calc_mode'] = 'radiosity' if use_radiosity else 'direct'
                profile = compute_real_luminance_profile(
                    lum_result,
                    luminaire_params,
                    road_width,
                    step_size=1.0 if tube_len <= 500 else 2.0,
                )
                photometric['real_profile'] = profile
                photometric = unify_zone_verification_with_profile(
                    photometric,
                    profile,
                    lum_result,
                    luminaire_params,
                )
        except Exception as exc:
            app.logger.exception(
                'No se ha podido recalcular CIE 140 para el informe Word: %s', exc
            )
            photometric = None  # El informe indicará explícitamente que falta CIE 140.

        # Generar documento Word
        docx_bytes = generate_report(
            result,
            data,
            photometric=photometric,
            luminaire=luminaire_result,
        )

        tube_id = result.get('summary', {}).get('tube_id', 'T1')
        filename = f"informe_tunel_{tube_id}{'_v2' if report_version == 'v2' else ''}.docx"

        return send_file(
            io.BytesIO(docx_bytes),
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )

    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500


@app.route('/api/tunnel/osm-proxy', methods=['POST'])
def tunnel_osm_proxy():
    """
    Proxy servidor->Overpass usando urllib (stdlib, sin dependencias externas).
    Body JSON: { "query": "<QL string>" }
    Prueba 3 endpoints en orden; devuelve el primero que responda.
    """
    import urllib.request
    import urllib.parse
    import urllib.error
    import json as _json

    ENDPOINTS = [
        'https://overpass-api.de/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter',
        'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
    ]
    TIMEOUT = 28  # segundos

    try:
        body = request.get_json(silent=True) or {}
        query = body.get('query', '')
        if not query:
            return jsonify({'success': False, 'error': 'Falta el parametro "query"'}), 400

        last_err = 'Sin respuesta'
        for ep in ENDPOINTS:
            try:
                # Overpass espera POST con parámetro de formulario "data=<query>"
                post_data = urllib.parse.urlencode({'data': query}).encode('utf-8')
                req = urllib.request.Request(
                    ep, data=post_data,
                    headers={'User-Agent': 'SALVI-TunnelEngine/1.0',
                             'Content-Type': 'application/x-www-form-urlencoded'}
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    raw = resp.read()
                    return jsonify(_json.loads(raw))
            except urllib.error.HTTPError as e:
                last_err = f'HTTP {e.code} desde {ep}'
            except urllib.error.URLError as e:
                last_err = f'Timeout/red en {ep}: {e.reason}'
            except Exception as exc:
                last_err = f'{ep}: {exc}'

        return jsonify({'success': False, 'error': f'Overpass no disponible. {last_err}'}), 502

    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e),
                        'traceback': traceback.format_exc()}), 500


@app.route('/api/tunnel/climate-ta', methods=['POST'])
def tunnel_climate_ta():
    """
    Sugiere la temperatura ambiente media anual [°C] en las coordenadas
    dadas, para usar como Ta de diseño del motor LED (evaluar la reduccion
    media de eficiencia — no es un limite de seguridad, por eso se usa la
    media anual y no un maximo historico; ver modules/tunnel/led_engine.py).

    Fuente: Open-Meteo Archive API (histórico ERA5, sin API key). Se
    promedian los ultimos 5 años naturales completos.
    Body JSON: { "lat": float, "lng": float }
    """
    import urllib.request
    import urllib.parse
    import urllib.error
    import json as _json

    try:
        body = request.get_json(silent=True) or {}
        lat = float(body.get('lat'))
        lng = float(body.get('lng'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'lat/lng invalidos o ausentes'}), 400

    end_year   = datetime.now().year - 1
    start_year = end_year - 4
    params = urllib.parse.urlencode({
        'latitude': lat, 'longitude': lng,
        'start_date': f'{start_year}-01-01', 'end_date': f'{end_year}-12-31',
        'daily': 'temperature_2m_mean', 'timezone': 'auto',
    })
    url = f'https://archive-api.open-meteo.com/v1/archive?{params}'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'SALVI-TunnelEngine/1.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = _json.loads(resp.read())
        values = [v for v in data.get('daily', {}).get('temperature_2m_mean', []) if v is not None]
        if not values:
            return jsonify({'success': False, 'error': 'Sin datos climaticos para esa ubicacion'}), 502
        ta_mean_c = sum(values) / len(values)
        return jsonify({
            'success': True,
            'ta_mean_c': round(ta_mean_c, 1),
            'years': [start_year, end_year],
            'n_days': len(values),
        })
    except urllib.error.URLError as e:
        return jsonify({'success': False, 'error': f'Open-Meteo no disponible: {e.reason}'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/debug/files', methods=['GET'])
def debug_files():
    """Debug endpoint para verificar que los archivos estan accesibles"""
    assets_folder = os.path.join(os.path.dirname(__file__), 'assets')
    files_info = {}
    if os.path.exists(assets_folder):
        for f in os.listdir(assets_folder):
            fp = os.path.join(assets_folder, f)
            files_info[f] = {'size': os.path.getsize(fp), 'exists': True}

    download_folder = os.path.join(os.path.dirname(__file__), 'downloads')
    downloads = []
    if os.path.exists(download_folder):
        downloads = os.listdir(download_folder)

    return jsonify({
        'assets': files_info,
        'downloads': downloads,
        'upload_folder': UPLOAD_FOLDER,
        'download_folder': DOWNLOAD_FOLDER,
    })


@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'success': False, 'error': 'Archivo demasiado grande (max 50MB)'}), 413

if __name__ == '__main__':
    # El reloader de Werkzeug reinicia el proceso si OneDrive sincroniza un
    # fichero durante un cálculo largo. Eso aborta la petición HTTP y la SPA
    # parece que "deja de calcular". Mantenemos el modo debug para los
    # diagnósticos, pero el proceso solo se reinicia al relanzar el BAT.
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
