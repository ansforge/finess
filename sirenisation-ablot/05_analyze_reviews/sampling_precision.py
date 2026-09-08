"""Simple per-stratum sampling-precision indicator.

The function in this module reports a conservative 95% margin of error for a
proportion, using only the number of examined entities (n) and the stratum
population size (N).

It assumes simple random sampling within the stratum and uses p=0.5, the
worst-case proportion because it gives the largest standard error. A finite-
population correction reduces the margin of error when a large share of the
population has been examined::

    MOE = z * sqrt[p(1-p) / n] * sqrt[(N-n) / (N-1)]

The result is returned in percentage points, so ``8.25`` means ``±8.25%`` at
the requested confidence level. If the whole population is examined, the
margin of error is 0. If no entity is examined, precision is undefined and the
function returns ``None``.

For a two-stage/clustered design (notably the EGE workflow), this is a useful
"examined versus population" descriptive indicator, but not a full design-
based variance estimate; clustering can make the true sampling uncertainty
larger or smaller depending on the design and within-cluster correlation.
"""

from __future__ import annotations

import math
from statistics import NormalDist


def finite_population_margin_of_error_pct(
    sample_size: float,
    population_size: float,
    *,
    confidence_level: float = 0.95,
    assumed_proportion: float = 0.5,
) -> float | None:
    """Return a finite-population margin of error in percentage points.

    Parameters
    ----------
    sample_size:
        Number of examined entities in the stratum (n).
    population_size:
        Total number of entities in the stratum (N).
    confidence_level:
        Two-sided confidence level. Defaults to 0.95.
    assumed_proportion:
        Proportion used for the standard-error calculation. The default 0.5 is
        conservative because it maximizes p(1-p).

    Returns
    -------
    float | None
        Margin of error in percentage points. ``None`` means undefined because
        the population or examined sample is empty.
    """

    n = float(sample_size)
    N = float(population_size)

    if not math.isfinite(n) or not math.isfinite(N):
        raise ValueError("sample_size and population_size must be finite numbers")
    if n < 0 or N < 0:
        raise ValueError("sample_size and population_size must be non-negative")
    if n > N:
        raise ValueError("sample_size cannot exceed population_size")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be strictly between 0 and 1")
    if not 0 <= assumed_proportion <= 1:
        raise ValueError("assumed_proportion must be between 0 and 1")

    if N == 0 or n == 0:
        return None
    if n == N:
        return 0.0

    z = NormalDist().inv_cdf((1.0 + confidence_level) / 2.0)
    variance = assumed_proportion * (1.0 - assumed_proportion) / n
    fpc = math.sqrt((N - n) / (N - 1.0)) if N > 1 else 0.0
    margin_fraction = z * math.sqrt(variance) * fpc
    return round(100.0 * margin_fraction, 2)
