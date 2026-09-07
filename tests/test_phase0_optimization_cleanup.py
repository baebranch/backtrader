import json
import os
from pathlib import Path
import subprocess
import sys

import backtrader as bt
import pytest

from phase0_support import (
  FixedCommission,
  Phase0Result,
  Phase0Strategy,
  daily_feed,
)


def configure_cerebro(maxcpus=1):
  cerebro = bt.Cerebro(
    runonce=True,
    preload=True,
    maxcpus=maxcpus,
    stdstats=False,
  )
  cerebro.adddata(daily_feed())
  cerebro.broker.setcash(1000)
  cerebro.broker.addcommissioninfo(FixedCommission())
  cerebro.addanalyzer(Phase0Result, _name="phase0")
  return cerebro


def normal_results():
  results = {}
  for entry_bar in (1, 2, 3):
    cerebro = configure_cerebro()
    cerebro.addstrategy(Phase0Strategy, entry_bar=entry_bar)
    strategy = cerebro.run()[0]
    results[entry_bar] = strategy.analyzers.phase0.get_analysis()
  return results


def optimized_results(maxcpus):
  cerebro = configure_cerebro(maxcpus=maxcpus)
  cerebro.optstrategy(Phase0Strategy, entry_bar=(1, 2, 3))
  runs = cerebro.run()
  return {
    run[0].p.entry_bar: run[0].analyzers.phase0.get_analysis()
    for run in runs
  }


def run_isolated(mode="success", timeout=30):
  runner = Path(__file__).with_name("phase0_spawn_runner.py")
  process = subprocess.Popen(
    [sys.executable, str(runner), mode],
    cwd=runner.parents[3],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
  )
  try:
    stdout, stderr = process.communicate(timeout=timeout)
    return process.returncode, stdout, stderr, False
  except subprocess.TimeoutExpired:
    subprocess.run(
      ["taskkill", "/PID", str(process.pid), "/T", "/F"],
      capture_output=True,
      check=False,
    )
    stdout, stderr = process.communicate(timeout=5)
    return process.returncode, stdout, stderr, True


def isolated_spawn_results():
  returncode, stdout, stderr, timed_out = run_isolated()
  assert timed_out is False
  assert returncode == 0, stderr
  return json.loads(stdout)


def test_optimized_and_unoptimized_results_are_equivalent():
  expected = normal_results()
  assert optimized_results(maxcpus=1) == expected


@pytest.mark.skipif(os.name != "nt", reason="Characterizes Windows spawn semantics")
def test_windows_spawn_optimization_returns_results_and_closes_workers():
  expected = json.loads(json.dumps(optimized_results(maxcpus=1), sort_keys=True))
  assert isolated_spawn_results() == expected


@pytest.mark.skipif(os.name != "nt", reason="Characterizes Windows spawn semantics")
def test_windows_spawn_worker_failure_propagates_and_pool_closes():
  returncode, _, stderr, timed_out = run_isolated("failure")
  assert timed_out is False
  assert returncode != 0
  assert "phase0 worker failure" in stderr


@pytest.mark.skipif(os.name != "nt", reason="Characterizes Windows spawn semantics")
def test_windows_spawn_interruption_kills_the_process_tree():
  returncode, _, _, timed_out = run_isolated("hang", timeout=2)
  assert timed_out is True
  assert returncode is not None
