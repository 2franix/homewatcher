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

from homewatcher import ensurepyknx

from pyknx import logger
from homewatcher import configuration, timer
import subprocess
import tempfile
import os
import threading
import time
import smtplib
import ftplib
# from homewatcher import alarm

class ActivationCriterion(object):
    """ Represents a criterion that tells if a sensor can be activated. Criterion's logic has to be implemented in method named isValid(self). """
    def __init__(self, sensor, config):
        self.sensor = sensor
        self.config = config
        self.daemon = sensor.daemon

    @staticmethod
    def makeNew(forSensor, config):
        if config is None: return None

        if config.type == configuration.ActivationCriterion.Type.SENSOR:
            return SensorActivationCriterion(forSensor, config)
        elif config.type in (configuration.ActivationCriterion.Type.AND, configuration.ActivationCriterion.Type.OR):
            return BooleanActivationCriterion(forSensor, config)
        else:
            raise Exception('Unsupported criterion type "{0}".'.format(config.type))

class SensorActivationCriterion(ActivationCriterion):
    """ Criterion that allows sensor activation if another sensor is triggered or not. """
    def __init__(self, sensor, config):
        ActivationCriterion.__init__(self, sensor, config)

    @property
    def watchedSensor(self):
        return self.daemon.getSensorByName(self.config.sensorName)

    @property
    def shouldBeTriggered(self):
        return self.config.whenTriggered

    def isValid(self):
        return self.watchedSensor.isTriggered == self.shouldBeTriggered

class BooleanActivationCriterion(ActivationCriterion):
    def __init__(self, sensor, config):
        ActivationCriterion.__init__(self, sensor, config)
        self.children = []
        for childConfig in config.children:
            self.children.append(ActivationCriterion.makeNew(sensor, childConfig))

    @property
    def type(self):
        return self.config.type

    def isValid(self):
        for child in self.children:
            if self.config.type == configuration.ActivationCriterion.Type.AND:
                if not child.isValid(): return False
            elif self.config.type == configuration.ActivationCriterion.Type.OR:
                if child.isValid(): return True
            else:
                raise Exception('Unsupported criterion type "{0}".'.format(self.config.type))

        if self.config.type == configuration.ActivationCriterion.Type.AND:
            return True
        elif self.config.type == configuration.ActivationCriterion.Type.OR:
            return False
        else:
            raise Exception('Unsupported criterion type "{0}".'.format(self.config.type))

class SubprocessLoggerThread(threading.Thread):
    def __init__(self, process, readsStdout, name):
        threading.Thread.__init__(self, name='Logger thread')
        self.process = process
        self.readsStdout = readsStdout
        self.name = name

    def run(self):
        statusFormat = 'Logger thread for std{0} of {1} PID=<{2}> is {3}.'.format('out' if self.readsStdout else 'err', self.name, self.process.pid, '{0}')
        logger.reportInfo(statusFormat.format('started'))
        while self.process.returncode is None:
            stream = self.process.stdout if self.readsStdout else self.process.stderr
            line = stream.readline()
            if line == '':
                time.sleep(1)
                continue

            line = line.rstrip('\n')
            log = '[{0}.{3} pid={1}] {2}'.format(self.name, self.process.pid, line, 'out' if self.readsStdout else 'err')
            logger.reportInfo(log)
        logger.reportInfo(statusFormat.format('terminated'))

class Sensor(object):
    def __init__(self, daemon, config):
        # Classes cannot be instanciated!
        if config.isClass:
            raise Exception('Sensor config {0} represents a sensor class. It cannot be used to instanciate a sensor.'.format(config.name))

        self._daemon = daemon
        self._config = config
        self.linknx = daemon.linknx
        self._isTriggered = None # Is initialized at the end of __init__, once all data members are set.
        self._activationTimer = None
        self._enabledObject = self.linknx.getObject(config.enabledObjectId)
        self._watchedObject = self.linknx.getObject(config.watchedObjectId)
        self._persistenceObject = self.linknx.getObject(config.persistenceObjectId)
        self.alert = self._daemon.getAlertByName(config.alertName)
        self.activationCriterion = ActivationCriterion.makeNew(self, config.activationCriterion)
        self._lock = threading.RLock()

        # Compute the initial trigger state.
        self._isTriggered = self.getUpdatedTriggerState()

    def isRequiredByCurrentMode(self):
        if self._daemon._isTerminated: return False

        # Simple case: the sensor is specified by its name in config.
        return self.name in self._daemon.currentMode.sensorNames

        # # Advanced case: one of the sensor base classes is specified by its name
        # # in config.
        # baseClassesNames = set(self.getInheritedClassNames())
# 
        # return len(baseClassesNames.intersection(self._daemon.currentMode.sensorNames)) > 0

    @property
    def daemon(self):
        return self._daemon

    @property
    def config(self):
        return self._config

    @property
    def name(self):
        return self._config.name

    @property
    def description(self):
        return self._config.description

    @property
    def type(self):
        return self._config.type

    @property
    def watchedObject(self):
        return self._watchedObject

    @property
    def watchedObjectId(self):
        return self._config.watchedObjectId

    @property
    def isTriggered(self):
        return self._isTriggered

    def isNotTriggered(self):
        return not self.isTriggered

    @property
    def persistenceObject(self):
        return self._persistenceObject

    @property
    def isInPrealert(self):
        return self in self.alert.sensorsInPrealert

    @property
    def isAlertActive(self):
        return self in self.alert.sensorsInAlert

    # @property
    # def isInhibited(self):
        # return self.alert.isInhibited

    # @isAlertActive.setter
    # def isAlertActive(self, value):
        # # No change.
        # if self.isAlertActive == value: return
# 
        # # Check that alert should not be discarded.
        # if value and self.isInhibited:
            # logger.reportWarning('{0}\' alert will not become active because its alert type is currently inhibited.'.format(self))
            # return
# 
        # # Change alert state.
        # self.setAlertActiveRaw(value)
# 
        # # Also set as active all sensors currently in prealert.
        # if value:
            # for sensor in self.daemon.sensors:
                # if sensor == self: continue
                # if sensor.isInPrealert and sensor.alertName == self.alertName:
                    # logger.reportInfo('{0} is in prealert, let it join the current alert immediately!'.format(sensor))
                    # sensor.setAlertActiveRaw(True)
# 
    # def setAlertActiveRaw(self, value):
        # """
        # Updates the internal alert active status without reevaluating daemon's alert status.
# 
        # value Whether alert is active.
        # returns True if state changed, False if sensor's alert state was already correct.
        # """
# 
        # # No change.
        # if value == self.isAlertActive: return False
# 
        # if value:
            # logger.reportInfo('Sensor {0}\'s alert is active.'.format(self))
            # # Do not set persistent alert immediately. Wait for alert to be
            # # implemented for that (or sensors will always consider alert has
            # # already been previously triggered).
            # # self.persistenceObject.value = True
        # else:
            # logger.reportInfo('Sensor {0}\'s alert is no more active. If an alert is current, this sensor will not participate.'.format(self.name))
        # if value:
            # self.alert.addSensorToAlert(self)
        # else:
            # self.alert.removeSensorFromAlert(self)
# 
        # if not value and not self._alertTimer is None:
            # self._alertTimer.stop()
            # self._alertTimer = None
        # return True

    def implementEmail(self, emailDescription):
        pass

    # def implementAlert(self, alertDescription):
        # logger.reportDebug('{0} is now implementing alert'.format(self))
        # if not self.isEnabled:
            # logger.reportDebug('{0} is not enabled, alert implementation is empty.'.format(self))
            # return
        # if not self.isAlertActive:
            # logger.reportDebug('{0}\'s alert is not active, alert implementation is empty.'.format(self))
            # return
# 
        # alertDescription.setCurrentSensor(self)
        # try:
            # self.implementAlertRaw(alertDescription)
        # finally:
            # alertDescription.setCurrentSensor(None)

    @property
    def isEnabled(self):
        """ Tell whether the sensor is currently active (i.e under surveillance and able to fire alarm) """
        return self._enabledObject.value

    @isEnabled.setter
    def isEnabled(self, value):
        with self._lock:
            logger.reportDebug('{1}.isEnabled={0}, activationTimer is {2}'.format(value, self, self._activationTimer))
            if not value:
                self.stopActivationTimer()

            if self._enabledObject.value == value: return

            # Make sure this sensor is still required by the current mode.
            # Safer in case of data race between the thread that runs
            # updateModeFromLinknx and the one that runs the activation timer.
            if self.isRequiredByCurrentMode() or not value:
                self._enabledObject.value = value

            if value:
                try:
                    if self.persistenceObject != None:
                        self.persistenceObject.value = False
                    self.onEnabled()
                except Exception as e:
                    self._enabledObject.value = False
                    logger.reportException()
            else:
                # Sensor may currently be in alert.
                self.alert.removeSensorFromAlert(self)
                self.onDisabled()

            logger.reportInfo('Sensor {0} is now {1}'.format(self.name, 'enabled' if value else 'disabled'))

    def getInheritedClassNames(self):
            return [sensorConfig.name for sensorConfig in self.daemon.configuration.getInheritedClassNames(self.config)]

    def makePrealertTimer(self):
        def onPrealertEnded(timer):
            self.alert.notifySensorPrealertExpired(self)
        return timer.Timer(self, self.getPrealertDuration(), 'Prealert timer', onTimeoutReached=onPrealertEnded, onTerminated=None)

    def makeAlertTimer(self):
        def onAlertEnded(timer):
            self.alert.removeSensorFromAlert(self)
        return timer.Timer(self, self.getAlertDuration(), 'Alert timer', onTimeoutReached=None, onTerminated=onAlertEnded)

    def getUpdatedTriggerState(self):
        """
        Return the new trigger state.

        Implement sensor's logic here. The default implementation returns the watched object's value, which should suit most sensor types.
        """
        return self.watchedObject.value

    def getPrealertDuration(self):
        return self._config.prealertDuration.getForMode(self.daemon.currentMode.name)

    def getAlertDuration(self):
        return self._config.alertDuration.getForMode(self.daemon.currentMode.name)

    def getActivationDelay(self):
        delay = self._config.activationDelay.getForMode(self.daemon.currentMode.name)
        logger.reportDebug('getActivationDelay of {2} for {0}, currentMode={1}'.format(self, self.daemon.currentMode, delay))
        return delay

    def onEnabled(self):
        pass

    def onDisabled(self):
        pass

    def isActivationPending(self):
        return self._activationTimer != None and self._activationTimer.isAlive() and not self._activationTimer.isTerminating

    def _onActivationTimerTimeout(self, timer):
        if not timer.isCancelled:
            self.isEnabled = True

    def _onActivationTimerIterate(self, timer):
        if self.activationCriterion != None and not self.activationCriterion.isValid():
            if not timer.isPaused:
                logger.reportInfo('Pausing activation timer for {0} because activation criterion is not satisfied.'.format(self))
            timer.pause()
        else:
            if timer.isPaused:
                # Restart activation delay.
                logger.reportInfo('Restarting activation timer for {0} because activation criterion is now satisfied.'.format(self))
                timer.reset()

    def startActivationTimer(self):
        # Already enabled.
        if self.isEnabled: return

        if self.isActivationPending():
            logger.reportInfo('An activation timer for {0} is already running. Cancel it and start a new one.'.format(self))
            self._activationTimer.stop()
        self._activationTimer = timer.Timer(self, self.getActivationDelay(), 'Activation timer', onTimeoutReached=self._onActivationTimerTimeout, onIterate=self._onActivationTimerIterate)
        self._activationTimer.start()

    def stopActivationTimer(self):
        if self._activationTimer != None:
            self._activationTimer.stop()
            self._activationTimer = None

    def notifyWatchedObjectChanged(self):
        """ Notifies the sensor that its watched object's value has just changed. """
        newTriggeredState = self.getUpdatedTriggerState() # Depends on the concrete sensor class. Most of them will do nothing as trigger state IS the watched object state. But for FloatSensor for instance, trigger may take an hysteresis into account.
        if self._isTriggered == newTriggeredState: return
        self._isTriggered = newTriggeredState
        if self.isTriggered:
            logger.reportInfo('{0} is triggered.'.format(self.name))
            if self.isEnabled:
                self.alert.addSensorToAlert(self)
        else:
            # Nothing to do regarding alert here. If sensor was previously
            # triggered, alert will not end by simply releasing trigger.
            logger.reportInfo('{0}\'s trigger is released.'.format(self.name))

    def __repr__(self):
        if self.description != None and len(self.description) > 0:
            return '{name} ({description})'.format(name=self.name, description=self.description)
        else:
            return '{name}'.format(name=self.name)

class FloatSensor(Sensor):
    def __init__(self, daemon, config):
        Sensor.__init__(self, daemon, config)

    def getUpdatedTriggerState(self):
        value = self.watchedObject.value
        low = self.config.lowerBound
        up = self.config.upperBound
        if self.isTriggered:
            # Apply hysteresis.
            if not low is None: low += self.config.hysteresis
            if not up is None: up -= self.config.hysteresis
        if not low is None and value <= low: return True
        if not up is None and value >= up: return True
        return False

    def notifyAlertsInhibited(self, isIntrusionInhibited, isFireInhibited):
        pass

    # def implementAlertRaw(self, alertDescription):
        # alertDescription.setTemperature()
        # currentTemp = self.temperatureObject.value
        # if self.highLimit != None and currentTemp > self.highLimit - self.hysteresis:
            # heatingErrorType = 'élevée'
            # threshold = self.highLimit
        # elif self.lowLimit != None:
            # heatingErrorType = 'basse'
            # threshold = self.lowLimit
        # alertDescription.addEmailText('Alerte température trop {2}, temp={0}°C, seuil d\'alerte={1}°C'.format(self.temperatureObject.value, threshold, heatingErrorType))

class BooleanSensor(Sensor):
    def __init__(self, daemon, config):
        Sensor.__init__(self, daemon, config)

    def getUpdatedTriggerState(self):
        if self.config.triggerValue:
            return self.watchedObject.value
        else:
            return not self.watcheObject.value
