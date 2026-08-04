"""
Salvi Studio · Columns — Seed de datos mínimos de demostración.

Idempotente: puede ejecutarse varias veces sin duplicar filas (upsert por
código/email único). Pensado para poder probar el flujo end-to-end desde el
frontend sin depender de catálogo, materiales o geodatos reales todavía.

Uso:
    docker exec backend-api-1 python scripts/seed_demo_data.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import Role, hash_password

# Importar todos los módulos de modelos, igual que migrations/env.py, para que
# SQLAlchemy pueda resolver relaciones cruzadas (p.ej. User.audit_entries -> AuditLog)
# al configurar los mappers.
import app.models.db.users        # noqa: F401
import app.models.db.projects     # noqa: F401
import app.models.db.libraries    # noqa: F401
import app.models.db.audit        # noqa: F401
import app.models.db.geometry     # noqa: F401
import app.models.db.actions      # noqa: F401
import app.models.db.structural   # noqa: F401
import app.models.db.steel        # noqa: F401
import app.models.db.aluminium    # noqa: F401
import app.models.db.concrete     # noqa: F401
import app.models.db.details      # noqa: F401
import app.models.db.joints       # noqa: F401
import app.models.db.baseplate    # noqa: F401
import app.models.db.foundation   # noqa: F401
import app.models.db.catalog      # noqa: F401
import app.models.db.optimization # noqa: F401
import app.models.db.cad_bom      # noqa: F401
import app.models.db.reports      # noqa: F401
import app.models.db.catenary     # noqa: F401
import app.models.db.validation   # noqa: F401

from app.models.db.users import User, UserRole
from app.models.db.steel import SteelProductProperty, SteelGrade, SteelSubgrade, SteelProductForm
from app.models.db.catalog import ProductFamily, StandardProduct

DEMO_EMAIL = "demo@salvi.es"
DEMO_PASSWORD = "salvi-demo-2026"
DEMO_FULL_NAME = "Usuario de demostración"


async def seed_demo_user(session) -> User:
    result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
    user = result.scalar_one_or_none()
    if user:
        print(f"  usuario demo ya existe: {DEMO_EMAIL}")
        return user

    user = User(
        email=DEMO_EMAIL,
        full_name=DEMO_FULL_NAME,
        hashed_password=hash_password(DEMO_PASSWORD),
        preferred_language="es",
        preferred_unit_system="SI",
        is_active=True,
        is_sso=False,
    )
    session.add(user)
    await session.flush()

    for role in (Role.SYSTEM_ADMIN, Role.ENGINEER, Role.TECHNICAL_OFFICE, Role.COMMERCIAL):
        session.add(UserRole(user_id=user.id, role=role, granted_by_id=user.id))

    print(f"  usuario demo creado: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return user


STEEL_GRADES = [
    # (grade, subgrade, fy_mpa, fu_mpa)
    (SteelGrade.S235, SteelSubgrade.JR, 235.0, 360.0),
    (SteelGrade.S275, SteelSubgrade.JR, 275.0, 430.0),
    (SteelGrade.S355, SteelSubgrade.J2, 355.0, 470.0),
]


async def seed_steel_materials(session) -> None:
    for grade, subgrade, fy, fu in STEEL_GRADES:
        result = await session.execute(
            select(SteelProductProperty).where(
                SteelProductProperty.steel_grade == grade,
                SteelProductProperty.subgrade == subgrade,
            )
        )
        if result.scalar_one_or_none():
            print(f"  material {grade.value} {subgrade.value} ya existe")
            continue

        session.add(
            SteelProductProperty(
                product_norm="EN 10025-2",
                steel_grade=grade,
                subgrade=subgrade,
                product_form=SteelProductForm.HOT_TUBE,
                supply_condition="AR",
                thickness_min_mm=3.0,
                thickness_max_mm=16.0,
                fy_mpa=fy,
                fu_mpa=fu,
            )
        )
        print(f"  material sembrado: {grade.value} {subgrade.value} (fy={fy} MPa)")


DEMO_FAMILY_CODE = "COL-ACERO-DEMO"
DEMO_PRODUCT_CODE = "SAL-9M-114-4"


async def seed_catalog_product(session) -> None:
    result = await session.execute(
        select(ProductFamily).where(ProductFamily.code == DEMO_FAMILY_CODE)
    )
    family = result.scalar_one_or_none()
    if not family:
        family = ProductFamily(
            code=DEMO_FAMILY_CODE,
            name="Columna de acero — familia de demostración",
            material="steel",
            has_hierarchy=False,
            is_third_party=False,
        )
        session.add(family)
        await session.flush()
        print(f"  familia de catálogo creada: {DEMO_FAMILY_CODE}")
    else:
        print(f"  familia de catálogo ya existe: {DEMO_FAMILY_CODE}")

    result = await session.execute(
        select(StandardProduct).where(
            StandardProduct.family_id == family.id,
            StandardProduct.code == DEMO_PRODUCT_CODE,
        )
    )
    if result.scalar_one_or_none():
        print(f"  producto de catálogo ya existe: {DEMO_PRODUCT_CODE}")
        return

    session.add(
        StandardProduct(
            family_id=family.id,
            code=DEMO_PRODUCT_CODE,
            name="Columna acero 9 m, D114mm, e4mm — demo",
            nominal_height_m=9.0,
            base_type="plate",
            material_grade="S275",
        )
    )
    print(f"  producto de catálogo sembrado: {DEMO_PRODUCT_CODE}")


async def main() -> None:
    print("Sembrando datos mínimos de demostración…")
    async with AsyncSessionLocal() as session:
        try:
            await seed_demo_user(session)
            await seed_steel_materials(session)
            await seed_catalog_product(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    print("Listo.")


if __name__ == "__main__":
    asyncio.run(main())
