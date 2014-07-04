#!/usr/bin/python3
# coding=utf-8

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
		self.assertTrue(timer.isAlive())
		status.shouldStop = True
		self.waitDuring(0.2, 'Let timer stop.')
		self.assertFalse(timer.isAlive())

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
		self.waitDuring(2.7, 'Wait for timer\'s timeout.', [lambda: self.assertTrue(timer.isAlive())], 0, 0.2)
		self.assertFalse(timer.isAlive())


if __name__ == '__main__':
	unittest.main()
