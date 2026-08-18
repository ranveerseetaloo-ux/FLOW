"""Customer CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Customer
from ..schemas import CustomerIn, CustomerOut
from .auth import require

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("", response_model=list[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    return db.scalars(select(Customer).order_by(Customer.id)).all()


@router.post("", response_model=CustomerOut, status_code=201)
def create_customer(body: CustomerIn, db: Session = Depends(get_db), _=Depends(require("operator"))):
    if db.scalar(select(Customer).where(Customer.ref == body.ref)):
        raise HTTPException(409, "customer ref already exists")
    c = Customer(**body.model_dump())
    db.add(c)
    db.commit()
    return c


@router.get("/{cid}", response_model=CustomerOut)
def get_customer(cid: int, db: Session = Depends(get_db)):
    c = db.get(Customer, cid)
    if not c:
        raise HTTPException(404, "not found")
    return c


@router.delete("/{cid}", status_code=204)
def delete_customer(cid: int, db: Session = Depends(get_db), _=Depends(require("admin"))):
    c = db.get(Customer, cid)
    if c:
        db.delete(c)
        db.commit()
