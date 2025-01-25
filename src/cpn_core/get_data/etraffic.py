from datetime import datetime
from logging import getLogger
from typing import Final, Literal, LiteralString, TypedDict, cast, override

from curl_cffi import CurlError, requests

from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import get_vehicle_enum

from .base import BaseGetDataEngine

logger = getLogger(__name__)
API_TOKEN_URL = "https://etraffic.gtelict.vn/api/citizen/v2/auth/login"
API_URL = "https://etraffic.gtelict.vn/api/citizen/v2/property/deferred/fines"

RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"


class _DataPlateInfoResponse(TypedDict):
    violationId: str | None
    licensePlate: str
    licensePlateType: str
    vehicleType: Literal["Ô tô con", "Xe máy", "Xe máy điện"]
    vehicleTypeText: Literal["Ô tô con", "Xe máy", "Xe máy điện"]
    violationType: str | None
    violationTypeText: str
    violationAt: str
    violationAtText: str
    violationAddress: str
    handlingAddress: str
    propertyName: str
    statusType: Literal["Đã xử phạt", "Chưa xử phạt"]
    statusTypeText: Literal["Đã xử phạt", "Chưa xử phạt"]
    departmentName: str
    contactPhone: str


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
        plate: str = data["licensePlate"]
        date: str = data["violationAt"]
        type: Literal["Ô tô con", "Xe máy", "Xe máy điện"] = data["vehicleType"]
        color: str = data["licensePlateType"]
        location: str = data["handlingAddress"]
        status: str = data["statusType"]
        enforcement_unit: str = data["propertyName"]
        resolution_offices: tuple[str, ...] = tuple(data["departmentName"])
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
        self._violations_details_set.add(violation_detail)

    def parse(self) -> tuple[ViolationDetail, ...] | None:
        for violations in self._data:
            self._parse_violation(violations)
        return tuple(self._violations_details_set)


class EtrafficEngine(BaseGetDataEngine):
    @property
    def api(self):
        """The api property."""
        return ApiEnum.etraffic_gtelict_vn

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "C08_CD/1.1.8 (com.ots.global.vneTrafic; build:32; iOS 18.2.1) Alamofire/5.10.2",
    }

    def __init__(
        self, citizen_indentify: str, password: str, time_out: float = 10
    ) -> None:
        self._citizen_indetify = citizen_indentify
        self._password = password
        self._time_out = time_out

    def _request_token(self, plate_info: PlateInfo) -> str | None:
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
        except CurlError as e:
            logger.error(
                f"Error occurs while getting token for plate {plate_info.plate} in API {API_TOKEN_URL}: {e}"
            )
        except Exception as e:
            logger.error(f"Error occurs:{e}")

    def _request(self, plate_info: PlateInfo) -> _Response | None:
        headers: Final[dict[str, str]] = {
            "Authorization": f"Bearer {self._request_token(plate_info)}",
            "User-Agent": "C08_CD/1.1.8 (com.ots.global.vneTrafic; build:32; iOS 18.2.1) Alamofire/5.10.2",
        }
        params: Final[dict[str, str]] = {
            "licensePlate": plate_info.plate,
            "type": f"{get_vehicle_enum(plate_info.type)}",
        }
        try:
            response = requests.get(url=API_URL, headers=headers, params=params)
            plate_detail_raw = response.json()
            return cast(_Response, plate_detail_raw)
        except CurlError as e:
            logger.error(
                f"Error occurs while getting data for plate {plate_info.plate} in API {API_TOKEN_URL}: {e}"
            )
        except Exception as e:
            logger.error(f"Error occurs:{e}")

    @override
    async def _get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        plate_detail_typed = self._request(plate_info)
        if not plate_detail_typed:
            logger.error(f"Failed to get data from api:{self.api}")
            return
        if plate_detail_typed["tag"] == "limit_response":
            logger.error("You are limited to send more requests")
            return
        violation_details: tuple[ViolationDetail, ...] | None = (
            _EtrafficGetDataParseEngine(
                plate_info=plate_info, data=tuple(plate_detail_typed["data"])
            ).parse()
        )
        return violation_details
