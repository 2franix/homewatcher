#!/usr/bin/python3

# Copyright (C) 2014 Cyrille Defranoux
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

from pyknx import logger
import subprocess
import os
import threading
import time

class Timer(threading.Thread):
	def __init__(self, sensor, timeout, name, onTimeoutReached, onIterate = None, onTerminated = None):
		threading.Thread.__init__(self, name=name + ' (id={0})'.format(id(self)))
		self.sensor = sensor
		self.timeout = timeout
		self.reset()
		self.isTerminating = False
		self.isTerminated = False # Mainly for unit testing.
		self.onIterate = onIterate
		self.onTimeoutReached = onTimeoutReached
		self.onTerminated = onTerminated

	def run(self):
		try:
			logger.reportDebug('Starting {0}'.format(self))
			while not self.isTerminating:
				if self.onIterate is not None: self.onIterate(self)

				# Check for termination.
				if self.isTerminating:
					return

				# Main loop.
				if not self.isPaused:
					if self.endTime is None: self.extend(starts=True)
					if time.time() > self.endTime:
						# Execute delayed job.
						logger.reportDebug('Timeout reached for {0}.'.format(self))
						if callable(self.onTimeoutReached): self.onTimeoutReached(self)
						break

				time.sleep(0.2)
		finally:
			if self.isTerminating:
				# Timer has been stopped from outside.
				logger.reportDebug('{0} is canceled.'.format(self))
			else:
				# Maybe useless but set it for consistency.
				self.isTerminating = True
			if callable(self.onTerminated): self.onTerminated(self)
			logger.reportDebug('{0} is now terminated.'.format(self))
			self.isTerminated = True

	def forceTimeout(self):
		logger.reportDebug('Forcing timeout of {0}'.format(self))
		self.endTime = 0

	def pause(self):
		self.isPaused = True

	def stop(self):
		if not self.isTerminating:
			self.isTerminating = True
			logger.reportDebug('Stopping {0}.'.format(self))

	def reset(self):
		self.endTime = None
		self.isPaused = False

	def __str__(self):
		return '{0} => {1} id={2}'.format(self.sensor, self.name, id(self))

	def extend(self, starts = False):
		""" Prolong duration by the timeout amount of time. """
		if self.isTerminating:
			raise Exception('Timer {0} is terminating, it cannot be extended.'.format(self))
		self.endTime = time.time() + self.timeout
		if starts:
			logger.reportDebug('{0} started for {1} seconds.'.format(self, self.timeout))
		else:
			logger.reportDebug('{0} is extended by {1} seconds.'.format(self, self.timeout))

	# class AlertTimer(Timer):
		# def __init__(self, sensor):
			# Sensor.Timer.__init__(self, sensor, sensor.getPrealertTimeout(), 'Alert timer for {0}'.format(sensor.name))
			# self.state = 'prealert'
# 
		# def onTimeoutReached(self):
			# # To be on the safe side, check that this sensor is still the
			# # current one in its related sensor.
			# if self.sensor._alertTimer != self:
				# logger.reportError('{0} is not the current alert timer of {1} (which is currently {2}). onTimeoutReached is aborted and timer stopped.'.format(self, self.sensor, self.sensor._alertTimer))
				# self.stop()
				# return
# 
			# logger.reportDebug('AlertTimer.onTimeoutReached state={0}'.format(self.state))
			# if self.sensor.isInhibited: self.stop()
# 
			# if self.state == 'prealert':
				# logger.reportDebug('AlertTimer.onTimeoutReached isAlertActive={0}'.format(self.sensor.isAlertActive))
				# self.sensor.isAlertActive = True
				# self.state = 'postalert'
				# nextTimeout = self.sensor.getPostalertTimeout()
			# elif self.state == 'postalert':
				# logger.reportDebug('AlertTimer.onTimeoutReached isAlertActive={0}'.format(self.sensor.isAlertActive))
				# self.sensor.isAlertActive = False
				# nextTimeout = None
			# else:
				# raise Exception('Invalid alert timer state.')
# 
			# return nextTimeout
# 
		# def onTerminated(self):
			# self.sensor.isAlertActive = False
# 
		# # def onIterate(self):
			# # if self.state == 'prealert' and self.sensor.hasSimilarAlertAlreadyBeenTriggered:
				# # # Another sensor fired alert, do not wait until our prealert
				# # # delay is over, participate now!
				# # self.forceTimeout()
# 
	# class DelayedActivationTimer(Timer):
		# def __init__(self, sensor):
			# Sensor.Timer.__init__(self, sensor, sensor.getDelayedActivationTimeout(), 'Activation timer for {0}'.format(sensor.name))
			# self.isReady = None
# 
		# def reset(self):
			# Sensor.Timer.reset(self)
			# self.isReady = None
# 
		# def onTimeoutReached(self):
			# # To be on the safe side, check that this sensor is still the
			# # current one in its related sensor.
			# if self.sensor._activationTimer != self:
				# logger.reportError('{0} is not the current activation timer of {1} (which is currently {2}). onTimeoutReached is aborted and timer stopped.'.format(self, self.sensor, self.sensor._activationTimer))
				# self.stop()
				# return
# 
			# self.sensor.isEnabled = True
# 
		# # def onIterate(self):
			# # if not self.sensor.isRequiredByCurrentMode():
				# # self.stop()
			# # if self.isReady is None or not self.isReady:
				# # isFirstPass = self.isReady is None
				# # self.isReady = self.sensor.canBeEnabled()
				# # self.isPaused = not self.isReady
				# # if isFirstPass and not self.isReady:
					# # logger.reportInfo('{0}\'s activation is postponed until {1} returns True.'.format(self.sensor.name, self.sensor.canBeEnabled))
				# # elif self.isReady:
					# # logger.reportInfo('{0} will be activated in {1} seconds.'.format(self.sensor.name, self.timeout))
			# # else:
				# # if not self.sensor.canBeEnabled():
					# # self.reset()
# 
