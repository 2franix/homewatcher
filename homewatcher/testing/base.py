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

import sys
import os
import subprocess
import unittest
import time
import traceback
import inspect
import stat
import pwd, grp
import shutil

from pyknx import logger, linknx
from pyknx.testing import base
from pyknx.communicator import Communicator
from homewatcher import configuration, configurator
import logging
import test
from homewatcher.sensor import *
from homewatcher.alarm import *

class TestCaseBase(base.WithLinknxTestCase):
	def sendEmailMock(self, toAddr, subject, text, attachments=[]):
		logger.reportDebug('sendEmailMock: {0} {1}'.format(toAddr, subject))
		self.assertIsNone(self.emailInfo, 'An unconsumed email is about to be deleted. It is likely to be an unexpected email. Details are {0}'.format(self.emailInfo))
		self.emailInfo = {'to' : toAddr, 'subject' : subject, 'text' : text, 'attachments' : attachments, 'date' : time.ctime()}
		logger.reportInfo('sendEmail mock received {0}'.format(self.emailInfo))

	def assertEmail(self, purpose, to, subject, attachments, consumesEmail=True):
		self.assertIsNotNone(self.emailInfo, 'No email has been sent for {0}.'.format(purpose))
		if not isinstance(to, list): to=[to]
		self.assertEqual(self.emailInfo['to'], to, 'Wrong recipient list.')
		self.assertEqual(self.emailInfo['subject'][:len(subject)], subject, 'Subject is incorrect.')
		self.assertEqual(self.emailInfo['attachments'], attachments)
		if consumesEmail: self.emailInfo = None

	def setUp(self, usesLinknx=True, usesCommunicator=True):
		linknxConfFile = 'linknx_test_conf.xml' if usesLinknx else None
		communicatorAddress = ('localhost', 1031) if usesCommunicator else None
		userScript = os.path.join(os.path.dirname(configuration.__file__), 'linknxuserfile.py')
		hwConfigFile = os.path.join(os.path.dirname(__file__), 'homewatcher_test_conf.xml')
		userScriptArgs = {'hwconfig':hwConfigFile}
		try:
			if usesCommunicator:
				linknxPatchedFile = tempfile.mkstemp(suffix='.xml', text=True)[1]
				hwConfigurator = configurator.Configurator(hwConfigFile, linknxConfFile, linknxPatchedFile)
				hwConfigurator.generateConfig()
				hwConfigurator.writeConfig()
			else:
				linknxPatchedFile = None
			base.WithLinknxTestCase.setUp(self, linknxConfFile=linknxPatchedFile, communicatorAddr=communicatorAddress, patchLinknxConfig=False, userScript=userScript, userScriptArgs=userScriptArgs)
		finally:
			if linknxPatchedFile is not None: os.remove(linknxPatchedFile)
		self.homewatcherScriptsDirectory = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
		self.homewatcherModulesDirectory = os.path.normpath(os.path.join(os.path.dirname(__file__), '..'))
		try:
			# Redirect the emailing capability of the daemon.
			if self.alarmDaemon:
				self.alarmDaemon.sendEmail = self.sendEmailMock
			self.emailInfo = None
		except:
			logger.reportException('Error in setUp.')
			self.tearDown()
			self.fail('Test setup failed.')
			raise

	@property
	def alarmDaemon(self):
		userModule = self.communicator._userModule if self.communicator else None
		if userModule is None: return None

		return userModule.alarmDaemon

	@property
	def alarmModeObject(self):
		return self.alarmDaemon.modeValueObject

	# @property
	# def alarmDaemon(self):
		# userModule = self.communicator._userModule
		# if userModule is None: return None
# 
		# return userModule.alarmDaemon

	def tearDown(self):
		logger.reportInfo('Tearing down...')

		base.WithLinknxTestCase.tearDown(self)

	def changeAlarmMode(self, newMode, emailAddressesForNotification):
		self.alarmDaemon.currentMode = newMode

		# Check that mode is now changed.
		self.waitDuring(1.5, 'Waiting for linknx to handle mode change')
		self.assertEqual(self.alarmDaemon.currentMode, self.alarmDaemon.getMode(newMode), 'Alarm mode in daemon should now be synchronized.')

		# Check email notification.
		expectedSubjectStart = 'Entered mode {0}'.format(newMode)
		self.waitDuring(1, 'Waiting for email notification')
		self.assertEmail('mode change', emailAddressesForNotification, expectedSubjectStart, [])

	def assertAlert(self, sensorsInPrealert, sensorsInAlert, sensorsInPersistentAlert):
		# Sort sensors by alert types.
		sortedPrealertSensors = self._sortSensors(sensorsInPrealert)
		sortedAlertSensors = self._sortSensors(sensorsInAlert)
		sortedPostalertSensors = self._sortSensors(sensorsInPersistentAlert)

		# Check each alert type.
		for alert in self.alarmDaemon.alerts:
			self._assertStateOfSingleAlertType(alert, sortedPrealertSensors[alert], sortedAlertSensors[alert], sortedPostalertSensors[alert])

	def _sortSensors(self, inputSensors):
		sortedSensors = {}
		for alert in self.alarmDaemon.alerts:
			sortedSensors[alert] = []

		for s in inputSensors:
			sortedSensors[s.alert].append(s)

		return sortedSensors

	def _assertStateOfSingleAlertType(self, alert, sensorsInPrealert, sensorsInAlert, sensorsInPersistentAlert):
		# Define constants.
		persistentAlertObject = alert.persistenceObject

		# Check integrity of parameters.
		self.assertTrue(not sensorsInPrealert or not sensorsInAlert, 'There should not be some sensors in prealert if some are in alert.')
		self.assertEqual(len(set(sensorsInAlert).intersection(set(sensorsInPersistentAlert))), len(sensorsInAlert), 'Some sensors in alert are not in persistent alert.')

		# Check persistent alert.
		expectedPersistentValue = len(sensorsInPersistentAlert) > 0
		self.assertEqual(persistentAlertObject.value, expectedPersistentValue, 'Persistence for "{1}" should be {2}={0}'.format(expectedPersistentValue, alert, persistentAlertObject))
		if sensorsInPrealert:
			expectedStatus = Alert.Status.INITIALIZING
		elif sensorsInAlert:
			expectedStatus = Alert.Status.ACTIVE
		elif sensorsInPersistentAlert:
			expectedStatus = Alert.Status.PAUSED
		else:
			expectedStatus = Alert.Status.STOPPED
		self.assertEqual(alert.status, expectedStatus)
		for s in self.alarmDaemon.sensors:
			if s.alert != alert: continue
			self.assertEqual(s.isAlertActive, s in sensorsInAlert, '{0} alert should be {1}'.format(s, s in sensorsInAlert))
			if s.persistenceObject != None:
				self.assertEqual(s.persistenceObject.value, s in sensorsInPersistentAlert, '{0} persistent alert should be {1}'.format(s, s in sensorsInPersistentAlert))
			self.assertEqual(s.isInPrealert, s in sensorsInPrealert, '{0}\'s prealert should be {1}'.format(s, s in sensorsInPrealert))

		# # Determine whether notifications should have been sent.
		# newSensorsInAlert = [s for s in sensorsInAlert if not s in self.sensorsInPersistentAlertOnLastCheck[alertType]]
		# sendsSMS = alertType != Daemon.TEMPERATURE and sensorsInAlert and not self.sensorsInPersistentAlertOnLastCheck[alertType]
		# alertSubject = 'Alerte {0}'.format(alertType)
		# if newSensorsInAlert:
			# purpose = 'alert "{1}" due to {0}'.format(newSensorsInAlert, alertType)
			# self.assertEmail(purpose, ['knx.protection.alerte@youplaboum.fr'], alertSubject, [])
		# else:
			# if not self.emailInfo is None:
				# # An email is possible if it is not for our alert type.
				# self.assertIsNot(self.emailInfo['subject'], alertSubject, 'No alert email is expected for "{0}".'.format(alertType))
# 
		# smsMessage = 'Alerte {0} !'.format(alertType)
		# if sendsSMS:
			# self.assertSMS('0652259392', smsMessage)
			# self.assertSMS('0660074615', smsMessage)
		# else:
			# if self.smsInfos:
				# # Only sms that are not for our alert type are expected.
				# for sms in self.smsInfos:
					# self.assertIsNot(sms['message'], smsMessage, 'No alert SMS is expected for "{0}".'.format(alertType))

		# # Track current sensors.
		# self.sensorsInPersistentAlertOnLastCheck[alertType] = []
		# self.sensorsInPersistentAlertOnLastCheck[alertType].extend(sensorsInPersistentAlert)
