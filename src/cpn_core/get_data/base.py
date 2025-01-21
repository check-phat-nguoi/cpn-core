from abc import abstractmethod
from logging import getLogger
from typing import Self, final

from aiohttp import ClientError

from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum

logger = getLogger(__name__)


class BaseGetDataEngine:
    def __init__(self, *, timeout: float) -> None:
        self._timeout: float = timeout

    @property
    def api(self) -> ApiEnum:
        raise NotImplementedError("The engine must define API")

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None: ...

    @abstractmethod
    async def _get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None: ...

    @final
    async def get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        try:
            return await self._get_data(plate_info)
        except TimeoutError as e:
            logger.error(
                "Plate %s: Time out (%ds) getting data from API %s. %s",
                plate_info.plate,
                self._timeout,
                self.api.value,
                e,
            )
        except ClientError as e:
            logger.error(
                "Plate %s: Error occurs while getting data from API %s. %s",
                plate_info.plate,
                self.api.value,
                e,
            )
        except Exception as e:
            logger.error(
                "Plate %s: Error occurs while getting data (internal) %s. %s",
                plate_info.plate,
                self.api.value,
                e,
            )
