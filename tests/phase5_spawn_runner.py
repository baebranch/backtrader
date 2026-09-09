"""Fresh-process characterization for generated Backtrader classes."""
import json
import multiprocessing
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import backtrader as bt

from core.backtrader_compat import StrategyRegistration, StrategyRegistry


class SpawnParameters(bt.metabase.ParamsBase):
  params = (("alpha", 1),)


class SpawnDerivedParameters(SpawnParameters):
  params = (("alpha", 3), ("beta", 2))


class SpawnBaseLines(bt.Indicator):
  lines = ("base",)


class SpawnDerivedLines(SpawnBaseLines):
  alias = ("SpawnLinesAlias",)
  lines = ("derived",)


def characterize(queue):
  params = SpawnDerivedParameters(alpha=7)
  restored_params = pickle.loads(pickle.dumps(params))
  restored_lines = pickle.loads(pickle.dumps(SpawnDerivedLines.lines))
  registry = StrategyRegistry()
  registry.register(StrategyRegistration(
    "Spawn", "phase5_spawn_runner", "SpawnParameters", structures=("child",)
  ))
  target = registry.resolve("Spawn", "child")
  queue.put({
    "aliases": list(restored_lines.getlinealiases()),
    "params": dict(restored_params.p._getkwargs()),
    "registry": target.__name__,
  })


def main():
  context = multiprocessing.get_context("spawn")
  queue = context.Queue()
  process = context.Process(target=characterize, args=(queue,))
  process.start()
  process.join(20)
  if process.is_alive():
    process.terminate()
    process.join(5)
    raise RuntimeError("Phase 5 spawn child timed out")
  if process.exitcode != 0:
    raise RuntimeError(f"Phase 5 spawn child exited with {process.exitcode}")
  print(json.dumps(queue.get(timeout=5), sort_keys=True))


if __name__ == "__main__":
  main()
