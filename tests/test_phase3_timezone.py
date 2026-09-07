from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import backtrader as bt
import pytest

from backtrader.filters.session import _is_session_time, _session_bounds
from backtrader.tradingcal import TradingCalendar
from backtrader.utils.dateintern import (
  date2num,
  localize,
  num2date,
  tzparse,
)


def assert_close(left, right):
  assert abs((left - right).total_seconds()) < 0.00002


def test_timezone_resolution_accepts_public_forms_and_rejects_unknown_names():
  utc = timezone.utc
  assert tzparse(None) is None
  assert tzparse(utc) is utc
  assert tzparse("UTC").key == "UTC"
  assert tzparse("Asia/Kolkata").key == "Asia/Kolkata"
  assert tzparse("CST").key == "CST6CDT"
  with pytest.raises(ValueError, match="unknown timezone"):
    tzparse("Not/A_Timezone")


def test_dst_wall_time_policy_is_explicit_for_folds_and_gaps():
  new_york = ZoneInfo("America/New_York")
  ambiguous = localize(datetime(2024, 11, 3, 1, 30), new_york)
  assert ambiguous.fold == 1
  assert ambiguous.astimezone(timezone.utc) == datetime(
    2024, 11, 3, 6, 30, tzinfo=timezone.utc
  )

  nonexistent = localize(datetime(2024, 3, 10, 2, 30), new_york)
  assert nonexistent.replace(tzinfo=None) == datetime(2024, 3, 10, 3, 30)
  assert nonexistent.astimezone(timezone.utc) == datetime(
    2024, 3, 10, 7, 30, tzinfo=timezone.utc
  )


def test_ordinal_round_trips_preserve_utc_and_non_dst_zone_contracts():
  value = datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc)
  assert_close(num2date(date2num(value), tz=timezone.utc, naive=False), value)

  kolkata = ZoneInfo("Asia/Kolkata")
  wall_time = datetime(2024, 3, 10, 12, 15)
  encoded = date2num(wall_time, tz=kolkata)
  restored = num2date(encoded, tz=kolkata, naive=False)
  assert_close(restored, wall_time.replace(tzinfo=kolkata))
  assert restored.utcoffset().total_seconds() == 5.5 * 60 * 60


@pytest.mark.parametrize(
  "zone, current, expected_open, expected_close, elapsed_hours",
  [
    (
      "America/New_York",
      datetime(2024, 3, 10, 5),
      datetime(2024, 3, 10, 3),
      datetime(2024, 3, 10, 7),
      4,
    ),
    (
      "America/New_York",
      datetime(2024, 11, 3, 4),
      datetime(2024, 11, 3, 2),
      datetime(2024, 11, 3, 8),
      6,
    ),
    (
      "Asia/Kolkata",
      datetime(2024, 1, 1, 18, 30),
      datetime(2024, 1, 1, 16, 30),
      datetime(2024, 1, 1, 21, 30),
      5,
    ),
  ],
)
def test_overnight_calendar_preserves_real_elapsed_time_across_zones(
    zone, current, expected_open, expected_close, elapsed_hours):
  calendar = TradingCalendar(open=time(22), close=time(3), offdays=[])
  opening, closing = calendar.schedule(current, tz=tzparse(zone))
  assert opening == expected_open
  assert closing == expected_close
  assert (closing - opening).total_seconds() == elapsed_hours * 60 * 60


def test_cross_midnight_session_membership_and_bounds():
  start, end = time(22), time(2)
  assert _is_session_time(time(23), start, end)
  assert _is_session_time(time(1), start, end)
  assert not _is_session_time(time(12), start, end)
  assert _session_bounds(datetime(2024, 1, 2, 1), start, end) == (
    datetime(2024, 1, 1, 22), datetime(2024, 1, 2, 2)
  )


class Phase3CSVData(bt.feeds.GenericCSVData):
  params = (("spread", 6),)


class CaptureDatetime(bt.Strategy):
  def __init__(self):
    self.values = []

  def next(self):
    self.values.append((
      self.data.datetime.datetime(0),
      self.data.datetime.datetime(0, naive=False),
    ))


def test_feed_tzinput_uses_fold_policy_and_output_zone(tmp_path):
  source = tmp_path / "ambiguous.csv"
  source.write_text(
    "2024-11-03 01:30:00,1,2,0,1.5,10,0\n",
    encoding="utf-8",
  )
  feed = Phase3CSVData(
    dataname=str(source),
    headers=False,
    dtformat="%Y-%m-%d %H:%M:%S",
    timeframe=bt.TimeFrame.Minutes,
    openinterest=-1,
    tzinput="America/New_York",
    tz="America/New_York",
  )
  cerebro = bt.Cerebro(stdstats=False)
  cerebro.adddata(feed)
  cerebro.addstrategy(CaptureDatetime)
  values = cerebro.run()[0].values
  assert values[0][0] == datetime(2024, 11, 3, 1, 30)
  assert values[0][1].fold == 1
  assert values[0][1].astimezone(timezone.utc) == datetime(
    2024, 11, 3, 6, 30, tzinfo=timezone.utc
  )
