import json
from datetime import datetime
from logging import getLogger
from typing import (
    Final,
    Literal,
    LiteralString,
    Self,
    TypeAlias,
    TypedDict,
    cast,
    override,
)

from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    VehicleStrVieType,
    VehicleTypeEnum,
    get_vehicle_enum,
)
from cpn_core.utils.request_session_helper import RequestSessionHelper

API_URL: LiteralString = "https://api.checkphatnguoi.vn/phatnguoi"
RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"

logger = getLogger(__name__)

_DataResponse = TypedDict(
    "_DataResponse",
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
        "data": tuple[_DataResponse, ...],
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
    def __init__(self, plate_info: PlateInfo, plate_detail_dict: _Response) -> None:
        self._plate_info: PlateInfo = plate_info
        self._vehicle_type: VehicleTypeEnum = get_vehicle_enum(plate_info.type)
        self._plate_detail_typed: _Response = plate_detail_dict
        self._violation_details_set: set[ViolationDetail] = set()

    def _parse_violation(self, data: _DataResponse) -> None:
        type: VehicleStrVieType = data["Loại phương tiện"]
        # NOTE: this is for filtering the vehicle that doesn't match the plate info type. Because checkphatnguoi.vn return all of the type of the plate
        parsed_type: VehicleTypeEnum = get_vehicle_enum(type)
        if parsed_type != self._vehicle_type:
            logger.info(
                "Plate %s: The violation doesn't match the input vehicle type %s",
                self._plate_info.plate,
                self._vehicle_type,
            )
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
            # Have to cast to string because lsp's warning
            date=datetime.strptime(str(date), RESPONSE_DATETIME_FORMAT),
            location=location,
            violation=violation,
            status=status == "Đã xử phạt",
            enforcement_unit=enforcement_unit,
            resolution_offices=resolution_offices,
        )
        self._violation_details_set.add(violation_detail)

    def parse(self) -> tuple[ViolationDetail, ...] | None:
        if self._plate_detail_typed["status"] == 2:
            logger.info(
                "Plate %s: Don't have any violations",
                self._plate_info.plate,
            )
            return ()
        if self._plate_detail_typed["status"] != 1:
            logger.error(
                "Plate %s: Unknown Error with status = 1 from API",
                self._plate_info.plate,
            )
            return
        for violation in self._plate_detail_typed["data"]:
            self._parse_violation(violation)
        return tuple(self._violation_details_set)


class CheckPhatNguoiEngine(BaseGetDataEngine, RequestSessionHelper):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.phatnguoi_vn

    headers: Final[dict[str, str]] = {"Content-Type": "application/json"}

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def _request(self, plate_info: PlateInfo) -> dict | None:
        payload: Final[dict[str, str]] = {"bienso": plate_info.plate}
        async with self._session.post(
            API_URL,
            headers=self.headers,
            json=payload,
        ) as response:
            response.raise_for_status()
            response_data: bytes = await response.read()
            return json.loads(response_data)

    @override
    async def _get_data(
        self,
        plate_info: PlateInfo,
    ) -> tuple[ViolationDetail, ...] | None:
        plate_detail_raw: dict | None = await self._request(plate_info)
        if not plate_detail_raw:
            return
        plate_detail_typed: _Response = cast(_Response, plate_detail_raw)
        violations: tuple[ViolationDetail, ...] | None = _CheckPhatNguoiParseEngine(
            plate_info=plate_info, plate_detail_dict=plate_detail_typed
        ).parse()
        return violations

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await RequestSessionHelper.__aexit__(self, exc_type, exc_value, exc_traceback)
