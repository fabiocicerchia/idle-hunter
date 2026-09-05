"""The shapes this package moves between its modules.

The AWS-facing ones stay dicts: they are boto3 responses, and every reader here
uses `.get` because the fields it wants are optional in one API version or
another. `Finding` is the one thing that becomes a class, because its field
order is the JSON output order.
"""

from collections.abc import Callable
from typing import Any

# A boto3 client, or the fake a test passes in its place.
Client = Any
# A boto3 session, likewise.
Session = Any
# One AWS resource as its describe/list call returns it.
Resource = dict[str, Any]
# A resource's tag list: [{"Key": ..., "Value": ...}].
Tags = list[dict[str, str]]
# The per-region price lookup a scanner is handed, so it never has to know
# whether the number came from the Pricing API or the bundled default.
PriceOf = Callable[..., float]
