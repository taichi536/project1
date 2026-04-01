from .doda import DodaPlatform
from .bizreach import BizreachPlatform
from .mynavi import MynaviPlatform
from .green import GreenPlatform
from .ambi import AmbiPlatform
from .dodax import DodaxPlatform
from .recruit_direct import RecruitDirectPlatform
from .base import BasePlatform

PLATFORM_CLASSES = {
    "doda": DodaPlatform,
    "bizreach": BizreachPlatform,
    "mynavi": MynaviPlatform,
    "green": GreenPlatform,
    "ambi": AmbiPlatform,
    "dodax": DodaxPlatform,
    "recruit_direct": RecruitDirectPlatform,
}

__all__ = [
    "BasePlatform",
    "DodaPlatform",
    "BizreachPlatform",
    "MynaviPlatform",
    "GreenPlatform",
    "AmbiPlatform",
    "DodaxPlatform",
    "RecruitDirectPlatform",
    "PLATFORM_CLASSES",
]
