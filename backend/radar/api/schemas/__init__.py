"""Request and response models, grouped by the surface that uses them."""

from radar.api.schemas.auth import LoginIn, OpsLoginIn
from radar.api.schemas.company import CompanyIn, CompanyOut
from radar.api.schemas.competitors import (
    CompetitorIn,
    CompetitorOut,
    CompetitorPatch,
    DiscoverIn,
    SourceIn,
    SourceSummary,
    WatchPageIn,
)
from radar.api.schemas.inbox import (
    AssessmentOut,
    FeedbackIn,
    FeedbackOut,
    InboxPage,
    ItemCard,
    ItemDetail,
)
from radar.api.schemas.ops import GoldenIn, GoldenManualIn, PromptIn, SourcePatch
from radar.api.schemas.teams import TeamOut, TeamPatch
from radar.api.schemas.topics import TopicIn, TopicOut

__all__ = [
    "AssessmentOut",
    "CompanyIn",
    "CompanyOut",
    "CompetitorIn",
    "CompetitorOut",
    "CompetitorPatch",
    "DiscoverIn",
    "FeedbackIn",
    "FeedbackOut",
    "GoldenIn",
    "GoldenManualIn",
    "InboxPage",
    "ItemCard",
    "ItemDetail",
    "LoginIn",
    "OpsLoginIn",
    "PromptIn",
    "SourceIn",
    "SourcePatch",
    "SourceSummary",
    "TeamOut",
    "TeamPatch",
    "TopicIn",
    "TopicOut",
    "WatchPageIn",
]
