from datetime import datetime
from functools import cached_property
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

from cpn_core.exceptions.get_data import ServerLimitError
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import get_vehicle_enum

from .base import BaseGetDataEngine

logger = getLogger(__name__)


API_TOKEN_URL = "https://etraffic.gtelict.vn/api/citizen/v2/auth/login"
API_URL = "https://etraffic.gtelict.vn/api/citizen/v2/property/deferred/fines"

RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"

try:
    from curl_cffi import CurlError
    from curl_cffi.requests import Response, Session
    from curl_cffi.requests.exceptions import Timeout
except ImportError:
    raise RuntimeError(
        'Cannot use Etraffic get data engine because "curl_cffi" dependency in "curl" optional dependencies group hasn\'t been installed'
    )


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
    data: tuple[_DataPlateInfoResponse, ...]


class _LimitResponse(TypedDict):
    tag: Literal["limit_response"]
    guid: str
    code: str
    message: str
    status: int
    path: str
    method: str
    timestamp: str
    error: str | None


_Response: TypeAlias = _LimitResponse | _FoundResponse


class _EtrafficGetDataParseEngine:
    def __init__(self, violations: tuple[_DataPlateInfoResponse, ...]) -> None:
        self._violations: tuple[_DataPlateInfoResponse, ...] = violations

    def _parse_violation(self, data: _DataPlateInfoResponse) -> ViolationDetail:
        plate: str = data["licensePlate"]
        date: str = data["violationAt"]
        type: Literal["Ô tô con", "Xe máy", "Xe máy điện"] = data["vehicleType"]
        color: str = data["licensePlateType"]
        location: str = data["handlingAddress"]
        status: str = data["statusType"]
        enforcement_unit: str = data["propertyName"]
        resolution_offices: tuple[str, ...] = (data["departmentName"],)
        violation_detail: ViolationDetail = ViolationDetail(
            plate=plate,
            color=color,
            # FIXME: @NTNguyen match case O to con?
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
        return tuple(self._parse_violation(violation) for violation in self._violations)


class _EtrafficRequestEngine:
    token_headers: Final[dict[str, str]] = {
        "Content-Type": "application/json",
        "User-Agent": "C08_CD/1.1.8 (com.ots.global.vneTrafic; build:32; iOS 18.2.1) Alamofire/5.10.2",
    }

    def __init__(
        self, citizen_indentify: str, password: str, *, timeout: float = 10
    ) -> None:
        self._citizen_indetify = citizen_indentify
        self._password = password
        self._timeout = timeout
        self._session_: Session | None = None

    @cached_property
    def request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._request_token()}",
            "User-Agent": "C08_CD/1.1.8 (com.ots.global.vneTrafic; build:32; iOS 18.2.1) Alamofire/5.10.2",
        }

    @property
    def _session(self) -> Session:
        if self._session_ is None:
            self._session_ = Session(timeout=self._timeout)
            logger.debug("Created a curl request session")
        return self._session_

    async def __aenter__(self) -> Self:
        self._token = self._request_token()
        return self

    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        if self._session_ is not None:
            self._session_.close()

    def _request_token(self) -> str:
        data: Final[dict[str, str]] = {
            "citizenIndentify": self._citizen_indetify,
            "password": self._password,
        }
        # FIXME: await
        response: Response = self._session.post(
            url=API_TOKEN_URL,
            headers=self.token_headers,
            json=data,
            verify=False,
        )
        # FIXME: cast type @NTNguyen
        data_dict = response.json()
        return data_dict["value"]["refreshToken"]

    def request(self, plate_info: PlateInfo) -> _Response:
        params: Final[dict[str, str]] = {
            "licensePlate": plate_info.plate,
            "type": f"{get_vehicle_enum(plate_info.type).value}",
        }
        # FIXME: await
        response: Response = self._session.get(
            url=API_URL,
            headers=self.request_headers,
            params=params,
        )
        data: dict = response.json()
        return cast(_Response, data)


class EtrafficEngine(BaseGetDataEngine):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.etraffic_gtelict_vn

    def __init__(
        self, citizen_indentify: str, password: str, *, timeout: float = 10
    ) -> None:
        self._request_engine: _EtrafficRequestEngine = _EtrafficRequestEngine(
            citizen_indentify=citizen_indentify, password=password, timeout=timeout
        )

    @override
    async def _get_data(self, plate_info: PlateInfo) -> tuple[ViolationDetail, ...]:
        response: _Response = self._request_engine.request(plate_info)
        if response["tag"] == "limit_response":
            raise ServerLimitError()
        violation_details: tuple[ViolationDetail, ...] = _EtrafficGetDataParseEngine(
            violations=response["data"]
        ).parse()
        return violation_details

    @override
    async def get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        try:
            violation_details: tuple[ViolationDetail, ...] = await self._get_data(
                plate_info
            )
            if not violation_details:
                logger.info(
                    "Plate %s - %s: Don't have any violation",
                    plate_info.plate,
                    self.api,
                )
            return violation_details
        except Timeout as e:
            logger.error(
                "Plate %s - %s: Time out (%ds) getting data from API. %s",
                plate_info.plate,
                self.api.value,
                self._timeout,
                e,
            )
        except CurlError as e:
            logger.error(
                "Plate %s - %s: Error occured. %s",
                plate_info.plate,
                self.api.value,
                e,
            )
        except ServerLimitError as e:
            logger.error(
                "Plate %s - %s: Got limit error from server. %s",
                plate_info.plate,
                self.api,
                e,
            )
        except Exception as e:
            logger.error(
                "Plate %s - %s: Error occurs while getting data (internal). %s",
                plate_info.plate,
                self.api.value,
                e,
            )

    @override
    async def __aenter__(self) -> Self:
        await self._request_engine.__aenter__()
        return self

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await self._request_engine.__aexit__(exc_type, exc_value, exc_traceback)
