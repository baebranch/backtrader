import pickle
from datetime import datetime, timezone

import pytest

from backtrader.linebuffer import LineBuffer
from backtrader.utils.dateintern import date2num, num2date
from phase0_support import DerivedParameterHolder


def test_unbounded_line_buffer_pointer_and_binding_contract():
  source = LineBuffer()
  target = LineBuffer()
  source.forward()
  target.forward()
  source.addbinding(target)
  source[0] = 10
  assert target[0] == 10

  source.forward()
  target.forward()
  source[0] = 20
  assert source[0] == 20
  assert source[-1] == 10
  assert source.get(size=2).tolist() == [10, 20]
  assert len(source) == 2

  source.backwards()
  assert len(source) == 1
  assert source[0] == 10
  assert source.buflen() == 1


def test_qbuffer_retains_minimum_period_while_logical_length_advances():
  line = LineBuffer()
  line._minperiod = 3
  line.qbuffer()
  for value in range(1, 6):
    line.forward()
    line[0] = value

  assert len(line) == 5
  assert line.buflen() == 3
  assert line.idx == 2
  assert line.get(size=3) == [3, 4, 5]
  assert line[0] == 5


def test_generated_parameter_values_inherit_override_and_pickle():
  holder = DerivedParameterHolder(alpha=7)
  assert holder.p.alpha == 7
  assert holder.p.beta == 2
  restored = pickle.loads(pickle.dumps(holder))
  assert restored.p._getkwargs() == holder.p._getkwargs()


@pytest.mark.parametrize(
  "value",
  [
    datetime(2020, 1, 2, 3, 4, 5, 123456),
    datetime(2020, 6, 1, 12, 30, tzinfo=timezone.utc),
  ],
)
def test_ordinal_datetime_round_trip_contract(value):
  restored = num2date(date2num(value), tz=value.tzinfo, naive=value.tzinfo is None)
  if value.tzinfo is not None:
    assert restored.tzinfo is not None
  assert abs((restored.replace(tzinfo=None) - value.replace(tzinfo=None)).total_seconds()) < 0.00002
