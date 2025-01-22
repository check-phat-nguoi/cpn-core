from datetime import datetime
from typing import Any, Literal, LiteralString, override

from pydantic import BaseModel, Field, computed_field

from cpn_core._constants.datetime import DATETIME_FORMAT_12, DATETIME_FORMAT_24
from cpn_core.models.plate_info import PlateInfo
from cpn_core.models.violation_detail import ViolationDetail


class PlateDetail(BaseModel):
    plate_info: PlateInfo = Field(
        description="Thông tin biển số phương tiện",
    )
    violations: tuple[ViolationDetail, ...] | None = Field(
        description="Danh sách các vi phạm của 1 biển xe",
    )
    date_time: datetime = Field(
        description="Thời gian lấy thông tin",
        default_factory=datetime.now,
    )

    @computed_field
    @property
    def total_fines(self) -> int:
        if self.violations is None:
            return -1
        return len(self.violations)

    @computed_field
    @property
    def total_peding_fines(self) -> int:
        if self.violations is None:
            return -1
        return len(
            tuple(violation for violation in self.violations if not violation.status)
        )

    def _get_fines_total_str(
        self, *, show_less_detail: bool, markdown: bool
    ) -> str | None:
        if self.violations is None:
            return None
        if markdown:
            return (
                ""
                if not show_less_detail
                else f"**Số vi phạm:** `{self.total_fines}`\n"
            ) + f"**Số vi phạm chưa xử phạt:** `{self.total_peding_fines}`"
        else:
            return (
                "" if not show_less_detail else f"Số vi phạm: {self.total_fines}\n"
            ) + (f"Số vi phạm chưa xử phạt: {self.total_peding_fines}")

    def get_str(
        self,
        *,
        show_less_detail: bool,
        markdown: bool,
        time_format: Literal["12", "24"],
    ) -> str:
        plate_info: str = self.plate_info.get_str(
            show_less_detail=show_less_detail, markdown=markdown
        )
        if self.violations is None:
            return plate_info
        fines_total: str | None = self._get_fines_total_str(
            show_less_detail=show_less_detail, markdown=markdown
        )
        violation_header: LiteralString = (
            "**Vi phạm thứ #{order}:**\n" if markdown else "Vi phạm thứ #{order}:\n"
        )
        violations: tuple[str, ...] = tuple(
            violation.get_str(
                show_less_detail=show_less_detail,
                markdown=markdown,
                time_format=time_format,
            )
            for violation in self.violations
        )
        return (
            plate_info
            + (f"\n{fines_total}" if fines_total else "")
            + "\n\n"
            + "\n\n".join(
                violation_header.format(order=order) + violation
                for order, violation in enumerate(violations, start=1)
            )
        )

    def get_messages(
        self,
        *,
        show_less_detail: bool,
        markdown: bool,
        time_format: Literal["12", "24"],
    ) -> tuple[str, ...]:
        if not self.violations:
            return ()
        plate_info: str = self.plate_info.get_str(
            show_less_detail=show_less_detail, markdown=markdown
        )
        violations: tuple[str, ...] = tuple(
            violation.get_str(
                show_less_detail=show_less_detail,
                markdown=markdown,
                time_format=time_format,
            )
            for violation in self.violations
        )
        date_time: str = self.date_time.strftime(
            DATETIME_FORMAT_24 if time_format == "24" else DATETIME_FORMAT_12
        )
        return tuple(
            f"{plate_info}\n\n{violation}\n\nGửi lúc: {date_time}"
            for violation in violations
        )

    @override
    def __hash__(self):
        return hash(self.plate_info) + hash(self.violations)

    @override
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, PlateDetail):
            return self.plate_info == other.plate_info and (
                all(x == y for x, y in zip(self.violations, other.violations))
                if self.violations and other.violations
                else (not self.violations and not other.violations)
            )
        return False


__all__ = ["PlateDetail"]
