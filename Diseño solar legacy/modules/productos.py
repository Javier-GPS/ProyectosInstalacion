#!/usr/bin/env python3
"""Product library access."""
from modules.db import get_all_products as _get_all, get_product as _get

def get_all_products():
    return _get_all()

def get_product(pid):
    return _get(pid)
