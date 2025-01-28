import json
from datetime import datetime
from logging import getLogger
from typing import Literal, LiteralString, TypedDict, cast, override

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.exceptions.get_data import ServerResponseFail
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


class _ResponseData(TypedDict):
    json: tuple[_DataPlateInfoResponse, ...] | None
    html: str
    css: str


class _Response(TypedDict):
    time_end: int
    data: _ResponseData
    error: bool


class _ZmioParseEngine:
    def __init__(
        self,
        data: tuple[_DataPlateInfoResponse, ...],
    ) -> None:
        self._data: tuple[_DataPlateInfoResponse, ...] = data

    def _parse_violation(self, data: _DataPlateInfoResponse) -> ViolationDetail:
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
        return violation_detail

    def parse(self) -> tuple[ViolationDetail, ...]:
        return tuple(self._parse_violation(violations) for violations in self._data)


class _ZmioRequestEngine(RequestSessionHelper):
    def __init__(self, *, timeout: float = 20) -> None:
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def request(self, plate_info: PlateInfo) -> _Response:
        url: str = API_URL.format(
            plate=plate_info.plate, type=get_vehicle_enum(plate_info.type).value
        )
        async with self._session.stream("GET", url) as response:
            content: bytes = await response.aread()
            data = json.loads(content.decode("utf-8"))
            return cast(_Response, data)


class ZmioEngine(BaseGetDataEngine):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.zm_io_vn

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)
        self._request_engine: _ZmioRequestEngine = _ZmioRequestEngine(timeout=timeout)

    @override
    async def _get_data(self, plate_info: PlateInfo) -> tuple[ViolationDetail, ...]:
        response: _Response = await self._request_engine.request(plate_info)
        if response["data"] is None:
            raise ServerResponseFail("Cannot get data")
        data: tuple[_DataPlateInfoResponse, ...] | None = response["data"]["json"]
        if data is None:
            return ()
        violation_details: tuple[ViolationDetail, ...] = _ZmioParseEngine(
            data=data
        ).parse()
        return violation_details
