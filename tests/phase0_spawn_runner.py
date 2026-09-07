"""Isolated Windows-spawn characterization harness for Phase 0."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backtrader as bt

from phase0_support import (
  FailingOptimizationStrategy,
  FixedCommission,
  HangingOptimizationStrategy,
  Phase0Result,
  Phase0Strategy,
  daily_feed,
)


def main():
  mode = sys.argv[1] if len(sys.argv) > 1 else "success"
  strategy = {
    "success": Phase0Strategy,
    "failure": FailingOptimizationStrategy,
    "hang": HangingOptimizationStrategy,
  }[mode]
  parameters = {"entry_bar": (1, 2, 3)}
  if mode == "failure":
    parameters["fail"] = (False, True)
  elif mode == "hang":
    parameters["hang"] = (True,)

  cerebro = bt.Cerebro(runonce=True, preload=True, maxcpus=2, stdstats=False)
  cerebro.adddata(daily_feed())
  cerebro.broker.setcash(1000)
  cerebro.broker.addcommissioninfo(FixedCommission())
  cerebro.addanalyzer(Phase0Result, _name="phase0")
  cerebro.optstrategy(strategy, **parameters)
  runs = cerebro.run()
  results = {
    run[0].p.entry_bar: run[0].analyzers.phase0.get_analysis()
    for run in runs
  }
  print(json.dumps(results, sort_keys=True))


if __name__ == "__main__":
  main()
