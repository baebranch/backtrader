import json

import backtrader as bt
import pytest

from phase0_support import (
  FIXTURES,
  BarCapture,
  MultiDataCapture,
  NotificationCSVData,
  NotificationCapture,
  TriStateFeed,
  daily_feed,
  intraday_feed,
)


def expected_modes():
  path = FIXTURES / "expected" / "phase0_data_modes.json"
  return json.loads(path.read_text(encoding="utf-8"))


def run_multi_data(runonce):
  cerebro = bt.Cerebro(runonce=runonce, preload=True, stdstats=False)
  cerebro.adddata(daily_feed())
  cerebro.adddata(daily_feed("phase0_daily_secondary_missing.csv", "secondary"))
  cerebro.addstrategy(MultiDataCapture)
  return cerebro.run()[0].timeline


@pytest.mark.parametrize("runonce", [True, False])
def test_missing_and_short_secondary_feed_has_stable_clock_behavior(runonce):
  assert run_multi_data(runonce) == expected_modes()["multiData"]


@pytest.mark.parametrize("runonce", [True, False])
def test_resampled_ohlcv_is_stable_across_execution_modes(runonce):
  cerebro = bt.Cerebro(runonce=runonce, preload=True, stdstats=False)
  cerebro.resampledata(
    intraday_feed(), timeframe=bt.TimeFrame.Minutes, compression=15
  )
  cerebro.addstrategy(BarCapture)
  assert cerebro.run()[0].bars == expected_modes()["resample"]


def test_replay_preserves_partial_bar_evolution():
  cerebro = bt.Cerebro(runonce=False, preload=False, stdstats=False)
  cerebro.replaydata(
    intraday_feed(), timeframe=bt.TimeFrame.Minutes, compression=15
  )
  cerebro.addstrategy(BarCapture)
  assert cerebro.run()[0].bars == expected_modes()["replay"]


def test_feed_load_distinguishes_bar_waiting_and_exhausted_states():
  cerebro = bt.Cerebro(stdstats=False)
  data = TriStateFeed()
  cerebro.adddata(data)
  data.reset()
  data._start()
  try:
    assert data.load() is True
    assert len(data) == 1
    assert data.close[0] == 101.0

    assert data.load() is None
    assert len(data) == 1

    assert data.load() is True
    assert len(data) == 2
    assert data.close[0] == 102.0

    assert data.load() is False
    assert len(data) == 2
  finally:
    data.stop()


def test_data_notifications_preserve_status_and_payload_order():
  data = NotificationCSVData(
    dataname=str(FIXTURES / "phase0_daily_primary.csv"),
    dtformat="%Y-%m-%d",
    timeframe=bt.TimeFrame.Days,
    name="primary",
  )
  cerebro = bt.Cerebro(runonce=False, preload=False, stdstats=False)
  cerebro.adddata(data)
  cerebro.addstrategy(NotificationCapture)
  strategy = cerebro.run()[0]
  assert strategy.notifications == [
    ("DELAYED", ("waiting",), {}),
    ("LIVE", ("ready",), {}),
  ]
