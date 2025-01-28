import re
from datetime import datetime
from logging import getLogger
from re import DOTALL
from typing import LiteralString, override

from bs4 import BeautifulSoup, ResultSet, Tag

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.exceptions.get_data import ParseResponseError
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    get_vehicle_enum,
)

API_URL: LiteralString = "https://api.phatnguoi.vn/web/tra-cuu/{plate}/{type}"


RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"


logger = getLogger(__name__)


class _PhatNguoiParseEngine:
    def __init__(self, html_data: str) -> None:
        self._html_data: str = html_data

    def _parse_violation(self, violation_html: Tag) -> ViolationDetail:
        plate: str | None = (
            plate_tag.text.strip()
            if (
                plate_tag := violation_html.select_one(
                    "tr:nth-child(1) > td:nth-child(2)"
                )
            )
            else None
        )
        color: str | None = (
            color_tag.text.strip()
            if (
                color_tag := violation_html.select_one(
                    "tr:nth-child(2) > td:nth-child(2)"
                )
            )
            else None
        )
        type: str | None = (
            type_tag.text.strip()
            if (
                type_tag := violation_html.select_one(
                    "tr:nth-child(3) > td:nth-child(2)"
                )
            )
            else None
        )
        date: str | None = (
            date_tag.text.strip()
            if (
                date_tag := violation_html.select_one(
                    "tr:nth-child(4) > td:nth-child(2)"
                )
            )
            else None
        )
        location: str | None = (
            location_tag.text.strip()
            if (
                location_tag := violation_html.select_one(
                    "tr:nth-child(5) > td:nth-child(2)"
                )
            )
            else None
        )
        violation: str | None = (
            violation_tag.text.strip()
            if (
                violation_tag := violation_html.select_one(
                    "tr:nth-child(6) > td:nth-child(2)"
                )
            )
            else None
        )
        status: str | None = (
            status_tag.text.strip()
            if (
                status_tag := violation_html.select_one(
                    "tr:nth-child(7) > td:nth-child(2)"
                )
            )
            else None
        )
        enforcement_unit: str | None = (
            enforcement_unit_tag.text.strip()
            if (
                enforcement_unit_tag := violation_html.select_one(
                    "tr:nth-child(8) > td:nth-child(2)"
                )
            )
            else None
        )
        resolution_offices: str | None = (
            resolution_offices_tag.text.strip()
            if (
                resolution_offices_tag := violation_html.select_one(
                    "tr:nth-child(9) > td:nth-child(2)"
                )
            )
            else None
        )
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
        #  TODO: Split resolution_office as other api
        violation_detail: ViolationDetail = ViolationDetail(
            plate=plate,
            color=color,
            type=get_vehicle_enum(type),
            location=location,
            # Have to cast to string because lsp's warning
            date=datetime.strptime(str(date), RESPONSE_DATETIME_FORMAT),
            violation=violation,
            status=status == "Đã xử phạt",
            enforcement_unit=enforcement_unit,
            resolution_offices=tuple(
                re.findall(r"\d\..*?(?=(?:\d\.|$))", resolution_offices, DOTALL)
            ),
        )
        return violation_detail

    def parse(self) -> tuple[ViolationDetail, ...]:
        soup: BeautifulSoup = BeautifulSoup(self._html_data, "html.parser")
        if not soup.css:
            raise ParseResponseError(
                "The response in HTML cannot be parsed because of not having css to use css selector"
            )
        violation_htmls: ResultSet[Tag] | None = soup.css.select("tbody")
        if not violation_htmls:
            raise ParseResponseError("Cannot get the tbody tag")
        violation_details: tuple[ViolationDetail, ...] = tuple(
            self._parse_violation(violation_html) for violation_html in violation_htmls
        )
        return violation_details


class _PhatNguoiRequestEngine(RequestSessionHelper):
    def __init__(self, *, timeout: float = 20) -> None:
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def request(self, plate_info: PlateInfo) -> str:
        url: str = API_URL.format(
            plate=plate_info.plate, type=get_vehicle_enum(plate_info.type).value
        )
        async with self._session.stream("GET", url=url) as response:
            html_data: bytes = await response.aread()
        return html_data.decode("utf-8")


class PhatNguoiEngine(BaseGetDataEngine):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.phatnguoi_vn

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)

    @override
    async def _get_data(self, plate_info: PlateInfo) -> tuple[ViolationDetail, ...]:
        html_data: str = await _PhatNguoiRequestEngine(timeout=self._timeout).request(
            plate_info
        )
        violation_details: tuple[ViolationDetail, ...] = _PhatNguoiParseEngine(
            html_data=html_data,
        ).parse()
        return violation_details
