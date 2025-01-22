import re
from datetime import datetime
from logging import getLogger
from re import DOTALL
from typing import LiteralString, Self, override

from bs4 import BeautifulSoup, ResultSet, Tag

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    get_vehicle_enum,
)

logger = getLogger(__name__)

API_URL: LiteralString = "https://api.phatnguoi.vn/web/tra-cuu/{plate}/{type}"
RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"


class _PhatNguoiParseEngine:
    def __init__(self, plate_info: PlateInfo, html_data: str) -> None:
        self._plate_info: PlateInfo = plate_info
        self._html_data: str = html_data
        self._violation_details_set: set[ViolationDetail] = set()

    def _parse_violation(self, violation_html: Tag) -> None:
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
            logger.error(
                f"Plate {self._plate_info.plate}: Cannot parse a violation data"
            )
            return
        # # TODO: Split resolution_office as other api
        self._violation_details_set.add(
            ViolationDetail(
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
        )

    def parse(self) -> tuple[ViolationDetail, ...] | None:
        soup: BeautifulSoup = BeautifulSoup(self._html_data, "html.parser")
        if not soup.css:
            logger.error("The data got doesn't have css selector ability")
            return
        violation_htmls: ResultSet[Tag] | None = soup.css.select("tbody")
        if not violation_htmls:
            logger.error("Cannot get the tbody tag")
            return
        for violation_html in violation_htmls:
            self._parse_violation(violation_html)
        violation_details: tuple[ViolationDetail, ...] = tuple(
            self._violation_details_set
        )
        if not violation_details:
            logger.info("Plate %s: Don't find any violation", self._plate_info.plate)
        return violation_details


class PhatNguoiEngine(BaseGetDataEngine, RequestSessionHelper):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.phatnguoi_vn

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)
        RequestSessionHelper.__init__(self, timeout=timeout)

    async def _request(self, plate_info: PlateInfo) -> str | None:
        url: str = API_URL.format(
            plate=plate_info.plate, type=get_vehicle_enum(plate_info.type)
        )
        async with self._session.stream("GET", url=url) as response:
            html_data: bytes = await response.aread()
        return html_data.decode("utf-8")

    @override
    async def _get_data(
        self, plate_info: PlateInfo
    ) -> tuple[ViolationDetail, ...] | None:
        html_data: str | None = await self._request(plate_info)
        if html_data is None:
            return
        violations: tuple[ViolationDetail, ...] | None = _PhatNguoiParseEngine(
            plate_info=plate_info,
            html_data=html_data,
        ).parse()
        return violations

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await RequestSessionHelper.__aexit__(self, exc_type, exc_value, exc_traceback)
