from datetime import datetime
from typing import Literal, LiteralString, override

from pydantic import BaseModel

from cpn_core._constants.datetime import DATETIME_FORMAT_12, DATETIME_FORMAT_24
from cpn_core._utils._gen_map_search_url import _gen_map_search_url
from cpn_core.types.vehicle_type import VehicleTypeEnum, get_vehicle_str_vie


class ViolationDetail(BaseModel):
    plate: str | None
    color: str | None
    type: VehicleTypeEnum | None
    date: datetime | None
    location: str | None
    violation: str | None
    status: bool | None
    enforcement_unit: str | None
    resolution_offices: tuple[str, ...] | None

    def get_str(
        self,
        *,
        show_less_detail: bool,
        markdown: bool,
        time_format: Literal["12", "24"],
    ) -> str:
        if markdown:
            return self._get_markdown_message(show_less_detail, time_format)
        else:
            return self._get_raw_messages(show_less_detail, time_format)

    def _get_raw_messages(
        self,
        show_less_detail: bool,
        time_format: Literal["12", "24"],
    ) -> str:
        header: LiteralString = "⚠️ Thông tin vi phạm:"
        message: str = (
            (
                (f"Biển: {self.plate}" if self.plate is not None else "")
                + (f"\nMàu biển: {self.color}" if self.color is not None else "")
                + (
                    f"\nLoại xe: {get_vehicle_str_vie(self.type)}"
                    if self.type is not None
                    else ""
                )
                + "\n"
                if not show_less_detail
                else ""
            )
            + (
                f"Thời điểm: {self.date.strftime(DATETIME_FORMAT_24) if time_format == '24' else self.date.strftime(DATETIME_FORMAT_12)}"
                if self.date is not None
                else ""
            )
            + (f"\nVị trí: {self.location}" if self.location is not None else "")
            + (f"\nHành vi: {self.violation}" if self.violation is not None else "")
            + (
                f"\nTrạng thái: {'Đã xử phạt' if self.status else 'Chưa xử phạt'}"
                if self.status is not None
                else ""
            )
            + (
                f"\nĐơn vị phát hiện: {self.enforcement_unit}"
                if self.enforcement_unit is not None
                else ""
            )
            + (
                (
                    "\n"
                    + "\n".join(
                        f"- {resolution_office}"
                        for resolution_office in self.resolution_offices
                    )
                )
                if self.resolution_offices is not None
                else ""
            )
        ).strip()
        return f"{header}\n{message}".strip()

    def _get_markdown_message(
        self,
        show_less_detail: bool,
        time_format: Literal["12", "24"],
    ) -> str:
        header: LiteralString = "**⚠️ Thông tin vi phạm:**"
        message: str = (
            (
                (f"**Biển:** {self.plate}" if self.plate is not None else "")
                + (f"\n**Màu biển:** {self.color}" if self.color is not None else "")
                + (
                    f"\n**Loại xe:** {get_vehicle_str_vie(self.type)}"
                    if self.type is not None
                    else ""
                )
                + "\n"
                if not show_less_detail
                else ""
            )
            + (
                f"**Thời điểm:** {self.date.strftime(DATETIME_FORMAT_24) if time_format == '24' else self.date.strftime(DATETIME_FORMAT_12)}"
                if self.date is not None
                else ""
            )
            + (
                f"\n**Vị trí:** [{self.location}]({_gen_map_search_url(self.location)})"
                if self.location is not None
                else ""
            )
            + (f"\n**Hành vi:** {self.violation}" if self.violation else "")
            + (
                f"\n**Trạng thái:** {'Đã xử phạt ✅' if self.status else 'Chưa xử phạt ❌'}"
                if self.status is not None
                else ""
            )
            + (
                f"\n**Đơn vị phát hiện:** {self.enforcement_unit}"
                if self.enforcement_unit is not None
                else ""
            )
            + (
                (
                    "\n"
                    + "\n".join(
                        f"- {resolution_office}"
                        for resolution_office in self.resolution_offices
                    )
                )
                if self.resolution_offices is not None
                else ""
            )
        ).strip()
        return f"{header}\n{message}".strip()

    @override
    def __hash__(self):
        return (
            hash(self.plate) + hash(self.color) + hash(self.date) + hash(self.location)
        )
