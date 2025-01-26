import json
from datetime import datetime
from logging import getLogger
from typing import (
    Final,
    LiteralString,
    Self,
    override,
)

from bs4 import BeautifulSoup, NavigableString, Tag

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    VehicleTypeEnum,
    get_vehicle_enum,
)

API_URL: LiteralString = "https://tracuuphatnguoi.net"
RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"
logger = getLogger(__name__)


class _TraCuuPhatNguoiParseEngine:
    def __init__(self, plate_info: PlateInfo, response: LiteralString) -> None:
        self._plate_info: PlateInfo = plate_info
        self._vehicle_type: VehicleTypeEnum = get_vehicle_enum(plate_info.type)
        self._response: LiteralString = response
        self._violation_details_set: set[ViolationDetail] = set()

    def parse(self) -> tuple[ViolationDetail, ...]:
        # NOTE:: The type of tables is bs4.element.ResultSet but I don't think it's important here
        soup = BeautifulSoup(self._response, "html.parser")
        tables = soup.find_all("table", class_="css_table")

        for _, table in enumerate(tables, start=1):
            rows = table.find_all("tr")
            infos: list[str] = []

            for row in rows:
                info = row.find("td", class_="row_right")
                if info is None:
                    continue
                infos.append(info.get_text(strip=True))

            violation_detail = ViolationDetail(
                plate=infos[0],
                color=infos[1],
                date=datetime.strptime(infos[3], RESPONSE_DATETIME_FORMAT),
                type=self._vehicle_type,
                location=infos[4],
                violation=infos[5],
                status=infos[6] == "Đã xử phạt",
                enforcement_unit=infos[7],
                resolution_offices=tuple(infos[8:]),
            )

            self._violation_details_set.add(violation_detail)

        if len(self._violation_details_set) == 0:
            logger.info(
                "Plate %s: Don't have any violations",
                self._plate_info.plate,
            )
        return tuple(self._violation_details_set)


class TraCuuPhatNguoiEngine(BaseGetDataEngine, RequestSessionHelper):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.tracuuphatnguoi_net

    headers: Final[dict[str, str]] = {
        "Referer": "https://tracuuphatnguoi.net/",
    }

    cookies: Final[dict[str, str]] = {
        "PHPSESSID": "abc",
    }

    def __init__(self, *, timeout: float = 20) -> None:
        BaseGetDataEngine.__init__(self, timeout=timeout)
        RequestSessionHelper.__init__(self, timeout=timeout)
        self._token = None

    async def _request(self, plate_info: PlateInfo) -> LiteralString | None:
        if self._token is None:
            async with self._session.stream(
                "GET",
                API_URL,
                cookies=self.cookies,
            ) as response:
                response.raise_for_status()
                content: bytes = await response.aread()
                soup = BeautifulSoup(markup=content, features="html.parser")
                csrf_ele: Tag | NavigableString | None = soup.find(id="csrf")

                if type(csrf_ele) is Tag:
                    self._token = csrf_ele.get("value")
                else:
                    print("Can't find token!")

        query: str = f"/tracuu1.php?BienKS={plate_info.plate.replace('-','')}&Xe={get_vehicle_enum(plate_info.type)}&token={self._token}"

        async with self._session.stream(
            "POST",
            API_URL + query,
            headers=self.headers,
            cookies=self.cookies,
        ) as response:
            response.raise_for_status()
            content: bytes = await response.aread()
            response_data = json.loads(content.decode("utf-8"))
            self._token = response_data["token"]
        return response_data["html"]

    @override
    async def _get_data(
        self,
        plate_info: PlateInfo,
    ) -> tuple[ViolationDetail, ...] | None:
        response = await self._request(plate_info)
        if response is None:
            return None
        violations: tuple[ViolationDetail, ...] | None = _TraCuuPhatNguoiParseEngine(
            plate_info=plate_info, response=response
        ).parse()
        return violations

    @override
    async def __aenter__(self) -> Self:
        return self

    @override
    async def __aexit__(self, exc_type, exc_value, exc_traceback) -> None:
        await RequestSessionHelper.__aexit__(self, exc_type, exc_value, exc_traceback)
