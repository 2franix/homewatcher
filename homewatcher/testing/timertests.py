#!/usr/bin/python3

# Copyright (C) 2014-2017 Cyrille Defranoux
#
# This file is part of Homewatcher.
#
# Homewatcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Homewatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Homewatcher. If not, see <http://www.gnu.org/licenses/>.
#
# For any question, feature requests or bug reports, feel free to contact me at:
# knx at aminate dot net

import sys
from pyknx import logger
from pyknx.testing import base
from homewatcher.timer import Timer
import unittest
import time

class TimerTestCase(base.TestCaseBase):
    def testTimer(self):
        class TimerStatus:
            def __init__(self):
                self.isTimeoutReached = False
                self.isTerminated = False

            def onTimeout(self, timer):
                self.isTimeoutReached = True

            def onTerminated(self, timer):
                logger.reportInfo('onTerminated')
                self.isTerminated = True

        status = TimerStatus()
        timer = Timer(None, 2, 'Test timer', onTimeoutReached=status.onTimeout, onTerminated=status.onTerminated)
        timer.start()
        self.waitDuring(2.1, 'Waiting for test timer to complete', assertions=[lambda: self.assertFalse(status.isTimeoutReached or status.isTerminated)], assertEndMargin=0.2)
        logger.reportInfo('isTimeoutReached={isTimeoutReached}, isTerminated={isTerminated}'.format(isTimeoutReached=status.isTimeoutReached, isTerminated=status.isTerminated))
        self.assertTrue(status.isTimeoutReached and status.isTerminated)

    def testOnIterate(self):
        class TimerStatus:
            def __init__(self):
                self.iterationCount = 0

            def onIterate(self, timer):
                self.iterationCount += 1

        status = TimerStatus()
        timer = Timer(None, 2, 'OnIterate test timer', onTimeoutReached=None, onIterate=status.onIterate)
        timer.start()
        startTime = time.time()
        self.waitDuring(0.2, 'Let timer iterate for a while.')
        self.assertNotEqual(status.iterationCount, 0)
        iterationCount = status.iterationCount
        self.waitUntil(startTime + 1, 'Let timer iterate for a while.')
        self.assertNotEqual(status.iterationCount, iterationCount)
        iterationCount = status.iterationCount
        self.waitUntil(startTime + timer.timeout + 0.1, 'Wait for timer timeout.')
        self.assertNotEqual(status.iterationCount, iterationCount)
        iterationCount = status.iterationCount
        self.waitDuring(1, 'Wait a few seconds to make sure timer has now stopped and onIterate is no more called.')
        self.assertEqual(status.iterationCount, iterationCount)

    def testStopFromOnIterate(self):
        class TimerStatus:
            def __init__(self):
                self.shouldStop = False

            def onIterate(self, timer):
                if self.shouldStop:
                    timer.stop()

        status = TimerStatus()
        timer = Timer(None, 2, 'StopOnIterate test timer', onTimeoutReached=None, onIterate=status.onIterate)
        timer.start()
        startTime = time.time()
        self.waitDuring(0.2, 'Let timer iterate for a while.')
        self.assertTrue(timer.is_alive())
        status.shouldStop = True
        self.waitDuring(0.2, 'Let timer stop.')
        self.assertFalse(timer.is_alive())

    def testResetFromOnIterate(self):
        class TimerStatus:
            def __init__(self):
                self.hasBeenReset = False

            def onIterate(self, timer):
                if time.time() - startTime > 1 and not self.hasBeenReset:
                    timer.reset()
                    self.hasBeenReset = True

        startTime = time.time()
        status = TimerStatus()
        timer = Timer(None, 1.5, 'ResetOnIterate test timer', onTimeoutReached=None, onIterate=status.onIterate)
        timer.start()
        startTime = time.time()
        self.waitDuring(2.7, 'Wait for timer\'s timeout.', [lambda: self.assertTrue(timer.is_alive())], 0, 0.2)
        self.assertFalse(timer.is_alive())


if __name__ == '__main__':
    unittest.main()
