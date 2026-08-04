#!/usr/bin/env python
"""
Módulo de visualización de isocurvas fotométricas
Genera gráficos de Iluminancia y Luminancia con escala de colores
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from io import BytesIO
import base64

class VisualizacionFotometrica:
    """Genera visualizaciones de cálculos fotométricos"""

    # Paleta de colores para isocurvas (Azul -> Verde -> Amarillo -> Rojo)
    COLORES = ['#0040FF', '#0080FF', '#00FF00', '#FFFF00', '#FF8000', '#FF0000']

    def __init__(self, data, resultados):
        """
        Inicializa con datos del proyecto y resultados
        """
        self.data = data
        self.resultados = resultados
        self.altura = float(data.get('altura_montaje', 6))
        self.interdistancia = float(data.get('interdistancia', 15))
        self.ancho_calzada = float(data.get('calzada1_ancho', 7))

    def generar_malla_isocurvas(self, valor_total, num_isolineas=6):
        """
        Genera una malla de datos para isocurvas

        Simula distribución luminosa basada en:
        - Distancia a luminarias
        - Efecto de dispersión (gaussiano aproximado)
        """
        # Crear malla de puntos sobre la calzada
        x = np.linspace(0, self.ancho_calzada, 50)
        y = np.linspace(0, self.interdistancia * 2, 100)
        X, Y = np.meshgrid(x, y)

        # Simular distribución gaussiana desde dos luminarias
        # Luminaria 1 en (ancho/2, 0)
        # Luminaria 2 en (ancho/2, interdistancia)
        sigma_x = self.ancho_calzada / 2
        sigma_y = self.interdistancia / 1.5

        lum1_x = self.ancho_calzada / 2
        lum1_y = 0
        lum2_x = self.ancho_calzada / 2
        lum2_y = self.interdistancia

        # Distribución gaussiana 2D
        dist1 = np.sqrt((X - lum1_x)**2 + (Y - lum1_y)**2)
        dist2 = np.sqrt((X - lum1_x)**2 + (Y - lum2_y)**2)

        gauss1 = np.exp(-dist1**2 / (2 * sigma_x**2))
        gauss2 = np.exp(-dist2**2 / (2 * sigma_x**2))

        # Combinar con factor de uniformidad
        Z = valor_total * (0.5 * gauss1 + 0.5 * gauss2)

        # Añadir variación de uniformidad
        uo = self.resultados.get('Uo', 0.45)
        z_min = valor_total * uo
        z_max = valor_total
        Z = z_min + (Z - Z.min()) * (z_max - z_min) / (Z.max() - Z.min())

        return X, Y, Z

    def crear_grafico_iluminancia(self):
        """Crea gráfico de isocurvas de iluminancia"""
        try:
            em = self.resultados.get('Em_lux', 0)

            if em == 0:
                return None

            X, Y, Z = self.generar_malla_isocurvas(em, num_isolineas=6)

            fig, ax = plt.subplots(figsize=(12, 8), dpi=100)

            # Crear mapa de colores personalizado
            cmap = LinearSegmentedColormap.from_list('fotometrico', self.COLORES)

            # Contornos (isolíneas)
            niveles = np.linspace(Z.min(), Z.max(), 6)
            cs = ax.contour(X, Y, Z, levels=niveles, colors='black', linewidths=1.5, alpha=0.4)
            ax.clabel(cs, inline=True, fontsize=9, fmt='%.1f')

            # Relleno con colores
            cf = ax.contourf(X, Y, Z, levels=20, cmap=cmap, alpha=0.8)

            # Colorbar (leyenda)
            cbar = plt.colorbar(cf, ax=ax, label='Iluminancia (lux)')
            cbar.set_label('Iluminancia [lux]', rotation=270, labelpad=20, fontsize=11, fontweight='bold')

            # Etiquetas
            ax.set_xlabel('Ancho de calzada [m]', fontsize=11, fontweight='bold')
            ax.set_ylabel('Longitud (a lo largo de la calle) [m]', fontsize=11, fontweight='bold')
            ax.set_title(
                f'Distribución de Iluminancia - {self.data.get("nombre_proyecto", "Proyecto")}\n'
                f'Em = {em:.2f} lux | Uo = {self.resultados.get("Uo", 0):.3f}',
                fontsize=13, fontweight='bold', pad=20
            )

            # Grid
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.set_aspect('equal')

            plt.tight_layout()

            # Convertir a imagen (bytes)
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            plt.close()

            return buffer

        except Exception as e:
            print(f"Error al crear gráfico de iluminancia: {str(e)}")
            return None

    def crear_grafico_luminancia(self):
        """Crea gráfico de isocurvas de luminancia"""
        try:
            luminancia = self.resultados.get('luminancia_media', 0)

            if luminancia == 0:
                return None

            X, Y, Z = self.generar_malla_isocurvas(luminancia, num_isolineas=6)

            fig, ax = plt.subplots(figsize=(12, 8), dpi=100)

            # Crear mapa de colores personalizado
            cmap = LinearSegmentedColormap.from_list('fotometrico', self.COLORES)

            # Contornos (isolíneas)
            niveles = np.linspace(Z.min(), Z.max(), 6)
            cs = ax.contour(X, Y, Z, levels=niveles, colors='black', linewidths=1.5, alpha=0.4)
            ax.clabel(cs, inline=True, fontsize=9, fmt='%.2f')

            # Relleno con colores
            cf = ax.contourf(X, Y, Z, levels=20, cmap=cmap, alpha=0.8)

            # Colorbar (leyenda)
            cbar = plt.colorbar(cf, ax=ax, label='Luminancia (cd/m²)')
            cbar.set_label('Luminancia [cd/m²]', rotation=270, labelpad=20, fontsize=11, fontweight='bold')

            # Etiquetas
            ax.set_xlabel('Ancho de calzada [m]', fontsize=11, fontweight='bold')
            ax.set_ylabel('Longitud (a lo largo de la calle) [m]', fontsize=11, fontweight='bold')
            ax.set_title(
                f'Distribución de Luminancia - {self.data.get("nombre_proyecto", "Proyecto")}\n'
                f'L = {luminancia:.2f} cd/m² | Uo = {self.resultados.get("Uo", 0):.3f} | Ul = {self.resultados.get("Ul", 0):.3f}',
                fontsize=13, fontweight='bold', pad=20
            )

            # Grid
            ax.grid(True, alpha=0.3, linestyle='--')
            ax.set_aspect('equal')

            plt.tight_layout()

            # Convertir a imagen (bytes)
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            plt.close()

            return buffer

        except Exception as e:
            print(f"Error al crear gráfico de luminancia: {str(e)}")
            return None

    def grafico_a_base64(self, buffer):
        """Convierte buffer de imagen a string base64 para HTML"""
        if not buffer:
            return None

        buffer.seek(0)
        image_data = buffer.read()
        return base64.b64encode(image_data).decode('utf-8')

    def grafico_a_bytes(self, buffer):
        """Retorna bytes del gráfico para guardar como archivo"""
        if not buffer:
            return None

        buffer.seek(0)
        return buffer.getvalue()

def generar_graficos_isocurvas(data, resultados):
    """Función helper para usar desde Flask"""
    try:
        viz = VisualizacionFotometrica(data, resultados)

        # Generar gráficos
        grafico_iluminancia = viz.crear_grafico_iluminancia()
        grafico_luminancia = viz.crear_grafico_luminancia()

        # Convertir a base64 para HTML
        img_iluminancia_b64 = viz.grafico_a_base64(grafico_iluminancia) if grafico_iluminancia else None
        img_luminancia_b64 = viz.grafico_a_base64(grafico_luminancia) if grafico_luminancia else None

        # Guardar como bytes para PDF
        grafico_iluminancia.seek(0) if grafico_iluminancia else None
        grafico_luminancia.seek(0) if grafico_luminancia else None

        return {
            'success': True,
            'iluminancia_b64': img_iluminancia_b64,
            'luminancia_b64': img_luminancia_b64,
            'iluminancia_bytes': viz.grafico_a_bytes(grafico_iluminancia) if grafico_iluminancia else None,
            'luminancia_bytes': viz.grafico_a_bytes(grafico_luminancia) if grafico_luminancia else None,
        }
    except Exception as e:
        print(f"Error generando gráficos: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
