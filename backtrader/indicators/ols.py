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

import backtrader as bt
from . import PeriodN


__all__ = ['OLS_Slope_InterceptN', 'OLS_TransformationN', 'OLS_BetaN',
           'CointN']


def _pandas():
    try:
        import pandas
    except ImportError as exc:
        raise ImportError('OLS indicators require the optional pandas package') from exc
    return pandas


def _statsmodels():
    try:
        import statsmodels.api
    except ImportError as exc:
        raise ImportError(
            'OLS indicators require the optional statsmodels package'
        ) from exc
    return statsmodels.api


def _coint():
    try:
        from statsmodels.tsa.stattools import coint
    except ImportError as exc:
        raise ImportError(
            'CointN requires the optional statsmodels package'
        ) from exc
    return coint


class OLS_Slope_InterceptN(PeriodN):
    '''
    Calculates a linear regression using ``statsmodel.OLS`` (Ordinary least
    squares) of data1 on data0

    Uses ``pandas`` and ``statsmodels``
    '''
    _mindatas = 2  # ensure at least 2 data feeds are passed

    lines = ('slope', 'intercept',)
    params = (
        ('period', 10),
    )

    def next(self):
        pandas = _pandas()
        statsmodels = _statsmodels()
        p0 = pandas.Series(self.data0.get(size=self.p.period))
        p1 = pandas.Series(self.data1.get(size=self.p.period))
        p1 = statsmodels.add_constant(p1)
        intercept, slope = statsmodels.OLS(p0, p1).fit().params

        self.lines.slope[0] = slope
        self.lines.intercept[0] = intercept


class OLS_TransformationN(PeriodN):
    '''
    Calculates the ``zscore`` for data0 and data1. Although it doesn't directly
    uses any external package it relies on ``OLS_SlopeInterceptN`` which uses
    ``pandas`` and ``statsmodels``
    '''
    _mindatas = 2  # ensure at least 2 data feeds are passed
    lines = ('spread', 'spread_mean', 'spread_std', 'zscore',)
    params = (('period', 10),)

    def __init__(self):
        slint = OLS_Slope_InterceptN(*self.datas)

        spread = self.data0 - (slint.slope * self.data1 + slint.intercept)
        self.l.spread = spread

        self.l.spread_mean = bt.ind.SMA(spread, period=self.p.period)
        self.l.spread_std = bt.ind.StdDev(spread, period=self.p.period)
        self.l.zscore = (spread - self.l.spread_mean) / self.l.spread_std


class OLS_BetaN(PeriodN):
    '''
    Calculates a regression of data1 on data0 using ``pandas.ols``

    Uses ``pandas``
    '''
    _mindatas = 2  # ensure at least 2 data feeds are passed

    lines = ('beta',)
    params = (('period', 10),)

    def next(self):
        pandas = _pandas()
        y, x = (pandas.Series(d.get(size=self.p.period)) for d in self.datas)
        r_beta = pandas.ols(y=y, x=x, window_type='full_sample')
        self.lines.beta[0] = r_beta.beta['x']


class CointN(PeriodN):
    '''
    Calculates the score (coint_t) and pvalue for a given ``period`` for the
    data feeds

    Uses ``pandas`` and ``statsmodels`` (for ``coint``)
    '''
    _mindatas = 2  # ensure at least 2 data feeds are passed

    lines = ('score', 'pvalue',)
    params = (
        ('period', 10),
        ('trend', 'c'),  # see statsmodel.tsa.statttools
    )

    def next(self):
        pandas = _pandas()
        coint = _coint()
        x, y = (pandas.Series(d.get(size=self.p.period)) for d in self.datas)
        score, pvalue, _ = coint(x, y, trend=self.p.trend)
        self.lines.score[0] = score
        self.lines.pvalue[0] = pvalue
