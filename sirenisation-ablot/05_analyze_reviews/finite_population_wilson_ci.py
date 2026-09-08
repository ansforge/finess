"""Finite-population Wilson-type confidence intervals.

This module is based on the project's original ``finite_population_wilson_ci.py``
helper and is used by ``analyze_reviews.py`` for the stratum-level Wilson
confidence intervals.

The usual call is::

    finite_population_wilson_ci(N_h, n_h, X_h)

where ``N_h`` is the finite population, ``n_h`` is the binomial denominator and
``X_h`` is the number of successes.

For the review analysis, proposal-correctness proportions are defined among
*entities to match*, whereas the sampling fraction is based on all *entities
examined*.  The optional ``fpc_sample_size`` argument handles that distinction:
``n_h`` still defines the observed proportion ``X_h / n_h``, while
``fpc_sample_size / N_h`` defines how much of the finite stratum population was
examined.  If omitted, ``fpc_sample_size`` defaults to ``n_h`` and the function
reduces to the original finite-population Wilson formula.

This is a descriptive finite-population adjustment.  In particular, for the
EGE two-stage/clustered sample it is not a full design-based confidence interval
that accounts for clustering by EJ.
"""

from __future__ import annotations

import math
from statistics import NormalDist


def _as_integer_like(value: float, *, name: str) -> int:
    """Return an integer-like finite value or raise ``TypeError`` or ``ValueError``."""

    if isinstance(value, bool):
        raise TypeError(f"{name} must be integer-like, not boolean")

    try:
        numeric = float(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be integer-like; received {value!r}") from exc
    except ValueError as exc:
        raise ValueError(f"{name} must be integer-like; received {value!r}") from exc

    if not math.isfinite(numeric) or not numeric.is_integer():
        raise ValueError(f"{name} must be integer-like; received {value!r}")

    return int(numeric)


def _validate_confidence(confidence: float) -> float:
    try:
        value = float(confidence)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"confidence must be numeric; received {confidence!r}") from exc
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        raise ValueError("confidence must be strictly between 0 and 1")
    return value


def finite_population_wilson_ci(
    N_h: float,
    n_h: float,
    X_h: float,
    confidence: float = 0.95,
    digits: int | None = None,
    *,
    fpc_sample_size: float | None = None,
) -> tuple[float, float]:
    """Return a finite-population Wilson-type CI as fractions in ``[0, 1]``.

    Parameters
    ----------
    N_h:
        Total finite stratum population size.
    n_h:
        Denominator of the observed proportion.  In the review analysis this is
        the number of entities to match.
    X_h:
        Number of successes among those ``n_h`` entities.
    confidence:
        Two-sided confidence level; defaults to 0.95.
    digits:
        Optional number of decimal places for the returned fractions.
    fpc_sample_size:
        Number of units actually examined from the finite population for the
        finite-population correction.  Defaults to ``n_h`` for backward
        compatibility with the original helper.

    Returns
    -------
    tuple[float, float]
        Lower and upper bounds as fractions.  If ``n_h == 0`` (and ``X_h == 0``),
        the interval is undefined and ``(nan, nan)`` is returned.

    Raises
    ------
    ValueError
        For non-integer-like counts or logically impossible combinations.

    Notes
    -----
    The finite-population factor is

    ``c_h = (N_h - fpc_sample_size) / (N_h - 1)``.

    With ``fpc_sample_size=None`` this is exactly the original formulation using
    ``(N_h - n_h) / (N_h - 1)``.  Separating the two sample sizes lets the review
    analysis retain its estimand (correctness among entities to match) while
    reflecting the actual fraction of the stratum that was examined.
    """

    N_h = _as_integer_like(N_h, name="N_h")
    n_h = _as_integer_like(n_h, name="n_h")
    X_h = _as_integer_like(X_h, name="X_h")
    confidence = _validate_confidence(confidence)
    fpc_n = n_h if fpc_sample_size is None else _as_integer_like(
        fpc_sample_size, name="fpc_sample_size"
    )

    if N_h < 0:
        raise ValueError(f"N_h must be non-negative; received {N_h}")
    if n_h < 0:
        raise ValueError(f"n_h must be non-negative; received {n_h}")
    if X_h < 0 or X_h > n_h:
        raise ValueError(
            f"X_h must satisfy 0 <= X_h <= n_h; received X_h={X_h}, n_h={n_h}"
        )
    if fpc_n < 0:
        raise ValueError(f"fpc_sample_size must be non-negative; received {fpc_n}")
    if fpc_n > N_h:
        raise ValueError(
            "fpc_sample_size cannot exceed N_h; "
            f"received fpc_sample_size={fpc_n}, N_h={N_h}"
        )
    if n_h > fpc_n:
        raise ValueError(
            "n_h cannot exceed fpc_sample_size because the proportion denominator "
            f"must be contained in the examined sample; received n_h={n_h}, "
            f"fpc_sample_size={fpc_n}"
        )
    if N_h == 0:
        if n_h == 0 and X_h == 0 and fpc_n == 0:
            return math.nan, math.nan
        raise ValueError("A zero population can only have zero examined units and zero successes")
    if n_h == 0:
        if X_h != 0:
            raise ValueError("X_h must be zero when n_h is zero")
        return math.nan, math.nan

    p_hat = X_h / n_h

    # If the whole finite population was examined, there is no sampling
    # uncertainty left for this descriptive interval.
    if fpc_n == N_h:
        lower = upper = p_hat
    else:
        if N_h == 1:
            # The only non-census N=1 combination would imply no examined unit,
            # which was handled above.
            raise ValueError("N_h=1 with n_h>0 requires fpc_sample_size=1")
        z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
        c_h = (N_h - fpc_n) / (N_h - 1.0)
        a_h = z**2 * c_h / n_h
        delta = math.sqrt(a_h * p_hat * (1.0 - p_hat) + a_h**2 / 4.0)

        lower = (p_hat + a_h / 2.0 - delta) / (1.0 + a_h)
        upper = (p_hat + a_h / 2.0 + delta) / (1.0 + a_h)
        lower = max(0.0, lower)
        upper = min(1.0, upper)

    if digits is not None:
        if not isinstance(digits, int) or digits < 0:
            raise ValueError("digits must be a non-negative integer or None")
        lower, upper = round(lower, digits), round(upper, digits)

    return lower, upper
