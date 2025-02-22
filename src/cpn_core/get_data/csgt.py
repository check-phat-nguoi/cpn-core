from datetime import datetime
from io import BytesIO
from logging import getLogger
from typing import Final, LiteralString, override

from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
)

from cpn_core._utils._request_session_helper import RequestSessionHelper
from cpn_core.exceptions.get_data import (
    GetTokenError,
    ParseResponseError,
    ResolveCaptchaFail,
)
from cpn_core.get_data.base import BaseGetDataEngine
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail
from cpn_core.types.api import ApiEnum
from cpn_core.types.vehicle_type import (
    VehicleTypeEnum,
    get_vehicle_enum,
)

try:
    from pytesseract import image_to_string
except ImportError:
    raise RuntimeError(
        'Cannot use Csgt get data engine because "pytesseract" dependency in "ocr" optional dependencies group hasn\'t been installed'
    )

RESPONSE_DATETIME_FORMAT: LiteralString = "%H:%M, %d/%m/%Y"

API_CAPTCHA: LiteralString = "https://www.csgt.vn/lib/captcha/captcha.class.php"
API_URL_1: LiteralString = "https://www.csgt.vn/?mod=contact&task=tracuu_post&ajax"
API_QUERY_2: LiteralString = "https://www.csgt.vn/tra-cuu-phuong-tien-vi-pham.html?&LoaiXe={vehicle_type}&BienKiemSoat={plate}"

logger = getLogger(__name__)


class _CsgtParseEngine:
    def __init__(self, html_data: str) -> None:
        self._html_data: str = html_data

    def _parse_violation(self, violation_data: str) -> ViolationDetail:
        soup: BeautifulSoup = BeautifulSoup(violation_data, "html.parser")
        if not soup.css:
            raise ParseResponseError(
                "The response in HTML cannot be parsed because of not having css to use css selector"
            )
        plate: str | None = (
            plate_tag.text.strip()
            if (
                plate_tag := soup.select_one(
                    ".form-group:nth-child(1) > div > div:nth-child(2)"
                )
            )
            else None
        )
        color: str | None = (
            color_tag.text.strip()
            if (
                color_tag := soup.select_one(
                    ".form-group:nth-child(2) > div > div:nth-child(2)"
                )
            )
            else None
        )
        type: str | None = (
            type_tag.text.strip()
            if (
                type_tag := soup.select_one(
                    ".form-group:nth-child(3) > div > div:nth-child(2)"
                )
            )
            else None
        )
        date: str | None = (
            date_tag.text.strip()
            if (
                date_tag := soup.select_one(
                    ".form-group:nth-child(4) > div > div:nth-child(2)"
                )
            )
            else None
        )
        location: str | None = (
            location_tag.text.strip()
            if (
                location_tag := soup.select_one(
                    ".form-group:nth-child(5) > div > div:nth-child(2)"
                )
            )
            else None
        )
        violation: str | None = (
            action_tag.text.strip()
            if (
                action_tag := soup.select_one(
                    ".form-group:nth-child(6) > div > div:nth-child(2)"
                )
            )
            else None
        )
        status: str | None = (
            status_tag.text.strip()
            if (
                status_tag := soup.select_one(
                    ".form-group:nth-child(7) > div > div:nth-child(2)"
                )
            )
            else None
        )
        enforcement_unit: str | None = (
            enforcement_unit_tag.text.strip()
            if (
                enforcement_unit_tag := soup.select_one(
                    ".form-group:nth-child(8) > div > div:nth-child(2)"
                )
            )
            else None
        )
        resolution_offices: list[str] = [
            resolution_offices_tag.text.strip()
            for resolution_offices_tag in soup.select(".form-group:nth-child(n+9)")
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
            date=datetime.strptime(str(date), RESPONSE_DATETIME_FORMAT),
            location=location,
            violation=violation,
            status=status == "Đã xử phạt",
            enforcement_unit=enforcement_unit,
            resolution_offices=tuple(resolution_offices),
        )
        return violation_detail

    def _parse_violations(
        self, violations_data: list[str]
    ) -> tuple[ViolationDetail, ...]:
        violation_details: tuple[ViolationDetail, ...] = tuple(
            self._parse_violation(violation_data) for violation_data in violations_data
        )
        return violation_details

    def parse(self) -> tuple[ViolationDetail, ...]:
        soup: BeautifulSoup = BeautifulSoup(self._html_data, "html.parser")
        violation_group_tag: Tag | NavigableString | None = soup.find(
            "div", id="bodyPrint123"
        )
        if not violation_group_tag or isinstance(violation_group_tag, NavigableString):
            raise ParseResponseError('Cannot get the div whose id is "bodyPrint123"')
        violation_group: str = violation_group_tag.prettify(formatter=None)
        # HACK: This split is hard. Maybe change it to regex split later
        violations_data: list[str] = "".join(violation_group.splitlines()[1:-2]).split(
            '<hr style="margin-bottom: 25px;"/>'
        )
        return self._parse_violations(violations_data)


class _CsgtRequestEngine(RequestSessionHelper):
    _headers: Final[dict[str, str]] = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    def __init__(
        self, plate_info: PlateInfo, *, timeout: float, retry_captcha: int
    ) -> None:
        self._plate_info: PlateInfo = plate_info
        self._vehicle_type: VehicleTypeEnum = get_vehicle_enum(self._plate_info.type)
        self._retry_captcha: int = retry_captcha
        super().__init__(timeout=timeout)

    @staticmethod
    def _bypass_captcha(captcha_img: bytes) -> str:
        with Image.open(BytesIO(captcha_img)) as image:
            return image_to_string(image).strip()

    async def _get_phpsessid_and_captcha(self) -> tuple[str, bytes]:
        async with self._session.stream(
            "GET",
            API_CAPTCHA,
        ) as response:
            response.raise_for_status()
            phpsessid: str | None = response.cookies.get("PHPSESSID")
            captcha_img: bytes = await response.aread()
            if not phpsessid:
                raise GetTokenError("Cannot get PHPSESSID token")
            return phpsessid, captcha_img

    async def _get_html_check(self, captcha: str, phpsessid: str) -> str:
        payload: dict[str, str | int] = {
            "BienKS": self._plate_info.plate,
            "Xe": self._vehicle_type.value,
            "captcha": captcha,
            "ipClient": "9.9.9.91",
            "cUrl": self._vehicle_type.value,
        }
        cookies: dict[str, str] = {"PHPSESSID": phpsessid}
        async with self._session.stream(
            "POST",
            url=API_URL_1,
            headers=self._headers,
            cookies=cookies,
            data=payload,
        ) as response:
            html_content: bytes = await response.aread()
            return html_content.decode("utf-8")

    async def _get_plate_data(self) -> str:
        async with self._session.stream(
            "POST",
            url=API_QUERY_2.format(
                vehicle_type=self._vehicle_type.value,
                plate=self._plate_info.plate,
            ),
        ) as response:
            response_data: bytes = await response.aread()
            return response_data.decode("utf-8")

    async def get_data(self) -> str:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._retry_captcha),
                retry=retry_if_exception_type(ResolveCaptchaFail),
                before=lambda _: logger.info(
                    "Plate %s: Retrying because of failing to resolve captcha...",
                    self._plate_info.plate,
                ),
            ):
                with attempt:
                    phpsessid, captcha_img = await self._get_phpsessid_and_captcha()
                    captcha: str = self._bypass_captcha(captcha_img)
                    logger.debug(
                        "Plate %s captcha resolved: %s", self._plate_info.plate, captcha
                    )
                    logger.debug(
                        "Plate %s: Sending request again to get check...",
                        self._plate_info.plate,
                    )
                    html_check_data: str = await self._get_html_check(
                        captcha, phpsessid
                    )
                    if html_check_data.strip() == "404":
                        logger.error(
                            "Plate %s: Wrong captcha",
                            self._plate_info.plate,
                        )
                        raise ResolveCaptchaFail()
                    logger.debug(
                        "Plate %s: Sending request again to get data...",
                        self._plate_info.plate,
                    )
                    html_data: str = await self._get_plate_data()
                    return html_data
        except RetryError as e:
            raise ParseResponseError(
                f"Cannot get data after {self._retry_captcha} time(s). {e}"
            )
        # FIXME: why it can be?? lack of case?
        return ""


class CsgtEngine(BaseGetDataEngine):
    @property
    def api(self) -> ApiEnum:
        return ApiEnum.csgt_vn

    def __init__(self, *, timeout: float = 20, retry_captcha: int = 3) -> None:
        self._retry_captcha: int = retry_captcha
        super().__init__(timeout=timeout)

    @override
    async def _get_data(self, plate_info: PlateInfo) -> tuple[ViolationDetail, ...]:
        async with _CsgtRequestEngine(
            plate_info,
            timeout=self._timeout,
            retry_captcha=self._retry_captcha,
        ) as local_engine:
            html_data: str = await local_engine.get_data()
        violation_details: tuple[ViolationDetail, ...] = _CsgtParseEngine(
            html_data
        ).parse()
        return violation_details
