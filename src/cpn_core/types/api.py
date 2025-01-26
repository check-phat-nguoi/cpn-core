from enum import Enum


class ApiEnum(str, Enum):
    checkphatnguoi_vn = "checkphatnguoi.vn"
    csgt_vn = "csgt.vn"
    phatnguoi_vn = "phatnguoi.vn"
    zm_io_vn = "zm.io.vn"
    etraffic_gtelict_vn = "etraffic.gtelict.vn"
    tracuuphatnguoi_net = "tracuuphatnguoi.net"


__all__ = ["ApiEnum"]
