from fastapi import APIRouter

from radar.api.deps import DB, BusinessRole
from radar.api.serializers.inbox import overview as serialize_overview
from radar.assess.prompts import CATEGORY_LABELS
from radar.services import inbox as inbox_svc

router = APIRouter(tags=["overview"])


@router.get("/overview")
def overview(db: DB, _: BusinessRole):
    return serialize_overview(inbox_svc.overview(db))


@router.get("/categories")
def categories(_: BusinessRole):
    return [{"key": key, "label": label} for key, label in CATEGORY_LABELS.items()]
