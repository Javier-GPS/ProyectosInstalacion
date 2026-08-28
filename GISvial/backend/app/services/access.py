"""Project-scope authorization for new GIS job endpoints."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import GisProjectMembership, GisZone, Project
from ..routers.deps import Principal


def project_for(principal: Principal, db: Session, project_id: int, *, write: bool = False) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    if principal.user.role == "ADMIN" or project.owner_user_id == principal.user.id:
        return project
    membership = db.query(GisProjectMembership).filter(
        GisProjectMembership.project_id == project_id,
        GisProjectMembership.issuer == principal.issuer,
        GisProjectMembership.subject == principal.subject,
        GisProjectMembership.active.is_(True),
    ).first()
    if membership is not None and (not write or membership.role in {"owner", "editor", "admin"}):
        return project
    raise HTTPException(status_code=403, detail="Project membership required")


def can_project_write(principal: Principal, db: Session, project_id: int) -> bool:
    try:
        project_for(principal, db, project_id, write=True)
        return True
    except HTTPException:
        return False


def zone_for(principal: Principal, db: Session, zone_id: str, *, write: bool = False) -> GisZone:
    zone = db.get(GisZone, zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found")
    if zone.project_id is None:
        if principal.user.role != "ADMIN":
            raise HTTPException(status_code=403, detail="Zone is not assigned to a project")
        return zone
    project_for(principal, db, zone.project_id, write=write)
    return zone
