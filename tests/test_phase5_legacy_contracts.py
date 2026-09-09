import json
import os
from pathlib import Path
import subprocess
import sys

import backtrader as bt
import pytest

from phase0_support import Phase0Strategy, daily_feed


class LeftParameters(bt.metabase.ParamsBase):
  params = (("shared", "left"), ("left", 1))


class RightParameters(bt.metabase.ParamsBase):
  params = (("shared", "right"), ("right", 2))


class CombinedParameters(LeftParameters, RightParameters):
  params = (("shared", "combined"), ("child", 3))

  def __init__(self, **kwargs):
    self.init_params = self.p._getkwargs()
    self.remaining_kwargs = kwargs


class BaseLines(bt.Indicator):
  lines = ("base",)
  plotinfo = dict(plotname="base")
  plotlines = dict(base=dict(color="blue"))


class DerivedLines(BaseLines):
  lines = ("derived",)
  linealias = dict(derived="signal")
  plotinfo = dict(subplot=True)


class OwnerIndicator(bt.Indicator):
  lines = ("value",)

  def __init__(self):
    self.lines.value = self.data


class OwnerStrategy(bt.Strategy):
  def __init__(self):
    self.indicator = OwnerIndicator()


def test_params_are_available_before_init_and_preserve_alias_order_and_kwargs():
  instance = CombinedParameters(shared="runtime", unknown="retained")

  assert instance.p is instance.params
  assert instance.init_params == {
    "shared": "runtime", "left": 1, "right": 2, "child": 3
  }
  assert tuple(instance.params._getkeys()) == (
    "shared", "left", "right", "child"
  )
  assert instance.remaining_kwargs == {"unknown": "retained"}


def test_generated_lines_aliases_and_plot_metadata_preserve_inheritance():
  assert DerivedLines.lines.getlinealiases() == ("base", "derived")
  assert DerivedLines.lines._getlinesbase() == ("base",)
  assert isinstance(
    vars(DerivedLines.lines)["signal"], bt.lineseries.LineAlias
  )
  assert DerivedLines.plotinfo.plotname == "base"
  assert DerivedLines.plotinfo.subplot is True
  assert DerivedLines.plotlines.base.color == "blue"


def test_owner_discovery_and_indicator_registration_remain_legacy_controlled():
  cerebro = bt.Cerebro(stdstats=False, maxcpus=1)
  cerebro.adddata(daily_feed())
  cerebro.addstrategy(OwnerStrategy)
  strategy = cerebro.run()[0]

  assert strategy.indicator._owner is strategy
  assert strategy.indicator in strategy.getindicators()


def test_strategy_lifecycle_order_remains_stable():
  cerebro = bt.Cerebro(stdstats=False, maxcpus=1)
  cerebro.adddata(daily_feed())
  cerebro.addstrategy(Phase0Strategy)
  strategy = cerebro.run()[0]

  assert strategy.lifecycle[0] == "start"
  assert strategy.lifecycle[-1] == "stop"
  assert any(event.startswith("nextstart:") for event in strategy.lifecycle)
  assert strategy.lifecycle.index("start") < strategy.lifecycle.index("stop")


def test_in_tree_integrations_no_longer_declare_package_injection():
  from backtrader.analyzers.calmar import Calmar
  from backtrader.feeds.influxfeed import InfluxDB
  from backtrader.indicators.hurst import HurstExponent
  from backtrader.indicators.ols import CointN, OLS_BetaN, OLS_Slope_InterceptN

  for cls in (
    Calmar, InfluxDB, HurstExponent, CointN, OLS_BetaN,
    OLS_Slope_InterceptN,
  ):
    assert cls.packages == ()
    assert cls.frompackages == ()


def _run_spawn_runner(timeout=30):
  runner = Path(__file__).with_name("phase5_spawn_runner.py")
  process = subprocess.Popen(
    [sys.executable, str(runner)],
    cwd=runner.parents[3],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
  )
  try:
    stdout, stderr = process.communicate(timeout=timeout)
  except subprocess.TimeoutExpired:
    subprocess.run(
      ["taskkill", "/PID", str(process.pid), "/T", "/F"],
      capture_output=True,
      check=False,
    )
    process.communicate(timeout=5)
    pytest.fail("Phase 5 spawn runner timed out")
  assert process.returncode == 0, stderr
  return json.loads(stdout)


@pytest.mark.skipif(os.name != "nt", reason="Characterizes Windows spawn semantics")
def test_fresh_windows_spawn_reconstructs_generated_classes_and_registry():
  assert _run_spawn_runner() == {
    "aliases": ["base", "derived"],
    "params": {"alpha": 7, "beta": 2},
    "registry": "SpawnParameters",
  }


_lifecycle_events = []


class CharacterizedMeta(bt.metabase.MetaBase):
  def doprenew(cls, *args, **kwargs):
    _lifecycle_events.append("doprenew")
    return super().doprenew(*args, **kwargs)

  def donew(cls, *args, **kwargs):
    _lifecycle_events.append("donew")
    return super().donew(*args, **kwargs)

  def dopreinit(cls, instance, *args, **kwargs):
    _lifecycle_events.append("dopreinit")
    return super().dopreinit(instance, *args, **kwargs)

  def doinit(cls, instance, *args, **kwargs):
    _lifecycle_events.append("doinit")
    return super().doinit(instance, *args, **kwargs)

  def dopostinit(cls, instance, *args, **kwargs):
    _lifecycle_events.append("dopostinit")
    return super().dopostinit(instance, *args, **kwargs)


class CharacterizedLifecycle(metaclass=CharacterizedMeta):
  def __init__(self):
    _lifecycle_events.append("init")


def test_metabase_five_stage_construction_order_remains_stable():
  _lifecycle_events.clear()
  CharacterizedLifecycle()
  assert _lifecycle_events == [
    "doprenew", "donew", "dopreinit", "doinit", "init", "dopostinit"
  ]


def test_optional_indicator_dependencies_are_resolved_only_when_requested():
  from importlib.util import find_spec
  from backtrader.indicators import hurst, ols

  assert hurst._numpy().__name__ == "numpy"
  assert ols._pandas().__name__ == "pandas"
  if find_spec("statsmodels") is None:
    with pytest.raises(ImportError, match="optional statsmodels package"):
      ols._statsmodels()
    with pytest.raises(ImportError, match="optional statsmodels package"):
      ols._coint()
  else:
    assert ols._statsmodels().__name__ == "statsmodels.api"
    assert ols._coint().__name__ == "coint"


def test_influx_optional_dependency_has_clear_lazy_diagnostic(monkeypatch):
  import builtins
  from backtrader.feeds import influxfeed

  original_import = builtins.__import__

  def blocked_import(name, *args, **kwargs):
    if name == "influxdb" or name.startswith("influxdb."):
      raise ImportError("blocked for characterization")
    return original_import(name, *args, **kwargs)

  monkeypatch.setattr(builtins, "__import__", blocked_import)
  with pytest.raises(ImportError, match="optional influxdb package"):
    influxfeed._influx_dependencies()
