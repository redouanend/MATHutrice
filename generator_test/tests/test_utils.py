"""Tests de la fonction utilitaire clamp_score."""

from decimal import Decimal

import pytest

from fonctions_python.utils import clamp_score


@pytest.mark.parametrize(
    "value, expected",
    [
        (-1, 0.0),
        (-0.001, 0.0),
        (0, 0.0),
        (0.5, 0.5),
        (1, 1.0),
        (1.001, 1.0),
        (42, 1.0),
        (Decimal("0.8"), 0.8),
        (Decimal("-3"), 0.0),
    ],
)
def test_clamp_score_bounds_to_unit_interval(value, expected):
    assert clamp_score(value) == pytest.approx(expected)


def test_clamp_score_returns_float():
    assert isinstance(clamp_score(Decimal("0.5")), float)
