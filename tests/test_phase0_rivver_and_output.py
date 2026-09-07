import json

import backtrader as bt
import pytest

from core.modifiers.forex_broker import ForexBackBroker
from core.modifiers.trade_data import TradeData
from phase0_support import (
  FIXTURES,
  FixedCommission,
  Phase0Result,
  Phase0Strategy,
  ShortPhase0Strategy,
  WriterStrategy,
  daily_feed,
)


def configured_forex_broker():
  broker = ForexBackBroker()
  broker.setcash(1000)
  broker.set_avgspread({"primary": 2}, {"primary": 0.01})
  broker.set_dospread(True)
  broker.set_useask(False)
  broker.addcommissioninfo(FixedCommission(), name="primary")
  return broker


def test_forex_spread_adjustment_contract():
  broker = configured_forex_broker()
  broker.asset = "primary"
  assert broker._spread_up(100, 101) == pytest.approx((100.02, 101.02))
  assert broker._spread_down(100, 99) == pytest.approx((100, 99))

  broker.set_useask(True)
  assert broker._spread_up(100, 101) == pytest.approx((100, 101))
  assert broker._spread_down(100, 99) == pytest.approx((99.98, 98.98))

  broker.set_dospread(False)
  assert broker._spread_up(100, 101) == (100, 101)
  assert broker._spread_down(100, 99) == (100, 99)


def run_forex_scenario(strategy_class=Phase0Strategy, useask=False):
  cerebro = bt.Cerebro(stdstats=False, tradehistory=True)
  cerebro.adddata(daily_feed())
  broker = configured_forex_broker()
  broker.set_useask(useask)
  cerebro.broker = broker
  cerebro.addstrategy(strategy_class)
  cerebro.addanalyzer(Phase0Result, _name="phase0")
  cerebro.addanalyzer(TradeData, _name="trade_data")
  return cerebro.run()[0]


def test_forex_accounting_and_trade_data_schema_are_stable():
  strategy = run_forex_scenario()
  result = strategy.analyzers.phase0.get_analysis()
  completed = [order for order in result["orders"] if order["status"] == "Completed"]
  assert [order["price"] for order in completed] == pytest.approx([101.02, 104.0])
  assert result["bars"][1] == {
    "date": "2020-01-02",
    "cash": 999.5,
    "value": 1000.48,
    "position": 1.0,
  }
  assert result["finalCash"] == pytest.approx(1001.98)
  assert result["finalValue"] == pytest.approx(1001.98)
  assert result["trades"][-1]["pnl"] == pytest.approx(2.98)
  assert result["trades"][-1]["pnlcomm"] == pytest.approx(1.98)

  analysis = strategy.analyzers.trade_data.get_analysis()
  trade = next(iter(analysis["primary"].values()))
  assert list(trade) == [
    "size", "symbol", "ticket", "open_dt", "close_dt", "type",
    "open_price", "close_price", "commission", "pnl",
  ]
  assert trade["symbol"] == "primary"
  assert trade["type"] == "buy"
  assert trade["open_dt"] == "2020-01-02 23:59:59.999989"
  assert trade["close_dt"] == "2020-01-05 23:59:59.999989"
  assert trade["open_price"] == pytest.approx(101.02)
  assert trade["close_price"] == pytest.approx(104.0)
  assert trade["commission"] == pytest.approx(1.0)
  assert trade["pnl"] == pytest.approx(2.98)
  json.dumps({"primary": [dict(trade)]})


def test_writer_output_matches_complete_golden_file():
  cerebro = bt.Cerebro(stdstats=False)
  cerebro.adddata(daily_feed())
  cerebro.addstrategy(WriterStrategy)
  cerebro.addwriter(bt.WriterStringIO, csv=True)
  cerebro.run()

  actual = "".join(cerebro.runwriters[0].out).replace("\r\n", "\n").strip()
  expected = (
    FIXTURES / "expected" / "phase0_writer.txt"
  ).read_text(encoding="utf-8").strip()
  assert actual == expected
  assert actual.splitlines()[1].startswith("Id,primary,len,openinterest")
  assert sum(line.startswith(tuple(str(i) for i in range(1, 9))) for line in actual.splitlines()) == 8


def test_forex_short_trade_and_ask_side_spread_are_stable():
  strategy = run_forex_scenario(ShortPhase0Strategy, useask=True)
  result = strategy.analyzers.phase0.get_analysis()
  completed = [order for order in result["orders"] if order["status"] == "Completed"]
  assert [order["price"] for order in completed] == pytest.approx([100.98, 104.0])
  assert result["finalCash"] == pytest.approx(995.98)
  assert result["finalValue"] == pytest.approx(995.98)
  assert result["trades"][-1]["pnl"] == pytest.approx(-3.02)
  assert result["trades"][-1]["pnlcomm"] == pytest.approx(-4.02)

  trade = next(iter(strategy.analyzers.trade_data.get_analysis()["primary"].values()))
  assert trade["type"] == "sell"
  assert trade["open_price"] == pytest.approx(100.98)
  assert trade["close_price"] == pytest.approx(104.0)
  assert trade["commission"] == pytest.approx(1.0)
  assert trade["pnl"] == pytest.approx(-3.02)
