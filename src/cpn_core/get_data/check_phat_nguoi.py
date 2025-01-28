import json
from datetime import datetime
from logging import getLogger
from typing import (
    Final,
    Literal,
    LiteralString,
    TypeAlias,
    TypedDict,
    cast,
    override,
)

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.exceptions.get_data import ServerResponseFail
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    VehicleStrVieType,
    VehicleTypeEnum,
    get_vehicle_enum,
)

API_URL: LiteralString = "https://api.checkphatnguoi.vn/phatnguoi"
RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"

logger = getLogger(__name__)

_ResponseData = TypedDict(
    "_ResponseData",
    {
        "Biển kiểm soát": str,
        "Màu biển": str,
        "Loại phương tiện": Literal["Ô tô", "Xe máy", "Xe máy điện"],
        "Thời gian vi phạm": str,
        "Địa điểm vi phạm": str,
        "Hành vi vi phạm": str,
        "Trạng thái": Literal["Đã xử phạt", "Chưa xử phạt"],
        "Đơn vị phát hiện vi phạm": str,
        "Nơi giải quyết vụ việc": tuple[str, ...],
    },
)

_DataPlateInfoResponse = TypedDict(
    "_DataPlateInfoResponse",
    {
        "total": int,
        "chuaxuphat": Literal[0, 1],
        "daxuphat": Literal[0, 1],
        "latest": str,
    },
)

_FoundResponse = TypedDict(
    "_FoundResponse",
    {
        "status": Literal[1],
        "msg": str,
        "data": tuple[_ResponseData, ...],
    },
)


_NotFoundResponse = TypedDict(
    "_NotFoundResponse",
    {
        "status": Literal[2],
        "data": None,
    },
)

_Response: TypeAlias = _FoundResponse | _NotFoundResponse


class _CheckPhatNguoiParseEngine:
    def __init__(self, filter_type: VehicleTypeEnum, response: _Response) -> None:
        self._filter_type: VehicleTypeEnum = filter_type
        self._response: _Response = response

    def _parse_violation(self, data: _ResponseData) -> ViolationDetail | None:
        type: VehicleStrVieType = data["Loại phương tiện"]
        # NOTE: this is for filtering the vehicle that doesn't match the plate info type. Because checkphatnguoi.vn return all of the type of the plate
        parsed_type: VehicleTypeEnum = get_vehicle_enum(type)
        if parsed_type != self._filter_type:
            return
        plate: str = data["Biển kiểm soát"]
        date: str = data["Thời gian vi phạm"]
        color: str = data["Màu biển"]
        location: str = data["Địa điểm vi phạm"]
        violation: str = data["Hành vi vi phạm"]
        status: str = data["Trạng thái"]
        enforcement_unit: str = data["Đơn vị phát hiện vi phạm"]
        resolution_offices: tuple[str, ...] = data["Nơi giải quyết vụ việc"]
        violation_detail: ViolationDetail = ViolationDetail(
            plate=plate,
            color=color,
            type=parsed_type,
            date=datetime.strptime(str(date), RESPONSE_DATETIME_FORMAT),
            location=location,
            violation=violation,
            status=status == "Đã xử phạt",
            enforcement_unit=enforcement_unit,
            resolution_offices=resolution_offices,
        )
        return violation_detail

    def parse(self) -> tuple[ViolationDetail, ...]:
        if self._response["status"] == 2:
            return ()
        if self._response["status"] != 1:
            raise ServerResponseFail("Server responsed status other than success :(")
        return tuple(
            not_none_violation
            for violation in self._response["data"]
            if (not_none_violation := self._parse_violation(violation)) is not None
        )


class _CheckPhatNguoiRequestEngine(RequestSessionHelper):
    _headers: Final[dict[str, str]] = {"Content-Type": "application/json"}

    def __init__(self, *, timeout: float = 20) -> None:
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def request(self, plate_info: PlateInfo) -> _Response:
        payload: Final[dict[str, str]] = {"bienso": plate_info.plate}
        async with self._session.stream(
            "POST",
            API_URL,
            headers=self._headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            content: bytes = await response.aread()
            response_data = json.loads(content.decode("utf-8"))
            return cast(_Response, response_data)


class CheckPhatNguoiEngine(BaseGetDataEngine):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.phatnguoi_vn

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)
        self._request_engine: _CheckPhatNguoiRequestEngine = (
            _CheckPhatNguoiRequestEngine()
        )

    @override
    async def _get_data(
        self,
        plate_info: PlateInfo,
    ) -> tuple[ViolationDetail, ...]:
        response: _Response = await self._request_engine.request(plate_info)
        violation_details: tuple[ViolationDetail, ...] = _CheckPhatNguoiParseEngine(
            filter_type=get_vehicle_enum(plate_info.type), response=response
        ).parse()
        return violation_details

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await self._request_engine.__aexit__(exc_type, exc_value, exc_traceback)
        await BaseGetDataEngine.__aexit__(self, exc_type, exc_value, exc_traceback)
