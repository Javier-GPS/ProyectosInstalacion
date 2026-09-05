"""
Tunnel CRUD router.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...db.database import get_db
from ...db.models import Tunnel
from ..schemas import TunnelCreate, TunnelRead

router = APIRouter(prefix="/tunnels", tags=["tunnels"])


@router.post("/", response_model=TunnelRead, status_code=status.HTTP_201_CREATED)
def create_tunnel(body: TunnelCreate, db: Session = Depends(get_db)):
    t = Tunnel(**body.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.get("/", response_model=list[TunnelRead])
def list_tunnels(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Tunnel).offset(skip).limit(limit).all()


@router.get("/{tunnel_id}", response_model=TunnelRead)
def get_tunnel(tunnel_id: int, db: Session = Depends(get_db)):
    t = db.get(Tunnel, tunnel_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return t


@router.put("/{tunnel_id}", response_model=TunnelRead)
def update_tunnel(tunnel_id: int, body: TunnelCreate, db: Session = Depends(get_db)):
    t = db.get(Tunnel, tunnel_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    for k, v in body.model_dump().items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/{tunnel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tunnel(tunnel_id: int, db: Session = Depends(get_db)):
    t = db.get(Tunnel, tunnel_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    db.delete(t)
    db.commit()
