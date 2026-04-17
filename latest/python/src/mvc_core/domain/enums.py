from enum import Enum


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class Status(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Action(str, Enum):
    OPEN = "OPEN"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    HOLD = "HOLD"
    REBALANCE = "REBALANCE"



# Enums for threshold_1d_services 
class TriggerMode(str, Enum):
    POSITION = "position"
    CROSS = "cross"

class CrossSense(str, Enum):
    OUTSIDE_TO_INSIDE = "outside_to_inside"
    INSIDE_TO_OUTSIDE = "inside_to_outside"