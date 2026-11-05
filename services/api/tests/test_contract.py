import json
from datetime import datetime, UTC
from pathlib import Path
import pytest
from pydantic import ValidationError
from kkulpick.models import Observation


def fixture():
    return dict(json.loads((Path(__file__).parents[1]/"fixtures"/"offer.json").read_text(encoding="utf8")),
                observation_key="unit",observed_at=datetime.now(UTC).isoformat())


@pytest.mark.parametrize("patch",[{"price":1.1},{"price":"-5"},{"currency":None},{"field_presence":["price"]},
                                  {"url":"https://localhost/private"},{"schema_version":3},{"unexpected":True}])
def test_reject_invalid(patch):
    with pytest.raises(ValidationError):
        Observation(**(fixture()|patch))


def test_valid():
    assert Observation(**fixture()).variant_key=="blue-1l"
