"""
Configuración global de pytest para Salvi Columns.
Tests de aceptación usan ASGI transport (sin BD real en CI).
Tests de integración requieren BD de test (ver pytest-asyncio docs).
"""
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: tests que requieren base de datos real"
    )
