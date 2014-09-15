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
sys.path.append('../')
from pyknx import logger, linknx, configurator
from pyknx.communicator import Communicator
from homewatcher import configuration
from homewatcher.testing import base
import logging
from homewatcher.sensor import *
from homewatcher.alarm import *
import os.path
import subprocess
import unittest
import time
import traceback
import inspect
import stat
import pwd, grp
import shutil

class AcceptanceTestCase(base.TestCaseBase):
    def setUp(self):
        # Initialize alert state.
        self.sensorsInPersistentAlertOnLastCheck = []

        base.TestCaseBase.setUp(self, usesCommunicator=True)

    # @property
    # def alarmModeObject(self):
        # return self.linknx.getObject('Protection_Alarme_ModeDemande')

    # def testClassesActivationInModes(self):
        # """ Exercises the inclusion of classes in Mode objects.
# 
            # When doing so, all sensors that inherit those classes should be active. """
        # daemon = self.alarmDaemon
# 
        # # Prepare useful sensors.
        # bedroomSmoke = daemon.getSensorByName('BedroomSmokeSensor')
        # kitchenSmoke = daemon.getSensorByName('KitchenSmokeSensor')
# 
        # # Initialize state to a known one.
        # self.emailInfo = None
        # self.alarmModeObject.value = 3 # Night.
        # self.waitDuring(0.5, 'Initialization.')
# 
        # # Check smoke sensors are inactive.
        # self.assertFalse(bedroomSmoke.isEnabled)
        # self.assertFalse(kitchenSmoke.isEnabled)
# 
        # # Go to Presence mode.
        # self.emailInfo = None
        # self.alarmModeObject.value = 1 # Presence.
        # self.waitDuring(0.5, 'Switching to Presence.')
# 
        # # Check smoke sensors are now active.
        # self.assertTrue(bedroomSmoke.isEnabled)
        # self.assertTrue(kitchenSmoke.isEnabled)
# 
        # # Go to Night mode again.
        # self.emailInfo = None
        # self.alarmModeObject.value = 3 # Night.
        # self.waitDuring(0.5, 'Switching back to Night.')
# 
        # # Check smoke sensors are inactive again.
        # self.assertFalse(bedroomSmoke.isEnabled)
        # self.assertFalse(kitchenSmoke.isEnabled)
# 
    def changeAlarmMode(self, newMode, emailAddressesForNotification):
        previousMode = self.linknx.getObject('Mode').value

        base.TestCaseBase.changeAlarmMode(self, newMode, emailAddressesForNotification)

        # Check object "Applied Mode" contains the new mode. This copy is
        # operated by an action related to mode change event.
        self.assertEqual(self.linknx.getObject('Mode').value, self.linknx.getObject('AppliedMode').value)
        self.assertEqual(previousMode, self.linknx.getObject('PreviousMode').value)

    def testPostponedActivation(self):
        """ Test that exercises the postponing of the activation of a sensor whenever its canEnabled property returns False. """

        logger.reportInfo('\n\n*********INITIALIZE testPostponedActivation********************')

        daemon = self.alarmDaemon

        # Prepare useful sensors.
        garageDoor = daemon.getSensorByName('GarageDoorOpening')
        entranceDoor = daemon.getSensorByName('EntranceDoorOpening')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1 # Presence.
        entranceDoor.watchedObject.value = True # Open entrance.

        self.waitDuring(1, 'Initialization.')

        # Go to away mode.
        self.emailInfo = None # In case mode initialization has raised an email.
        self.changeAlarmMode('Away', 'notify@bar.com')

        # Neither door nor garage should be active for now.
        def assertNoAlert():
            self.assertAlert(sensorsInPrealert=[], sensorsInAlert=[], sensorsInPersistentAlert=[])
        def assertNotEnabled():
            self.assertFalse(entranceDoor.isEnabled, '{0} should not be enabled for now since it is open.'.format(entranceDoor))
            self.assertFalse(garageDoor.isEnabled, '{0} should not be enabled for now since it depends on the entrance door which is open.'.format(garageDoor))
        self.waitDuring(4, 'Wait for a while to make sure neither door nor garage are enabled.', assertions=[assertNoAlert, assertNotEnabled])

        # Close door.
        entranceDoor.watchedObject.value = False

        # No immediate activation is expected!
        self.waitDuring(4, 'Wait for a while to make sure doors do not get enabled for now.', assertions=[assertNoAlert, assertNotEnabled])
        assertEnabled = lambda sensor, isEnabled, format: self.assertEqual(sensor.isEnabled, isEnabled, format.format(sensor))
        assertPaused = lambda sensor, isPaused, format: self.assertEqual(sensor._activationTimer.isPaused, isPaused, format.format(sensor))
        disabledFormat = '{0} should not be enabled for now since its activation delay is not over.'
        enabledFormat = '{0} should be enabled since its activation delay is now over.'
        pausedFormat = 'Activation timer for {0} should be paused.'
        runningFormat = 'Activation timer for {0} should be running.'
        assertEnabled(entranceDoor, False, disabledFormat)
        assertEnabled(garageDoor, False, disabledFormat)
        assertPaused(entranceDoor, False, runningFormat)
        assertPaused(garageDoor, False, runningFormat)

        # Reopening door should cancel activation.
        entranceDoor.watchedObject.value = True
        self.waitDuring(2, 'Let activation timer go to pause.')
        for i in range(2):
            assertEnabled(entranceDoor, False, disabledFormat)
            assertEnabled(garageDoor, False, disabledFormat)
            assertPaused(entranceDoor, True, pausedFormat)
            assertPaused(garageDoor, True, pausedFormat)
            self.waitDuring(2, 'Check that state is stable.')

        # Close again and wait for activation.
        doorClosingTime = time.time()
        entranceDoor.watchedObject.value = False
        self.waitDuring(1, 'Let linknx handle door close event.')
        assertEnabled(entranceDoor, False, disabledFormat)
        assertEnabled(garageDoor, False, disabledFormat)
        assertPaused(entranceDoor, False, runningFormat)
        assertPaused(garageDoor, False, runningFormat)

        # Entrance door gets enabled first.
        assertions=[lambda: assertEnabled(entranceDoor, False, disabledFormat), lambda:    assertEnabled(garageDoor, False, disabledFormat), lambda: assertPaused(entranceDoor, False, runningFormat), lambda: assertPaused(garageDoor, False, runningFormat)]
        self.waitUntil(doorClosingTime + 5 + 0.5, 'Wait for doors to be enabled.', assertions=assertions, assertStartMargin=0, assertEndMargin=1)
        assertEnabled(entranceDoor, True, enabledFormat)
        assertEnabled(garageDoor, True, enabledFormat)
        self.assertFalse(entranceDoor.isActivationPending(), 'Activation timer should now be released.')
        self.assertFalse(garageDoor.isActivationPending(), 'Activation timer should now be released.')

    def testAlertLifeCycle(self):
        logger.reportInfo('\n\n*********INITIALIZE testAlertLifeCycle ********************')

        # Prepare useful sensors.
        kitchenWindow = self.alarmDaemon.getSensorByName('KitchenWindowOpening')
        livingWindow = self.alarmDaemon.getSensorByName('LivingRoomWindowOpening')

        intrusionAlert = self.alarmDaemon.getAlertByName('Intrusion')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1 # Presence.
        kitchenWindow.watchedObject.value = False
        livingWindow.watchedObject.value = False

        self.waitDuring(1, 'Initialization.')

        # Go to away mode.
        self.emailInfo = None # In case mode initialization has raised an email.
        self.changeAlarmMode('Away', 'notify@bar.com')

        # Wait for window activation.
        self.waitDuring(2, 'Wait for activation of window sensors.')
        self.assertTrue(kitchenWindow.isEnabled)
        self.assertTrue(livingWindow.isEnabled)

        def assertAlertEvents(firedEvents, resetsToOff=True):
            eventObjects = {}
            eventObjects[configuration.AlertEvent.Type.ALERT_STARTED] = 'IntrusionAlertStarted'
            eventObjects[configuration.AlertEvent.Type.ALERT_ACTIVATED] = 'IntrusionAlertActivated'
            eventObjects[configuration.AlertEvent.Type.ALERT_PAUSED] = 'IntrusionAlertPaused'
            eventObjects[configuration.AlertEvent.Type.ALERT_RESUMED] = 'IntrusionAlertResumed'
            eventObjects[configuration.AlertEvent.Type.ALERT_STOPPED] = 'IntrusionAlertStopped'
            eventObjects[configuration.AlertEvent.Type.SENSOR_JOINED] = 'IntrusionSensorJoined'
            eventObjects[configuration.AlertEvent.Type.SENSOR_LEFT] = 'IntrusionSensorLeft'

            # Check all events are in the dictionary. If not, that denotes a
            # coding error in the test.
            for eventType in configuration.AlertEvent.Type.getAll():
                self.assertTrue(eventType in eventObjects)

            for eventType, eventObject in eventObjects.items():
                eventState = self.linknx.getObject(eventObject).value
                expectedState = eventType in firedEvents
                self.assertEqual(eventState, expectedState, 'Event {0} should be {1}.\nState of all event objects is following:{2}'.format(eventObject, expectedState, dict([(objId, self.linknx.getObject(objId).value) for objId in eventObjects.values()])))
                if eventState and resetsToOff: self.linknx.getObject(eventObject).value = False

            # Clear email so that test does not complain about emails not
            # been treated.
            self.emailInfo = None

        self.assertAlert([], [], [])
        assertAlertEvents([])

        # Prealert.
        prealertStartTime = time.time()
        kitchenWindow.watchedObject.value = True
        self.waitDuring(0.1, "Let 'alert started' event be raised.")
        assertAlertEvents((configuration.AlertEvent.Type.ALERT_STARTED,))
        self.waitUntil(prealertStartTime + kitchenWindow.getPrealertDuration() + 0.2, 'Waiting for prealert to expire.', [lambda: self.assertAlert([kitchenWindow],[],[]), lambda: assertAlertEvents([], resetsToOff=False)], 0.2, 0.4) 
        kitchenWindow.watchedObject.value = False # Release sensor trigger now to be able to trigger it again in a while.
        assertAlertEvents((configuration.AlertEvent.Type.SENSOR_JOINED, configuration.AlertEvent.Type.ALERT_ACTIVATED))

        # Alert.
        self.waitUntil(prealertStartTime + kitchenWindow.getPrealertDuration() + kitchenWindow.getAlertDuration() + 0.5, 'Waiting for alert to expire', [lambda: self.assertAlert([],[kitchenWindow],[kitchenWindow]), lambda: assertAlertEvents([])], 0.2, 0.7)
        assertAlertEvents((configuration.AlertEvent.Type.ALERT_PAUSED, configuration.AlertEvent.Type.SENSOR_LEFT))

        # Paused.
        self.assertAlert([], [], [kitchenWindow])

        # Resumed.
        alertResumeTime = time.time()
        kitchenWindow.watchedObject.value = True
        self.waitDuring(0.3, 'Waiting for alert to resume', [])
        kitchenWindow.watchedObject.value = False # Release sensor trigger now to be able to trigger it again in a while.
        assertAlertEvents((configuration.AlertEvent.Type.ALERT_RESUMED, configuration.AlertEvent.Type.SENSOR_JOINED, configuration.AlertEvent.Type.ALERT_ACTIVATED))

        # Alert.
        self.waitUntil(alertResumeTime + kitchenWindow.getAlertDuration() + 0.5, 'Waiting for alert to expire', [lambda: self.assertAlert([],[kitchenWindow],[kitchenWindow]), lambda: assertAlertEvents([])], 0.2, 0.7)
        assertAlertEvents((configuration.AlertEvent.Type.ALERT_PAUSED, configuration.AlertEvent.Type.SENSOR_LEFT))

        # Paused.
        self.assertAlert([], [], [kitchenWindow])

        # Stopped.
        self.alarmDaemon.getAlertByName('Intrusion').persistenceObject.value = False
        self.waitDuring(0.4, 'Waiting for alert to stop.')
        assertAlertEvents((configuration.AlertEvent.Type.ALERT_STOPPED,))

        # Raise a new alert. Should begin with a prealert.
        # Prealert.
        prealertStartTime = time.time()
        kitchenWindow.watchedObject.value = True
        self.waitDuring(0.1, "Let 'alert started' event be raised.")
        assertAlertEvents((configuration.AlertEvent.Type.ALERT_STARTED,))
        self.waitUntil(prealertStartTime + kitchenWindow.getPrealertDuration() + 0.2, 'Waiting for prealert to expire.', [lambda: self.assertAlert([kitchenWindow],[],[]), lambda: assertAlertEvents([], resetsToOff=False)], 0.2, 0.4) 
        kitchenWindow.watchedObject.value = False # Release sensor trigger now to be able to trigger it again in a while.
        assertAlertEvents((configuration.AlertEvent.Type.SENSOR_JOINED, configuration.AlertEvent.Type.ALERT_ACTIVATED))

        # Alert. Stop it in the middle of the alert to test manual alert
        # abortion.
        self.alarmDaemon.getAlertByName('Intrusion').persistenceObject.value = False
        self.waitDuring(0.4, 'Waiting for alert to stop.')
        assertAlertEvents((configuration.AlertEvent.Type.SENSOR_LEFT, configuration.AlertEvent.Type.ALERT_PAUSED, configuration.AlertEvent.Type.ALERT_STOPPED))

        self.fail('Test an alert without persistenceObjectId to check that the "paused" status never occurs.')

    def testIntrusionWithInhibition(self):
        self.doTestIntrusion(False, False, False, True)

    def testIntrusionWithToggling(self):
        self.doTestIntrusion(True, False, False, False)

    def testIntrusionWithShuntPrealert(self):
        self.doTestIntrusion(False, True, False, False)

    def testIntrusionWithCancellation(self):
        self.doTestIntrusion(False, False, True, False)

    def doTestIntrusion(self, togglesSensorBeforeEndOfPrealert, shuntsprealertWithFasterSensor, cancelsAlarm, testsInhibition):
        """ Test exercising the alert handling when an intrusion is detected.  """
        logger.reportInfo('\n\n*********INITIALIZE testIntrusion togglesSensorBeforeEndOfPrealert={0} shuntsprealertWithFasterSensor={1} cancelsAlarm={2}********************'.format(togglesSensorBeforeEndOfPrealert, shuntsprealertWithFasterSensor, cancelsAlarm))
        daemon = self.alarmDaemon

        self.assertTrue(togglesSensorBeforeEndOfPrealert ^ shuntsprealertWithFasterSensor ^ cancelsAlarm ^ testsInhibition)

        # Prepare sensors involved in this test.
        entranceSensor = daemon.getSensorByName('EntranceDoorOpening')
        livingRoomWindowSensor = daemon.getSensorByName('LivingRoomWindowOpening')
        kitchenWindowSensor = daemon.getSensorByName('KitchenWindowOpening')
        intrusionAlert = daemon.getAlertByName('Intrusion')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1
        for sensor in (entranceSensor, livingRoomWindowSensor, kitchenWindowSensor):
            sensor.watchedObject.value = False

        self.waitDuring(1.5, 'Initializing')
        modeChangeTime = time.time()
        self.emailInfo = None # In case mode initialization has raised an email.
        self.changeAlarmMode('Away', 'notify@bar.com')

        self.waitUntil(modeChangeTime + entranceSensor.getActivationDelay() + 0.5, 'Waiting for door to be enabled.')
        for sensor in (entranceSensor, livingRoomWindowSensor, kitchenWindowSensor):
            self.assertTrue(sensor.isEnabled, '{0} should now be enabled.'.format(sensor))
        self.assertEqual(entranceSensor.getPrealertDuration(), 6)

        # Step inside home.
        firstTriggerTime = time.time()
        entranceSensor.watchedObject.value = True

        sensorsInPrealert = [entranceSensor]
        sensorsInAlert = []
        sensorsInPersistentAlert = []
        checkAlertStatus = lambda: self.assertAlert(sensorsInPrealert, sensorsInAlert, sensorsInPersistentAlert)
        intermediaryDelay = entranceSensor.getPrealertDuration() / 4
        if togglesSensorBeforeEndOfPrealert:
            # Release sensor as quickly as possible.
            self.waitDuring(intermediaryDelay, [checkAlertStatus])
            entranceSensor.watchedObject.value = False

            # Toggle sensor again.
            self.waitDuring(intermediaryDelay, [checkAlertStatus])
            entranceSensor.watchedObject.value = True

            # Release again and leave it in that state until end of prealert (to
            # make sure alert state is not taken from the current sensor
            # status).
            self.waitDuring(intermediaryDelay, [checkAlertStatus])
            entranceSensor.watchedObject.value = False

        if cancelsAlarm:
            self.waitDuring(intermediaryDelay, [checkAlertStatus])
            self.changeAlarmMode('Presence', 'notify@bar.com') # Takes some time.
            del(sensorsInPrealert[:])
            for sensor in (entranceSensor, livingRoomWindowSensor, kitchenWindowSensor):
                self.assertFalse(sensor.isEnabled, '{0} should not be enabled anymore.'.format(sensor))

            # Make sure alert is not raised after prealert delay of entrance
            # door.
            self.waitUntil(firstTriggerTime + entranceSensor.getPrealertDuration() + 1.5, 'Wait a few seconds to make sure no alert is being raised.', [checkAlertStatus])
        else:
            if shuntsprealertWithFasterSensor:
                # Prealert duration is driven by living room window, as it is a faster sensor
                # than entrance door.
                self.waitDuring(intermediaryDelay, [checkAlertStatus])
                sensorsInPrealert.append(livingRoomWindowSensor)
                livingRoomWindowSensor.watchedObject.value = True
                # Check that living room window will raise alert faster than
                # entrance door (the opposite would denote a configuration
                # error).
                remainingTimeBeforeDoorAlert = entranceSensor.getPrealertDuration() - (time.time() - firstTriggerTime)
                logger.reportDebug('Remaining time before door alert: {0}s, before living room alert: {1} (expected to be shorter in living room!)'.format(remainingTimeBeforeDoorAlert, livingRoomWindowSensor.getPrealertDuration()))
                self.assertLess(livingRoomWindowSensor.getPrealertDuration(), remainingTimeBeforeDoorAlert, 'Living room window will not raise alert before entrance door, this test is not properly set up.')
                self.waitDuring(livingRoomWindowSensor.getPrealertDuration() + 1, 'Let living room window prealert pass.', [checkAlertStatus], 0.2, 1.2)
            else:
                # Normal prealert with entrance door.
                self.waitUntil(firstTriggerTime + entranceSensor.getPrealertDuration() + 1, 'Let prealert delay pass.', [checkAlertStatus], 0.5, 1.2)

            # Whichever strategy should now lead to entrance door being in alert
            # (either because of its own prealert or because an intrusion alert has
            # been raised by kitchen blinds meanwhile).
            sensorsInAlert.extend(sensorsInPrealert)
            sensorsInPersistentAlert.extend(sensorsInAlert)
            del(sensorsInPrealert[:])

            # Wait for first sensor to quit alert. At this point, entranceSensor
            # should already have been in alert for 1 second.
            self.assertTrue(entranceSensor.getAlertDuration() < livingRoomWindowSensor.getAlertDuration(), 'This test assumes that door\'s alert is shorter than kitchen\'s one.')
            self.assertEmail('Sensor joined', ['intrusion@foo.com'], 'Alert Intrusion: sensor joined', [])
            self.waitDuring(entranceSensor.getAlertDuration() - 0.5, 'Wait for first sensor to quit alert.', [checkAlertStatus], 0, 1)
            sensorsInAlert.remove(entranceSensor)
            self.assertFalse(entranceSensor.isAlertActive)

            # Wait for the end of second sensor's alert.
            self.waitUntil(firstTriggerTime + intermediaryDelay + livingRoomWindowSensor.getPrealertDuration() + livingRoomWindowSensor.getAlertDuration() + 1, 'Waiting for second sensor to quit alert.', [checkAlertStatus], 0, 1)
            usesLivingWindow = livingRoomWindowSensor in sensorsInAlert
            if usesLivingWindow: sensorsInAlert.remove(livingRoomWindowSensor)

            # Check that test is properly set up at this point.
            self.assertFalse(sensorsInAlert)
            self.assertFalse(sensorsInPrealert)
            self.assertEqual(set(sensorsInPersistentAlert), set([livingRoomWindowSensor, entranceSensor] if usesLivingWindow else [entranceSensor]))

            # Wait a few seconds more, to check everything stays ok.
            self.waitDuring(5, 'Checking that no event occurs...', [checkAlertStatus])

            if testsInhibition:
                # Relaunch alert => shunt prealert and go to alert immediately.
                sensorsInAlert.append(entranceSensor)
                sensorsInPersistentAlert.append(entranceSensor)
                entranceSensor.watchedObject.value = False
                self.waitDuring(0.2, 'Closing entrance door.')
                entranceSensor.watchedObject.value = True
                self.waitDuring(0.5, 'Waiting for alert to be reraised...')
                self.assertEmail('Sensor joined', ['intrusion@foo.com'], 'Alert Intrusion: sensor joined', [])
                checkAlertStatus()

                # Stop current alert without inhibiting for now.
                intrusionAlert.persistenceObject.value = False
                sensorsInAlert.remove(entranceSensor)
                sensorsInPersistentAlert.clear()
                self.waitDuring(0.5, 'Stopping current alert without inhibiting...')
                checkAlertStatus()

                # Relaunch alert again.
                entranceSensor.watchedObject.value = False
                self.waitDuring(0.2, 'Closing entrance door.')
                entranceSensor.watchedObject.value = True
                self.waitDuring(0.2, 'Reopening entrance door.')
                entranceSensor.watchedObject.value = False
                sensorsInPrealert.append(entranceSensor)
                self.waitDuring(5.9, 'Waiting for alert to be reraised...', [checkAlertStatus], 0.5, 0.2)
                self.assertEmail('Sensor joined', ['intrusion@foo.com'], 'Alert Intrusion: sensor joined', [])
                sensorsInPrealert.remove(entranceSensor)
                sensorsInAlert.append(entranceSensor)
                sensorsInPersistentAlert.append(entranceSensor)
                checkAlertStatus()

                # Now inhibit intrusion alert.
                intrusionAlert.inhibitionObject.value = True
                intrusionAlert.persistenceObject.value = False
                del(sensorsInAlert[:])
                del(sensorsInPersistentAlert[:])
                self.waitDuring(0.6, 'Inhibiting intrusion alert...')
                checkAlertStatus()

                # Trigger another sensor to make sure alert is really inhibited.
                kitchenWindowSensor.watchedObject.value = False
                self.waitDuring(0.2, 'Closing kitchen window.')
                kitchenWindowSensor.watchedObject.value = True
                self.waitDuring(kitchenWindowSensor.getPrealertDuration() + 1.5, 'Checking that opening sesnors do not fire alert anymore (alert is inhibited)...', [checkAlertStatus])

                # Remove inhibition: nothing should occur until a sensor gets
                # triggered again (currently triggered sensors are still ignored).
                intrusionAlert.inhibitionObject.value = False
                self.waitDuring(4.5, 'Checking no event occurs...', [checkAlertStatus], 1.5)

                # Close window and open it again: alert!
                kitchenWindowSensor.watchedObject.value = False
                self.waitDuring(0.2, 'Closing kitchen window.', [checkAlertStatus])
                triggerTime = time.time()
                kitchenWindowSensor.watchedObject.value = True
                sensorsInPrealert.append(kitchenWindowSensor)
                self.waitDuring(kitchenWindowSensor.getPrealertDuration() + 0.2, 'Opening door again...', [checkAlertStatus], 0.2, 0.4)
                sensorsInPrealert.remove(kitchenWindowSensor)
                sensorsInAlert.append(kitchenWindowSensor)
                sensorsInPersistentAlert.append(kitchenWindowSensor)
                self.assertEmail('Sensor joined', ['intrusion@foo.com'], 'Alert Intrusion: sensor joined', [])
                self.waitUntil(triggerTime + kitchenWindowSensor.getPrealertDuration() + kitchenWindowSensor.getAlertDuration(), 'Checking door alert...', [checkAlertStatus], 0.2, 0.2)
                sensorsInAlert.remove(kitchenWindowSensor)
                self.waitUntil(2, 'Alert should now be paused...', [checkAlertStatus], 0.2, 0)

    def testInhibitionBeforeModeChange(self):
        daemon = self.alarmDaemon

        # Prepare sensors involved in this test.
        sensor = daemon.getSensorByName('EntranceDoorOpening')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1
        daemon.getAlertByName('Intrusion').inhibitionObject.value = True

        self.waitDuring(1, 'Initializing')
        modeChangeTime = time.time()
        self.emailInfo = None # In case mode initialization has raised an email.
        self.changeAlarmMode('Away', 'notify@bar.com')

        self.waitDuring(sensor.getActivationDelay() + 0.5, 'Waiting for {0} to be enabled.'.format(sensor))
        self.assertTrue(sensor.isEnabled, '{0} should now be enabled.'.format(sensor))

        # Trigger sensor and wait long enough to make sure no alert is raised.
        sensor.watchedObject.value = True
        self.waitDuring(sensor.getPrealertDuration() + 2, 'Wait to make sure no alert is raised.', [lambda: self.assertAlert([], [], [])], 0, 0)
        self.assertTrue(sensor.isTriggered, '{0} should still be triggered.'.format(sensor))

    def testModeChange(self):
        """
            Test that merely exercises the everyday changing of mode.

            Nothing special here, we just switch from one mode to another to check that sensors are activated/deactivated as expected.
        """
        daemon = self.alarmDaemon

        # Check mode objects are properly set up.
        for modeName in ('Presence', 'Away', 'Night'):
            mode = daemon.getMode(modeName)
            self.assertEqual(len(mode.eventManager.eventConfigs), 2)
            self.assertEqual(mode.eventManager.eventConfigs[0].type, 'entered')
            self.assertEqual(len(mode.eventManager.eventConfigs[0].actions), 2)
            self.assertEqual(mode.eventManager.eventConfigs[0].actions[0].type, configuration.Action.Type.SEND_EMAIL)
            self.assertEqual(mode.eventManager.eventConfigs[1].type, 'left')
            self.assertEqual(len(mode.eventManager.eventConfigs[1].actions), 1)

        # Prepare sensors involved in this test.
        entranceDoor = daemon.getSensorByName('EntranceDoorOpening')
        livingWindow = daemon.getSensorByName('LivingRoomWindowOpening')
        kitchenSmoke = daemon.getSensorByName('KitchenSmokeSensor')
        bedroomSmoke = daemon.getSensorByName('BedroomSmokeSensor')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1
        livingWindow.watchedObject.value = True # Open window.

        self.waitDuring(1, 'Initializing')
        modeChangeTime = time.time()
        logger.reportInfo('\n\n********* SWITCH TO MODE: AWAY ********************')
        self.emailInfo = None # In case mode initialization has raised an email.
        self.changeAlarmMode('Away', 'notify@bar.com')

        # Check smoke detectors are immediately active.
        self.waitDuring(1, 'Waiting for some sensors to be enabled.')
        for sensor in (kitchenSmoke, bedroomSmoke):
            self.assertTrue(sensor.isEnabled, '{0} should now be enabled.'.format(sensor))

        # Check entrance door is not immediately active. 
        self.waitUntil(modeChangeTime + 5.5, 'Consuming activation delay for {0}'.format(entranceDoor), [lambda: self.assertFalse(entranceDoor.isEnabled)], 0, 0.5)
        self.assertTrue(entranceDoor.isEnabled)

        # Check living window is not active since it is triggered.
        self.assertTrue(livingWindow.isTriggered, '{0} has been manually triggered at the beginning of the test, it should still be so.'.format(livingWindow))
        self.assertFalse(livingWindow.isEnabled, '{0} should not be enabled since it is triggered.'.format(livingWindow))

        # Close window and check that it becomes enabled in a short time.
        livingWindow.watchedObject.value = False
        self.waitDuring(1.2, 'Waiting for {0} to be enabled.'.format(livingWindow), [lambda: self.assertFalse(livingWindow.isEnabled)], 0, 0.2)
        self.assertTrue(livingWindow.isEnabled, '{0} should now be enabled.'.format(livingWindow))

        logger.reportInfo('\n\n************ SWITCH TO MODE: PRESENCE **********************')
        self.changeAlarmMode('Presence', 'notify@bar.com')

        # Check all sensors are now inactive.
        def checkAllSensorsEnabledState():
            for s in daemon.getAlertByName('Intrusion').sensors:
                self.assertFalse(s.isEnabled, '{0} should now be disabled.'.format(s))
        self.waitDuring(4, 'Let little time go to test sensors\' state in the long run.', [checkAllSensorsEnabledState])

    def testFloatSensors(self):
        daemon = self.alarmDaemon

        # Prepare sensors involved in this test.
        outdoorTemperature = daemon.getSensorByName('OutdoorTemperature')
        persistentAlert = self.linknx.getObject('TemperaturePersistence')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1 # Presence

        # Wait for initialization to complete.
        self.waitDuring(1, 'Wait for initialization to complete.')
        self.emailInfo = None

        # Fire alert!
        outdoorTemperature.watchedObject.value = 30.49 # Just below threshold.  
        self.waitDuring(1, 'Check alert is not fired.', [lambda: self.assertAlert([], [], [])], 0, 0)
        outdoorTemperature.watchedObject.value = 30.5 # Threshold.  
        self.waitDuring(1.5, 'Check alert is fired.', [lambda: self.assertAlert([], [], [outdoorTemperature])], 0.5, 0) # Temperature probes' alert does not last. They switch to the alert state quickly.

        # Lower temperature below alert threshold to stop alert.
        outdoorTemperature.watchedObject.value = 28 # Less than threshold - hysteresis.
        self.waitDuring(1, 'Ending alert...', [lambda: self.assertAlert([], [], [outdoorTemperature])], 0, 0)

    # def testPurge(self):
        # daemon = self.alarmDaemon
        # today = datetime.date.today()
        # camille = daemon.getSensorByName('Camille')
# 
        # # Build two event directories, one to be deleted and the other to be
        # # kept.
        # twentyDays = datetime.timedelta(20)
        # farDate = today - 2 * twentyDays
        # closeDate = today - twentyDays
        # try:
            # os.makedirs(os.path.join(camille.motionOutputDir, farDate.__str__())) # makedirs rather than mkdir, to create intermediate-level directories.
            # os.mkdir(os.path.join(camille.motionOutputDir, closeDate.__str__()))
# 
            # # Add an extra directory that does not look like an event, to make sure
            # # it is not deleted.
            # dummyDir = 'foodir'
            # os.mkdir(os.path.join(camille.motionOutputDir, dummyDir))
# 
            # # Purge.
            # daemon.purgeTemporaryFiles(21)
# 
            # # Check.
            # files = os.listdir(camille.motionOutputDir)
            # self.assertTrue(closeDate.__str__() in files)
            # self.assertTrue(dummyDir in files)
            # self.assertFalse(farDate.__str__() in files)
        # finally:
            # # Delete test dir.
            # shutil.rmtree(camille.motionOutputDir)

    def testLinknxAction(self):
        """ Exercises one of the various actions that can be performed by linknx. """

        # Prepare sensors involved in this test.
        intrusionSensor = self.alarmDaemon.getSensorByName('KitchenWindowOpening')
        intrusionAlert = self.alarmDaemon.getAlertByName('Intrusion')
        sirenObject = self.linknx.getObject('Siren')
        modeObject = self.linknx.getObject('Mode')
        appliedModeObject = self.linknx.getObject('AppliedMode')

        # Initialize state to a known one.
        self.alarmModeObject.value = 1
        intrusionSensor.watchedObject.value = False

        self.waitDuring(0.5, 'Initializing')
        modeChangeTime = time.time()
        self.emailInfo = None # In case mode initialization has raised an email.
        self.changeAlarmMode('Away', 'notify@bar.com')

        self.waitUntil(modeChangeTime + intrusionSensor.getActivationDelay() + 0.5, 'Waiting for sensor to activate.')

        # Intrusion!
        triggerTime = time.time()
        intrusionSensor.watchedObject.value = True
        self.waitUntil(triggerTime + intrusionSensor.getPrealertDuration() + 0.2, 'Waiting for prealert to expire.', [lambda: self.assertFalse(sirenObject.value), lambda: self.assertIsNone(self.emailInfo)], 0, 0.3)
        self.assertEmail('Sensor joined', ['intrusion@foo.com'], 'Alert Intrusion: sensor joined', [])
        self.waitUntil(triggerTime + intrusionSensor.getPrealertDuration() + intrusionSensor.getAlertDuration(), 'Waiting for alert to expire.', [lambda: self.assertTrue(sirenObject.value)], 0.2, 0.1)
        self.waitDuring(2, 'Checking siren is now off again.', [lambda: self.assertFalse(sirenObject.value)], 0.2, 0)

        # Check AppliedMode object has been synch'ed with Mode with a copy-value
        # action.
        self.assertEqual(appliedModeObject.value, modeObject.value)

        # Change mode again.
        self.changeAlarmMode('Presence', 'notify@bar.com')
        self.assertEqual(appliedModeObject.value, modeObject.value)

if __name__ == '__main__':
    unittest.main()
