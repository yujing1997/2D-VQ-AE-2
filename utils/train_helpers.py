from typing import Optional


def make_divisible(
    value: float,
    divisor: int,
    divide: bool = True,
    min_value: Optional[int] = None
):
    """
    Edited from: https://github.com/d-li14/efficientnetv2.pytorch/blob/775326e6c16bfc863e9b8400eca7d723dbfeb06e/effnetv2.py#L16
    """

    return max(
        divisor if min_value is None else min_value,
        int(value + divisor / 2)
    ) // (divisor if divide else 1)