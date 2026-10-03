"""What we sell. Edited by the business; read by every scoring call."""

from fastapi import APIRouter

from radar.api.deps import DB, BusinessRole
from radar.api.schemas import CompanyIn, CompanyOut
from radar.services import company as company_svc

router = APIRouter(prefix="/company", tags=["company"])


@router.get("", response_model=CompanyOut)
def get_company(db: DB, _: BusinessRole):
    return CompanyOut(text=company_svc.get_profile(db), is_default=company_svc.is_default(db))


@router.put("", response_model=CompanyOut)
def put_company(body: CompanyIn, db: DB, _: BusinessRole):
    text = company_svc.set_profile(db, body.text)
    return CompanyOut(text=text, is_default=company_svc.is_default(db))
