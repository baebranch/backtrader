#!/usr/bin/env python
# -*- coding: utf-8; py-indent-offset:4 -*-
###############################################################################
#
# Copyright (C) 2015-2020 Daniel Rodriguez
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime
import math
import time as _time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .py3 import string_types


ZERO = datetime.timedelta(0)

STDOFFSET = datetime.timedelta(seconds=-_time.timezone)
if _time.daylight:
    DSTOFFSET = datetime.timedelta(seconds=-_time.altzone)
else:
    DSTOFFSET = STDOFFSET

DSTDIFF = DSTOFFSET - STDOFFSET

# To avoid rounding errors taking dates to next day
TIME_MAX = datetime.time(23, 59, 59, 999990)

# To avoid rounding errors taking dates to next day
TIME_MIN = datetime.time.min


def tzparse(tz):
    """Resolve a public timezone value without mutating the tzinfo object."""
    if tz is None:
        return None
    if not isinstance(tz, string_types):
        name = getattr(tz, 'key', None) or getattr(tz, 'zone', None)
        if isinstance(name, string_types):
            try:
                return ZoneInfo('CST6CDT' if name == 'CST' else name)
            except ZoneInfoNotFoundError:
                pass
        return Localizer(tz)

    name = 'CST6CDT' if tz == 'CST' else tz
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError('unknown timezone: {!r}'.format(tz)) from exc


def Localizer(tz):
    """Retain the compatibility symbol while avoiding method injection."""
    if tz is None or isinstance(tz, datetime.tzinfo):
        return tz
    raise TypeError('timezone must be a name or tzinfo instance')


def localize(dt, tz):
    """Attach ``tz`` to a wall time under Rivver's explicit DST policy.

    Ambiguous times select the later, standard-time occurrence (``fold=1``).
    Nonexistent times are shifted forward by the transition gap. Aware inputs
    preserve their instant and are converted with ``astimezone``.
    """
    tz = tzparse(tz)
    if tz is None:
        return dt
    if not isinstance(dt, datetime.datetime):
        raise TypeError('only datetime values can be localized')
    if dt.tzinfo is not None:
        return dt.astimezone(tz)

    first = dt.replace(tzinfo=tz, fold=0)
    second = dt.replace(tzinfo=tz, fold=1)
    utc = datetime.timezone.utc
    first_back = first.astimezone(utc).astimezone(tz)
    second_back = second.astimezone(utc).astimezone(tz)
    first_valid = first_back.replace(tzinfo=None) == dt and first_back.fold == 0
    second_valid = second_back.replace(tzinfo=None) == dt and second_back.fold == 1

    if first_valid and second_valid:
        return second if first.utcoffset() != second.utcoffset() else first
    if first_valid:
        return first
    if second_valid:
        return second

    gap = second.utcoffset() - first.utcoffset()
    if gap <= ZERO:
        raise ValueError('nonexistent local time: {!r}'.format(dt))
    return localize(dt + gap, tz)


def utc_naive(dt, tz=None):
    """Normalize a datetime to the legacy naive-UTC engine representation."""
    if tz is not None:
        dt = localize(dt, tz)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)


# A UTC class, same as the one in the Python Docs
class _UTC(datetime.tzinfo):
    """UTC"""

    def utcoffset(self, dt):
        return ZERO

    def tzname(self, dt):
        return "UTC"

    def dst(self, dt):
        return ZERO

    def localize(self, dt):
        return dt.replace(tzinfo=self)


class _LocalTimezone(datetime.tzinfo):

    def utcoffset(self, dt):
        if self._isdst(dt):
            return DSTOFFSET
        else:
            return STDOFFSET

    def dst(self, dt):
        if self._isdst(dt):
            return DSTDIFF
        else:
            return ZERO

    def tzname(self, dt):
        return _time.tzname[self._isdst(dt)]

    def _isdst(self, dt):
        tt = (dt.year, dt.month, dt.day,
              dt.hour, dt.minute, dt.second,
              dt.weekday(), 0, 0)
        try:
            stamp = _time.mktime(tt)
        except (ValueError, OverflowError):
            return False  # Too far in the future, not relevant

        tt = _time.localtime(stamp)
        return tt.tm_isdst > 0

    def localize(self, dt):
        return dt.replace(tzinfo=self)


UTC = _UTC()
TZLocal = _LocalTimezone()


HOURS_PER_DAY = 24.0
MINUTES_PER_HOUR = 60.0
SECONDS_PER_MINUTE = 60.0
MUSECONDS_PER_SECOND = 1e6
MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY
SECONDS_PER_DAY = SECONDS_PER_MINUTE * MINUTES_PER_DAY
MUSECONDS_PER_DAY = MUSECONDS_PER_SECOND * SECONDS_PER_DAY


def num2date(x, tz=None, naive=True):
    # Same as matplotlib except if tz is None a naive datetime object
    # will be returned.
    """
    *x* is a float value which gives the number of days
    (fraction part represents hours, minutes, seconds) since
    0001-01-01 00:00:00 UTC *plus* *one*.
    The addition of one here is a historical artifact.  Also, note
    that the Gregorian calendar is assumed; this is not universal
    practice.  For details, see the module docstring.
    Return value is a :class:`datetime` instance in timezone *tz* (default to
    rcparams TZ value).
    If *x* is a sequence, a sequence of :class:`datetime` objects will
    be returned.
    """

    ix = int(x)
    dt = datetime.datetime.fromordinal(ix)
    remainder = float(x) - ix
    hour, remainder = divmod(HOURS_PER_DAY * remainder, 1)
    minute, remainder = divmod(MINUTES_PER_HOUR * remainder, 1)
    second, remainder = divmod(SECONDS_PER_MINUTE * remainder, 1)
    microsecond = int(MUSECONDS_PER_SECOND * remainder)
    if microsecond < 10:
        microsecond = 0  # compensate for rounding errors

    if tz is not None:
        tz = tzparse(tz)
        dt = datetime.datetime(
            dt.year, dt.month, dt.day, int(hour), int(minute), int(second),
            microsecond, tzinfo=UTC)
        dt = dt.astimezone(tz)
        if naive:
            dt = dt.replace(tzinfo=None)
    else:
        # If not tz has been passed return a non-timezoned dt
        dt = datetime.datetime(
            dt.year, dt.month, dt.day, int(hour), int(minute), int(second),
            microsecond)

    if microsecond > 999990:  # compensate for rounding errors
        dt += datetime.timedelta(microseconds=1e6 - microsecond)

    return dt


def num2dt(num, tz=None, naive=True):
    return num2date(num, tz=tz, naive=naive).date()


def num2time(num, tz=None, naive=True):
    return num2date(num, tz=tz, naive=naive).time()


def date2num(dt, tz=None):
    """
    Convert :mod:`datetime` to the Gregorian date as UTC float days,
    preserving hours, minutes, seconds and microseconds.  Return value
    is a :func:`float`.
    """
    dt = utc_naive(dt, tz=tz)

    base = float(dt.toordinal())
    if hasattr(dt, 'hour'):
        # base += (dt.hour / HOURS_PER_DAY +
        #          dt.minute / MINUTES_PER_DAY +
        #          dt.second / SECONDS_PER_DAY +
        #          dt.microsecond / MUSECONDS_PER_DAY
        #         )
        base = math.fsum(
            (base, dt.hour / HOURS_PER_DAY, dt.minute / MINUTES_PER_DAY,
             dt.second / SECONDS_PER_DAY, dt.microsecond / MUSECONDS_PER_DAY))

    return base


def time2num(tm):
    """
    Converts the hour/minute/second/microsecond part of tm (datetime.datetime
    or time) to a num
    """
    num = (tm.hour / HOURS_PER_DAY +
           tm.minute / MINUTES_PER_DAY +
           tm.second / SECONDS_PER_DAY +
           tm.microsecond / MUSECONDS_PER_DAY)

    return num
