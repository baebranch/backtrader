import json
import math

import backtrader as bt
import pytest

from phase0_support import (
  FIXTURES,
  FixedCommission,
  Phase0Result,
  Phase0Strategy,
  daily_feed,
)


def run_scenario(runonce, exactbars):
  cerebro = bt.Cerebro(
    runonce=runonce,
    preload=True,
    exactbars=exactbars,
    stdstats=False,
  )
  cerebro.adddata(daily_feed())
  cerebro.broker.setcash(1000)
  cerebro.broker.addcommissioninfo(FixedCommission())
  cerebro.addstrategy(Phase0Strategy)
  cerebro.addanalyzer(Phase0Result, _name="phase0")
  cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
  cerebro.addanalyzer(bt.analyzers.TimeReturn, _name="returns")
  return cerebro.run()[0]


@pytest.mark.parametrize(
  ("runonce", "exactbars"),
  [(True, False), (False, False), (True, -1), (False, -2)],
)
def test_trading_golden_is_stable_across_execution_and_memory_modes(
  runonce, exactbars
):
  strategy = run_scenario(runonce, exactbars)
  result = strategy.analyzers.phase0.get_analysis()
  expected_path = FIXTURES / "expected" / "phase0_trading.json"
  expected = json.loads(expected_path.read_text(encoding="utf-8"))

  assert result == expected
  assert json.loads(json.dumps(result, sort_keys=True)) == expected
  trades = strategy.analyzers.trades.get_analysis()
  assert trades.total.closed == 1
  assert trades.won.total == 1
  assert trades.pnl.net.total == pytest.approx(2.0)
  returns = strategy.analyzers.returns.get_analysis()
  cumulative_return = math.prod(1 + value for value in returns.values()) - 1
  assert cumulative_return == pytest.approx(0.002)
