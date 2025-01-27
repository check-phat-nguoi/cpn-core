from abc import abstractmethod
from logging import getLogger
from typing import Self

from httpx import StreamError, TimeoutException

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

    async def get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        try:
            # TODO: No None later
            violation_details: (
                tuple[ViolationDetail, ...] | None
            ) = await self._get_data(plate_info)
            if not violation_details:
                logger.info(
                    "Plate %s - %s: Don't have any violation",
                    plate_info.plate,
                    self.api,
                )
            return violation_details
        except TimeoutException as e:
            logger.error(
                "Plate %s - %s: Time out (%ds) getting data from API. %s",
                plate_info.plate,
                self.api.value,
                self._timeout,
                e,
            )
        except StreamError as e:
            logger.error(
                "Plate %s - %s: Error occured. %s",
                plate_info.plate,
                self.api.value,
                e,
            )
        # TODO: catch custom exception in main later
        except Exception as e:
            logger.error(
                "Plate %s - %s: Error occurs while getting data (internal). %s",
                plate_info.plate,
                self.api.value,
                e,
            )
