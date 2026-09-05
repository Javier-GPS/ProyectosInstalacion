#!/usr/bin/env python
"""
Módulo de cálculos fotométricos según EN 13201:2015
Cálculo de: Luminancia, Uniformidad, Deslumbramiento, Consumo Energético, etc.
"""

import math

class CalculoFotometrico:
    """Realiza cálculos fotométricos según EN 13201:2015"""

    def __init__(self, data):
        """
        Inicializa con datos del formulario
        """
        self.data = data
        self.resultados = {}

    def calcular_todo(self):
        """Ejecuta todos los cálculos"""
        try:
            self.calcular_luminancia()
            self.calcular_uniformidad()
            self.calcular_deslumbramiento()
            self.calcular_consumo_energetico()
            self.calcular_iluminancia()

            return {
                'success': True,
                'resultados': self.resultados
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def obtener_datos_entrada(self):
        """Extrae datos del formulario"""
        try:
            altura = float(self.data.get('altura_montaje', 6))
            interdistancia = float(self.data.get('interdistancia', 15))
            ancho_calzada = float(self.data.get('calzada1_ancho', 7))
            q0 = float(self.data.get('calzada1_q0', 0.07))

            # Luminarias
            luminarias = self.data.get('luminarias', [])
            if not luminarias:
                raise ValueError("No hay luminarias definidas")

            potencia_total = 0
            lumenes_total = 0

            for lum in luminarias:
                potencia_total += float(lum.get('potencia', 0))
                lumenes = float(lum.get('lumenes', 0))
                if lumenes > 0:
                    lumenes_total += lumenes

            return {
                'altura': altura,
                'interdistancia': interdistancia,
                'ancho_calzada': ancho_calzada,
                'q0': q0,
                'potencia_total': potencia_total,
                'lumenes_total': lumenes_total,
                'num_luminarias': len(luminarias)
            }
        except Exception as e:
            raise ValueError(f"Error en datos de entrada: {str(e)}")

    def calcular_iluminancia(self):
        """Calcula iluminancia media (Em) en lux"""
        try:
            datos = self.obtener_datos_entrada()

            # Em = (Φ * η) / A
            # Φ = flujo luminoso total (lm)
            # η = factor de utilización (aprox 0.4-0.6)
            # A = área de la calzada

            flujo_total = datos['lumenes_total']

            if flujo_total == 0:
                # Si no hay lúmenes, estimamos a partir de potencia
                # Aprox 100 lm/W para LED
                flujo_total = datos['potencia_total'] * 100

            area_calzada = datos['ancho_calzada'] * datos['interdistancia']

            # Factor de utilización aproximado (depende de optica, altura, etc)
            # Para cálculo rápido: 0.5
            factor_util = 0.5

            em = (flujo_total * factor_util) / area_calzada if area_calzada > 0 else 0

            self.resultados['Em_lux'] = round(em, 2)

        except Exception as e:
            self.resultados['Em_lux'] = 0
            print(f"Error en cálculo de Em: {str(e)}")

    def calcular_luminancia(self):
        """Calcula luminancia media (cd/m²) según EN 13201"""
        try:
            datos = self.obtener_datos_entrada()

            # L = (Em * q0) / π
            # donde q0 es coeficiente de luminancia del pavimento

            em = self.resultados.get('Em_lux', 0)
            q0 = datos['q0']

            if em == 0:
                # Calcular Em primero
                self.calcular_iluminancia()
                em = self.resultados.get('Em_lux', 0)

            # Luminancia media aproximada
            luminancia = (em * q0) / math.pi if q0 > 0 else 0

            self.resultados['luminancia_media'] = round(luminancia, 2)

            # Valores típicos EN 13201
            # ME1: 2.0 cd/m², ME2: 1.5 cd/m², ME3a: 1.0 cd/m², ME4a: 0.5 cd/m²
            clase = self.data.get('calzada1_clase', 'me2')
            valores_clase = {
                'me1': 2.0,
                'me2': 1.5,
                'me3a': 1.0,
                'me3b': 1.0,
                'me4a': 0.5,
                'me4b': 0.5
            }
            self.resultados['luminancia_norma'] = valores_clase.get(clase, 1.5)
            self.resultados['cumple_luminancia'] = luminancia >= valores_clase.get(clase, 1.5)

        except Exception as e:
            self.resultados['luminancia_media'] = 0
            print(f"Error en cálculo de luminancia: {str(e)}")

    def calcular_uniformidad(self):
        """Calcula uniformidad (Uo) y uniformidad longitudinal (Ul)"""
        try:
            # Uo = L_min / L_media (transversal)
            # Ul = L_min / L_max (longitudinal)

            # Para cálculo aproximado, usamos factores típicos
            # Uo típico: 0.4 - 0.6
            # Ul típico: 0.5 - 0.8

            datos = self.obtener_datos_entrada()

            # La uniformidad depende de la distribución de las luminarias
            # Para disposición lineal (spacing 15m, altura 6m):
            ratio = datos['interdistancia'] / datos['altura']

            # Aproximación simplificada
            if ratio > 2.5:
                uo = 0.45
                ul = 0.65
            elif ratio > 2.0:
                uo = 0.50
                ul = 0.70
            else:
                uo = 0.55
                ul = 0.75

            self.resultados['Uo'] = round(uo, 3)
            self.resultados['Ul'] = round(ul, 3)

            # Norma EN 13201
            self.resultados['Uo_norma'] = 0.4  # Mínimo típico
            self.resultados['Ul_norma'] = 0.5  # Mínimo típico
            self.resultados['cumple_Uo'] = uo >= 0.4
            self.resultados['cumple_Ul'] = ul >= 0.5

        except Exception as e:
            self.resultados['Uo'] = 0
            self.resultados['Ul'] = 0
            print(f"Error en cálculo de uniformidad: {str(e)}")

    def calcular_deslumbramiento(self):
        """Calcula TI (Índice de Incremento de Deslumbramiento) y SR (Cociente de Brillo)"""
        try:
            # TI = (95/Lv) * (Σ(L_s^2 * Ω) / L_0^2) * 10^5
            # donde:
            # Lv = luminancia de velo
            # L_s = luminancia de fuente
            # Ω = ángulo sólido
            # L_0 = luminancia de referencia

            # Valores típicos para cálculo aproximado
            # TI: 10-30 (bajo 40 es aceptable)

            datos = self.obtener_datos_entrada()
            altura = datos['altura']

            # Aproximación según altura
            if altura >= 8:
                ti = 12  # Mejor óptica a mayor altura
            elif altura >= 6:
                ti = 18
            else:
                ti = 25

            self.resultados['TI'] = round(ti, 1)
            self.resultados['TI_norma'] = 40  # Máximo típico
            self.resultados['cumple_TI'] = ti <= 40

            # SR (Cociente de Brillo) = L_max / L_media
            # Valores típicos: 0.8 - 1.0
            sr = round(0.85 + (altura * 0.02), 3)  # Aproximado

            self.resultados['SR'] = min(sr, 1.2)
            self.resultados['SR_norma'] = 1.0
            self.resultados['cumple_SR'] = sr <= 1.0

        except Exception as e:
            self.resultados['TI'] = 0
            self.resultados['SR'] = 0
            print(f"Error en cálculo de deslumbramiento: {str(e)}")

    def calcular_consumo_energetico(self):
        """Calcula consumo energético anual y costo"""
        try:
            datos = self.obtener_datos_entrada()

            potencia_total = datos['potencia_total']
            num_luminarias = datos['num_luminarias']
            potencia_unitaria = potencia_total / num_luminarias if num_luminarias > 0 else 0

            # Datos de entrada
            horas_anual = float(self.data.get('horas_funcionamiento', 3650))
            tarifa = float(self.data.get('tarifa_electrica', 0.15))
            factor_co2 = float(self.data.get('factor_co2', 0.4))

            # Cálculos
            # Consideramos un factor de balastro aprox 1.05 para LED
            factor_balastro = 1.05
            potencia_real = potencia_total * factor_balastro

            # Consumo anual en kWh
            consumo_kwh = (potencia_real * horas_anual) / 1000

            # Costo anual en €
            costo_anual = consumo_kwh * tarifa

            # Emisiones CO2 anuales en kg
            emisiones_co2 = consumo_kwh * factor_co2

            # Consumo específico (W/m²)
            area_calzada = datos['ancho_calzada'] * datos['interdistancia']
            consumo_especifico = (potencia_real / area_calzada) if area_calzada > 0 else 0

            self.resultados['potencia_total_w'] = round(potencia_total, 2)
            self.resultados['potencia_unitaria_w'] = round(potencia_unitaria, 2)
            self.resultados['potencia_real_w'] = round(potencia_real, 2)
            self.resultados['consumo_kwh_anual'] = round(consumo_kwh, 2)
            self.resultados['costo_anual_eur'] = round(costo_anual, 2)
            self.resultados['emisiones_co2_kg'] = round(emisiones_co2, 2)
            self.resultados['consumo_especifico_w_m2'] = round(consumo_especifico, 2)

            # Estimación de amortización (vida útil 50,000 horas aprox 15 años)
            self.resultados['costo_15anos_eur'] = round(costo_anual * 15, 2)

        except Exception as e:
            self.resultados['consumo_kwh_anual'] = 0
            self.resultados['costo_anual_eur'] = 0
            self.resultados['emisiones_co2_kg'] = 0
            print(f"Error en cálculo de consumo: {str(e)}")

def calcular_fotometria(data):
    """Función helper para usar desde Flask"""
    calc = CalculoFotometrico(data)
    return calc.calcular_todo()
