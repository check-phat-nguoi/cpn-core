import json
from datetime import datetime
from logging import getLogger
from typing import Literal, LiteralString, Self, TypedDict, cast, override

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import get_vehicle_enum

logger = getLogger(__name__)

RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"
API_URL: LiteralString = (
    "https://api.zm.io.vn/v1/csgt/tracuu?licensePlate={plate}&vehicleType={type}"
)


class _DataPlateInfoResponse(TypedDict):
    bienkiemsoat: str
    maubien: str
    loaiphuongtien: Literal["Ô tô", "Xe máy", "Xe máy điện"]
    thoigianvipham: str
    diadiemvipham: str
    trangthai: str
    donviphathienvipham: str
    noigiaiquyetvuviec: str


class _DataResponse(TypedDict):
    json: tuple[_DataPlateInfoResponse, ...] | None
    html: str
    css: str


class _Response(TypedDict):
    time_end: int
    data: _DataResponse
    error: bool


class _ZmioParseEngine:
    def __init__(
        self,
        plate_info: PlateInfo,
        data: tuple[_DataPlateInfoResponse, ...],
    ) -> None:
        self._plate_info: PlateInfo = plate_info
        self._data: tuple[_DataPlateInfoResponse, ...] = data
        self._violation_details_set: set[ViolationDetail] = set()

    def _parse_violation(self, data: _DataPlateInfoResponse) -> None:
        plate: str = data["bienkiemsoat"]
        date: str = data["thoigianvipham"]
        type: Literal["Ô tô", "Xe máy", "Xe máy điện"] = data["loaiphuongtien"]
        color: str = data["maubien"]
        location: str = data["diadiemvipham"]
        status: str = data["trangthai"]
        enforcement_unit: str = data["donviphathienvipham"]
        # NOTE: this api just responses 1 resolution_office
        resolution_offices: tuple[str, ...] = (data["noigiaiquyetvuviec"],)
        violation_detail: ViolationDetail = ViolationDetail(
            plate=plate,
            color=color,
            type=get_vehicle_enum(type),
            date=datetime.strptime(str(date), RESPONSE_DATETIME_FORMAT),
            location=location,
            status=status == "Đã xử phạt",
            enforcement_unit=enforcement_unit,
            resolution_offices=resolution_offices,
            violation=None,
        )
        self._violation_details_set.add(violation_detail)

    def parse(self) -> tuple[ViolationDetail, ...] | None:
        for violations in self._data:
            self._parse_violation(violations)
        return tuple(self._violation_details_set)


class ZmioEngine(BaseGetDataEngine, RequestSessionHelper):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.zm_io_vn

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def _request(self, plate_info: PlateInfo) -> _Response | None:
        url: str = API_URL.format(
            plate=plate_info.plate, type=get_vehicle_enum(plate_info.type)
        )
        async with self._session.stream("GET", url) as response:
            content = await response.aread()
            data = json.loads(content.decode("utf-8"))
            plate_detail_typed: _Response = cast(_Response, data)
            return plate_detail_typed

    @override
    async def _get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        plate_detail_typed: _Response | None = await self._request(plate_info)
        if not plate_detail_typed:
            return
        if plate_detail_typed["data"] is None:
            logger.error(
                "Plate %s: Cannot get data",
                plate_info.plate,
            )
            return
        if plate_detail_typed["data"]["json"] is None:
            logger.info(
                "Plate %s: Not found or don't have any violations",
                plate_info.plate,
            )
            return ()
        violation_details: tuple[ViolationDetail, ...] | None = _ZmioParseEngine(
            plate_info=plate_info, data=plate_detail_typed["data"]["json"]
        ).parse()
        return violation_details

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await RequestSessionHelper.__aexit__(self, exc_type, exc_value, exc_traceback)
