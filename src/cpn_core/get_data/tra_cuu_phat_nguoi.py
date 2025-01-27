import json
from datetime import datetime
from logging import getLogger
from typing import (
    Literal,
    LiteralString,
    Self,
    TypeAlias,
    TypedDict,
    cast,
    override,
)

from bs4 import BeautifulSoup, NavigableString, ResultSet, Tag

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.exceptions.get_data import GetTokenError, ParseResponseError
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    VehicleTypeEnum,
    get_vehicle_enum,
)

API_URL_1: LiteralString = "https://tracuuphatnguoi.net/tracuu1.php"
API_URL_2: LiteralString = (
    "https://tracuuphatnguoi.net/tracuu1.php/?BienKS={plate}&Xe={type}&token={token}"
)

RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"


class _FailedResponse(TypedDict):
    stt: Literal["0"]
    html: Literal[""]
    mess: str


class _SuccessfulResponse(TypedDict):
    stt: Literal["1"]
    html: str
    source: str
    token: str


_Response: TypeAlias = _FailedResponse | _SuccessfulResponse


logger = getLogger(__name__)


class _TraCuuPhatNguoiParseEngine:
    def __init__(self, plate_info: PlateInfo, html_data: str) -> None:
        self._vehicle_type: VehicleTypeEnum = get_vehicle_enum(plate_info.type)
        self._html_data: str = html_data
        self._violation_details_set: set[ViolationDetail] = set()

    @staticmethod
    def _parse_violation(table: Tag) -> ViolationDetail:
        plate: str | None = (
            plate_tag.text.strip()
            if (plate_tag := table.select_one("tr:nth-child(1) > td:nth-child(2)"))
            else None
        )
        color: str | None = (
            color_tag.text.strip()
            if (color_tag := table.select_one("tr:nth-child(2) > td:nth-child(2)"))
            else None
        )
        type: str | None = (
            type_tag.text.strip()
            if (type_tag := table.select_one("tr:nth-child(3) > td:nth-child(2)"))
            else None
        )
        date: str | None = (
            date_tag.text.strip()
            if (date_tag := table.select_one("tr:nth-child(4) > td:nth-child(2)"))
            else None
        )
        location: str | None = (
            location_tag.text.strip()
            if (location_tag := table.select_one("tr:nth-child(5) > td:nth-child(2)"))
            else None
        )
        violation: str | None = (
            action_tag.text.strip()
            if (action_tag := table.select_one("tr:nth-child(6) > td:nth-child(2)"))
            else None
        )
        status: str | None = (
            status_tag.text.strip()
            if (status_tag := table.select_one("tr:nth-child(7) > td:nth-child(2)"))
            else None
        )
        enforcement_unit: str | None = (
            enforcement_unit_tag.text.strip()
            if (
                enforcement_unit_tag := table.select_one(
                    "tr:nth-child(8) > td:nth-child(2)"
                )
            )
            else None
        )
        resolution_offices: list[str] = [
            resolution_offices_tag.text.strip()
            for resolution_offices_tag in table.select(".form-group:nth-child(n+9)")
        ]
        if (
            plate is None
            or color is None
            or date is None
            or location is None
            or violation is None
            or status is None
            or enforcement_unit is None
            or not resolution_offices
        ):
            raise ParseResponseError("Some field are missing that break the parsement")
        violation_detail: ViolationDetail = ViolationDetail(
            plate=plate,
            color=color,
            type=get_vehicle_enum(type),
            date=datetime.strptime(date, RESPONSE_DATETIME_FORMAT),
            location=location,
            violation=violation,
            status=status == "Đã xử phạt",
            enforcement_unit=enforcement_unit,
            resolution_offices=tuple(resolution_offices),
        )

        return violation_detail

    def parse(self) -> tuple[ViolationDetail, ...]:
        soup: BeautifulSoup = BeautifulSoup(self._html_data, "html.parser")
        if not soup.css:
            raise ParseResponseError(
                "The response in HTML cannot be parsed because of not having css to use css selector"
            )
        tables: ResultSet[Tag] = soup.css.select("table.css_table")
        return tuple(self._parse_violation(table) for table in tables)


class _TraCuuPhatNguoiRequestEngine(RequestSessionHelper):
    def __init__(self, plate_info: PlateInfo, *, timeout: float = 20) -> None:
        self._plate_info: PlateInfo = plate_info
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def _get_phpsessid_and_csrf(self) -> tuple[str, str]:
        async with self._session.stream(
            "GET",
            API_URL_1,
        ) as response:
            response.raise_for_status()
            content: bytes = await response.aread()
            phpsessid: str | None = response.cookies.get("PHPSESSID")
            soup: BeautifulSoup = BeautifulSoup(markup=content, features="html.parser")
            csrf_tag: Tag | NavigableString | None = soup.find(id="csrf")
            if not isinstance(csrf_tag, Tag):
                raise GetTokenError("Cannot get csrf token")
            csrf: str | list[str] | None = csrf_tag.get("value")
            if not csrf or isinstance(csrf, list):
                raise GetTokenError("Failed to parse the csrf token")
            if not phpsessid:
                raise GetTokenError("Cannot get PHPSESSID token")
            return phpsessid, csrf

    async def request(self) -> _Response:
        phpsessid, csrf = await self._get_phpsessid_and_csrf()
        headers: dict[str, str] = {
            "Referer": "https://tracuuphatnguoi.net/",
        }
        cookies: dict[str, str] = {"PHPSESSID": phpsessid}
        async with self._session.stream(
            "POST",
            API_URL_2.format(
                plate=self._plate_info.plate.replace("-", ""),
                type=get_vehicle_enum(self._plate_info.type).value,
                token=csrf,
            ),
            headers=headers,
            cookies=cookies,
        ) as response:
            response.raise_for_status()
            content: bytes = await response.aread()
            response_data = json.loads(content.decode("utf-8"))
            return cast(_Response, response_data)

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await RequestSessionHelper.__aexit__(self, exc_type, exc_value, exc_traceback)


class TraCuuPhatNguoiEngine(BaseGetDataEngine):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.tracuuphatnguoi_net

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)

    @override
    async def _get_data(
        self,
        plate_info: PlateInfo,
    ) -> tuple[ViolationDetail, ...] | None:
        response: _Response = await _TraCuuPhatNguoiRequestEngine(
            plate_info=plate_info, timeout=self._timeout
        ).request()
        if response["stt"] == "0":
            # TODO: Raise server fail in main later
            return
        violations: tuple[ViolationDetail, ...] | None = _TraCuuPhatNguoiParseEngine(
            plate_info=plate_info, html_data=response["html"]
        ).parse()
        return violations
