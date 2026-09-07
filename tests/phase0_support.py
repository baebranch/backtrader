from pathlib import Path
import datetime as dt
import time

import backtrader as bt


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class Phase0CSVData(bt.feeds.GenericCSVData):
  params = (("spread", -1),)


def daily_feed(filename="phase0_daily_primary.csv", name="primary"):
  return Phase0CSVData(
    dataname=str(FIXTURES / filename),
    dtformat="%Y-%m-%d",
    timeframe=bt.TimeFrame.Days,
    name=name,
  )


def intraday_feed(name="intraday"):
  return Phase0CSVData(
    dataname=str(FIXTURES / "phase0_intraday_5m.csv"),
    dtformat="%Y-%m-%d %H:%M:%S",
    timeframe=bt.TimeFrame.Minutes,
    compression=5,
    name=name,
  )


def rounded(value):
  return round(float(value), 6)


def date_text(value):
  return bt.num2date(value).date().isoformat()


class FixedCommission(bt.CommInfoBase):
  params = (
    ("commission", 0.5),
    ("commtype", bt.CommInfoBase.COMM_FIXED),
    ("stocklike", True),
  )


class Phase0Strategy(bt.Strategy):
  params = (("entry_bar", 1), ("hold_bars", 3))

  def __init__(self):
    self.lifecycle = []
    self.pending_order = None

  def start(self):
    self.lifecycle.append("start")

  def prenext(self):
    self.lifecycle.append(f"prenext:{self.datetime.date(0).isoformat()}")

  def nextstart(self):
    self.lifecycle.append(f"nextstart:{self.datetime.date(0).isoformat()}")
    super().nextstart()

  def next(self):
    self.lifecycle.append(f"next:{self.datetime.date(0).isoformat()}")
    if self.pending_order:
      return
    if len(self) == self.p.entry_bar and not self.position:
      self.pending_order = self.buy(size=1)
    elif len(self) == self.p.entry_bar + self.p.hold_bars and self.position:
      self.pending_order = self.close()

  def notify_order(self, order):
    if order.status not in {order.Submitted, order.Accepted}:
      self.pending_order = None

  def stop(self):
    self.lifecycle.append("stop")


class FailingOptimizationStrategy(Phase0Strategy):
  params = (("fail", False),)

  def next(self):
    if self.p.fail:
      raise RuntimeError("phase0 worker failure")
    super().next()


class HangingOptimizationStrategy(Phase0Strategy):
  params = (("hang", False),)

  def next(self):
    if self.p.hang:
      time.sleep(60)
    super().next()


class Phase0Result(bt.Analyzer):
  def start(self):
    self.order_ids = {}
    self.orders = []
    self.trades = []
    self.bars = []
    self.result = {}

  def notify_order(self, order):
    order_id = self.order_ids.setdefault(order.ref, len(self.order_ids) + 1)
    complete = order.status == order.Completed
    dt = order.executed.dt if complete else order.created.dt
    self.orders.append({
      "id": order_id,
      "side": "buy" if order.isbuy() else "sell",
      "status": order.getstatusname(),
      "date": date_text(dt),
      "size": rounded(order.executed.size if complete else order.created.size),
      "price": rounded(order.executed.price) if complete else None,
      "commission": rounded(order.executed.comm) if complete else None,
    })

  def notify_trade(self, trade):
    state = "opened" if trade.justopened else "closed" if trade.isclosed else "updated"
    self.trades.append({
      "state": state,
      "date": self.strategy.datetime.date(0).isoformat(),
      "size": rounded(trade.size),
      "price": rounded(trade.price),
      "pnl": rounded(trade.pnl),
      "pnlcomm": rounded(trade.pnlcomm),
    })

  def next(self):
    self.bars.append({
      "date": self.strategy.datetime.date(0).isoformat(),
      "cash": rounded(self.strategy.broker.getcash()),
      "value": rounded(self.strategy.broker.getvalue()),
      "position": rounded(self.strategy.position.size),
    })

  def stop(self):
    self.result = {
      "entryBar": self.strategy.p.entry_bar,
      "lifecycle": list(self.strategy.lifecycle),
      "bars": self.bars,
      "orders": self.orders,
      "trades": self.trades,
      "finalCash": rounded(self.strategy.broker.getcash()),
      "finalValue": rounded(self.strategy.broker.getvalue()),
      "finalPosition": rounded(self.strategy.position.size),
    }

  def get_analysis(self):
    return self.result


class MultiDataCapture(bt.Strategy):
  def __init__(self):
    self.timeline = []

  def next(self):
    self.timeline.append({
      "clock": self.datetime.date(0).isoformat(),
      "primaryLength": len(self.datas[0]),
      "secondaryLength": len(self.datas[1]),
      "primaryDate": self.datas[0].datetime.date(0).isoformat(),
      "secondaryDate": self.datas[1].datetime.date(0).isoformat(),
      "secondaryClose": rounded(self.datas[1].close[0]),
    })
class BarCapture(bt.Strategy):
  def __init__(self):
    self.bars = []

  def next(self):
    self.bars.append({
      "length": len(self),
      "datetime": self.datetime.datetime(0).isoformat(),
      "open": rounded(self.data.open[0]),
      "high": rounded(self.data.high[0]),
      "low": rounded(self.data.low[0]),
      "close": rounded(self.data.close[0]),
      "volume": rounded(self.data.volume[0]),
    })


class WriterStrategy(bt.Strategy):
  def next(self):
    pass


class TriStateFeed(bt.feed.DataBase):
  def __init__(self):
    self.responses = iter((True, None, True, False))
    self.bar = 0

  def _load(self):
    response = next(self.responses)
    if response is not True:
      return response
    self.bar += 1
    value = 100.0 + self.bar
    self.lines.datetime[0] = bt.date2num(dt.datetime(2020, 1, self.bar))
    for line in (self.lines.open, self.lines.high, self.lines.low, self.lines.close):
      line[0] = value
    self.lines.volume[0] = self.bar
    self.lines.openinterest[0] = 0
    return True


class BaseParameterHolder(bt.metabase.ParamsBase):
  params = (("alpha", 1),)


class DerivedParameterHolder(BaseParameterHolder):
  params = (("alpha", 3), ("beta", 2))


class ShortPhase0Strategy(Phase0Strategy):
  def next(self):
    self.lifecycle.append(f"next:{self.datetime.date(0).isoformat()}")
    if self.pending_order:
      return
    if len(self) == self.p.entry_bar and not self.position:
      self.pending_order = self.sell(size=1)
    elif len(self) == self.p.entry_bar + self.p.hold_bars and self.position:
      self.pending_order = self.close()


class NotificationCSVData(Phase0CSVData):
  def start(self):
    super().start()
    self.put_notification(self.DELAYED, "waiting")
    self.put_notification(self.LIVE, "ready")


class NotificationCapture(bt.Strategy):
  def __init__(self):
    self.notifications = []

  def notify_data(self, data, status, *args, **kwargs):
    self.notifications.append((data._getstatusname(status), args, kwargs))
