from logging import getLogger
from typing import Final, Literal, LiteralString, TypedDict, cast, override

from curl_cffi import requests

from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import get_vehicle_enum

from .base import BaseGetDataEngine

logger = getLogger(__name__)
API_TOKEN_URL = "https://etraffic.gtelict.vn/api/citizen/v2/auth/login"
API_URL = "https://etraffic.gtelict.vn/api/citizen/v2/property/deferred/fines"

RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"


# TODO: Handle after because out of request
class _DataPlateInfoResponse(TypedDict): ...


class _FoundResponse(TypedDict):
    tag: Literal["found_response"]
    status: int
    message: str
    data: list[_DataPlateInfoResponse]


class _LimitResponse(TypedDict):
    tag: Literal["limit_response"]
    guid: str
    code: str
    message: Literal[
        "Số lượt tìm kiếm thông tin phạt nguội đã đạt giới hạn trong ngày.\nVui lòng thử lại sau"
    ]
    status: int
    path: str
    method: str
    timestamp: str
    error: str | None


_Response = _LimitResponse | _FoundResponse


class _EtrafficGetDataParseEngine:
    def __init__(
        self, plate_info: PlateInfo, data: tuple[_DataPlateInfoResponse, ...]
    ) -> None:
        self._plate_info = plate_info
        self._data = data
        self._violations_details_set = set()

    def _parse_violation(self, data: _DataPlateInfoResponse) -> None:
        plate: str
        date: str
        type: Literal["Ô tô", "Xe máy", "Xe máy điện"]
        color: str
        location: str
        status: str
        enforcement_unit: str
        resolution_offices: tuple[str, ...]
        violation_detail: ViolationDetail = ViolationDetail()
        self._violations_details_set.add(violation_detail)

    def parse(self) -> tuple[ViolationDetail, ...] | None:
        for violations in self._data:
            self._parse_violation(violations)
        return tuple(self._violations_details_set)


class EtrafficGetDataEngine(BaseGetDataEngine):
    api = ApiEnum.etraffic_gtelict_vn
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "C08_CD/1.1.8 (com.ots.global.vneTrafic; build:32; iOS 18.2.1) Alamofire/5.10.2",
    }

    def __init__(self, citizen_indentify: str, password: str, time_out: float) -> None:
        self._citizen_indetify = citizen_indentify
        self._password = password
        self._time_out = time_out

    def _request_token(self) -> str | None:
        data: Final[dict[str, str]] = {
            "citizenIndentify": self._citizen_indetify,
            "password": self._password,
        }
        try:
            response = requests.post(
                url=API_TOKEN_URL,
                headers=self.headers,
                json=data,
                allow_redirects=False,
                verify=False,
            )
            data_dict = response.json()
            return data_dict["value"]["refreshToken"]
        except Exception as e:
            # TODO: Handle exception later
            print(e)

    def _request(self, plate_info: PlateInfo) -> dict | None:
        headers: Final[dict[str, str]] = {
            "Authorization": f"Bearer {self._request_token()}",
            "User-Agent": "C08_CD/1.1.8 (com.ots.global.vneTrafic; build:32; iOS 18.2.1) Alamofire/5.10.2",
        }
        params: Final[dict[str, str]] = {
            "licensePlate": plate_info.plate,
            "type": f"{get_vehicle_enum(plate_info.type)}",
        }
        try:
            response = requests.get(url=API_URL, headers=headers, params=params)
            return response.json()
        except Exception as e:
            print(e)

    @override
    async def get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        plate_detail_raw = self._request(plate_info)
        if not plate_detail_raw:
            return
        plate_detail_typed = cast(_Response, plate_detail_raw)
        if plate_detail_typed["tag"] == "limit_response":
            logger.error("You are limited to send more requests")
            return
        violation_details: tuple[ViolationDetail, ...] | None = (
            _EtrafficGetDataParseEngine(
                plate_info=plate_info, data=tuple(plate_detail_typed["data"])
            ).parse()
        )
        return violation_details
