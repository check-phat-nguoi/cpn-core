from enum import IntEnum
from typing import Any, Literal, TypeAlias


class VehicleTypeEnum(IntEnum):
    car = 1
    motorbike = 2
    electric_motorbike = 3


VehicleStrVieType: TypeAlias = Literal["Ô tô", "Xe máy", "Xe máy điện"]

VehicleStrType: TypeAlias = Literal["car", "motorbike", "electric_motorbike"]

VehicleIntType: TypeAlias = Literal[1, 2, 3]

VehicleType: TypeAlias = VehicleIntType | VehicleStrType | VehicleStrVieType


def get_vehicle_enum(type: VehicleTypeEnum | VehicleType | Any) -> VehicleTypeEnum:
    if isinstance(type, VehicleTypeEnum):
        return type
    match type:
        case VehicleTypeEnum.car | "car" | "Ô tô" | 1 | "1":
            return VehicleTypeEnum.car
        case VehicleTypeEnum.motorbike | "motorbike" | "Xe máy" | 2 | "2":
            return VehicleTypeEnum.motorbike
        case (
            VehicleTypeEnum.electric_motorbike
            | "electric_motorbike"
            | "Xe máy điện"
            | 3
            | "3"
        ):
            return VehicleTypeEnum.electric_motorbike
        case _:
            raise ValueError("Unknown vehicle type")


def get_vehicle_str(type: VehicleTypeEnum | VehicleType | Any) -> VehicleStrType:
    match type:
        case VehicleTypeEnum.car | "car" | "Ô tô" | 1 | "1":
            return "car"
        case VehicleTypeEnum.motorbike | "motorbike" | "Xe máy" | 2 | "2":
            return "motorbike"
        case (
            VehicleTypeEnum.electric_motorbike
            | "electric_motorbike"
            | "Xe máy điện"
            | 3
            | "3"
        ):
            return "electric_motorbike"
        case _:
            raise ValueError("Unknown vehicle type")


def get_vehicle_str_vie(type: VehicleTypeEnum | VehicleType | Any) -> VehicleStrVieType:
    match type:
        case VehicleTypeEnum.car | "car" | "Ô tô" | 1 | "1":
            return "Ô tô"
        case VehicleTypeEnum.motorbike | "motorbike" | "Xe máy" | 2 | "2":
            return "Xe máy"
        case (
            VehicleTypeEnum.electric_motorbike
            | "electric_motorbike"
            | "Xe máy điện"
            | 3
            | "3"
        ):
            return "Xe máy điện"
        case _:
            raise ValueError("Unknown vehicle type")


__all__ = [
    "VehicleIntType",
    "VehicleStrType",
    "VehicleStrVieType",
    "VehicleType",
    "VehicleTypeEnum",
    "get_vehicle_enum",
    "get_vehicle_str",
]
