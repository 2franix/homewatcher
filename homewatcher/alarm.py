#!/usr/bin/python3

# Copyright (C) 2012-2017 Cyrille Defranoux
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
import subprocess
import tempfile
import os
import sys
import threading
import time
import smtplib
import ftplib
import datetime
import shutil
import homewatcher
from homewatcher import sensor, configuration, contexthandlers
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
import email.header
from email import encoders
import xml.dom.minidom

class AlertStatusBlocker(object):
    """ RAII wrapper for blocking/releasing the immediate status update of alerts.

        This is useful to avoid numerous updates when disabling sensors one by one while still being sure that Alert.updateStatus
        is called whenever it is required."""

    def __init__(self, daemon):
        self.daemon = daemon

    def __enter__(self):
        self.daemon._suspendAlertStatusUpdates = True

    def __exit__(self, exc_type, exc_value, traceback):
        self.daemon._suspendAlertStatusUpdates = False
        for alert in self.daemon.alerts:
            alert.updateStatus()

class Action(object):
    """
    Base class for actions to be performed when an event is raised.

    Action classes must implement their job in the execute() method.
    """

    def __init__(self, daemon, config):
        self.daemon = daemon
        self._config = config
        self.actionXml = xml.dom.minidom.Document()
        self.actionXml.appendChild(self.actionXml.importNode(config.linknxActionXml, True))

    @property
    def description(self):
        return self._config.description

    @property
    def type(self):
        return self._config.type

    def parseParameterizableString(self, parameterizedStringXml, context):
        text = ''
        for childNode in parameterizedStringXml.childNodes:
            if childNode.nodeType == xml.dom.minidom.Element.ELEMENT_NODE:
                tagName = childNode.tagName
                if tagName == 'br':
                    text += '\n'
                elif tagName == 'context':
                    text += contexthandlers.ContextHandlerFactory.getInstance().makeHandler(childNode).analyzeContext(context)
            elif childNode.nodeType == xml.dom.minidom.Element.TEXT_NODE:
                text += childNode.data
        return text

    def execute(self, context):
        """ Implements the concrete job of the action. """
        raise Exception('Action\'s job is not implemented.')

    def __repr__(self):
        return self.description

class SendEmailAction(Action):
    """ Action that notifies of the alert by email. """
    def __init__(self, daemon, config):
        Action.__init__(self, daemon, config)

    def execute(self, context):
        # Initialize the XML to send to linknx with the XML from homewatcher
        # configuration. That will duplicate the static subject and body, if
        # defined.
        linknxActionXml = xml.dom.minidom.Document()
        linknxActionXml.appendChild(linknxActionXml.importNode(self.actionXml.childNodes[0], True))

        # As a second step, interpret any parameterizable block.
        actionXmlNode = linknxActionXml.getElementsByTagName('action')[0]
        parameterizedBody = None
        for childNode in actionXmlNode.childNodes:
            if childNode.nodeType == xml.dom.minidom.Element.ELEMENT_NODE:
                tagName = childNode.tagName
                if tagName == 'subject':
                    actionXmlNode.setAttribute('subject', self.parseParameterizableString(childNode, context))
                    actionXmlNode.removeChild(childNode)
                elif tagName == 'body':
                    parameterizedBody = self.parseParameterizableString(childNode, context)
                    actionXmlNode.removeChild(childNode)

        # If parameterizable body is used, allow for adding carriage returns and
        # tabulations inside the <action> element to enhance XML text layout. To
        # do so, we have to delete inner text nodes of the initial XML data.
        if parameterizedBody != None:
            while actionXmlNode.childNodes:
                actionXmlNode.removeChild(actionXmlNode.childNodes[0])

            textNode = linknxActionXml.createTextNode(parameterizedBody)
            actionXmlNode.appendChild(textNode)

        # Append footer.
        footer = """

--------------------------------------------------------
This email was sent by Homewatcher v{0} on {1}""".format(homewatcher.__version__, datetime.datetime.now())
        footerNode = linknxActionXml.createTextNode(footer)
        actionXmlNode.appendChild(footerNode)

        self.daemon.sendEmail(linknxActionXml)

class SendSMSAction(Action):
    """ Action that notifies of the alert by SMS. """
    def __init__(self, daemon, config):
        Action.__init__(self, daemon, config)

    def execute(self, context):
        # Initialize the XML to send to linknx with the XML from homewatcher
        # configuration. That will duplicate the static subject and body, if
        # defined.
        linknxActionXml = xml.dom.minidom.Document()
        linknxActionXml.appendChild(linknxActionXml.importNode(self.actionXml.childNodes[0], True))

        # As a second step, interpret any parameterizable block.
        actionXmlNode = linknxActionXml.getElementsByTagName('action')[0]
        for childNode in actionXmlNode.childNodes:
            if childNode.nodeType == xml.dom.minidom.Element.ELEMENT_NODE:
                if childNode.tagName == 'value':
                    actionXmlNode.setAttribute('value', self.parseParameterizableString(childNode, context))
                    actionXmlNode.removeChild(childNode)

        self.daemon.linknx.executeAction(linknxActionXml)

class ShellCommandAction(Action):
    def __init__(self, daemon, config):
        Action.__init__(self, daemon, config)

    def execute(self, context):
        # Initialize the XML to send to linknx with the XML from homewatcher
        # configuration.
        linknxActionXml = xml.dom.minidom.Document()
        linknxActionXml.appendChild(linknxActionXml.importNode(self.actionXml.childNodes[0], True))

        # As a second step, interpret any parameterizable block.
        actionXmlNode = linknxActionXml.getElementsByTagName('action')[0]
        for childNode in actionXmlNode.childNodes:
            if childNode.nodeType == xml.dom.minidom.Element.ELEMENT_NODE:
                if childNode.tagName == 'cmd':
                    actionXmlNode.setAttribute('cmd', self.parseParameterizableString(childNode, context))
                    actionXmlNode.removeChild(childNode)

        self.daemon.linknx.executeAction(linknxActionXml)

class LinknxAction(Action):
    """ Action that sets the value of an object. """
    def __init__(self, daemon, config):
        Action.__init__(self, daemon, config)

    def execute(self, context):
        self.daemon.linknx.executeAction(self.actionXml)
# 
# class FTPSender(threading.Thread):
    # def __init__(self, daemon, url):
        # threading.Thread.__init__(self, name='FTP backup thread')
        # self.url = url
        # self._daemon = daemon
        # self.loginInfoFile = os.path.join(daemon.motionConfigDir, '.ftpcredentials')
        # self.isTerminated = False
        # self._connection = None
        # # self._rootDirOnServer = '/motion.alert'
# 
    # def stop(self):
        # if not self.isTerminated:
            # logger.reportInfo('Terminating FTP backup thread...')
        # self.isTerminated = True
# 
    # def getConnection(self):
        # if not self._connection:
            # self._openConnection()
        # return self._connection
# 
    # def _openConnection(self):
        # if self._connection:
            # raise Exception('Connection already open.')
# 
        # loginInfoFile = open(self.loginInfoFile, 'r')
        # try:
            # [login, passwd] = [l.rstrip('\n') for l in loginInfoFile.readlines()]
        # finally:
            # loginInfoFile.close()
            # loginInfoFile = None
# 
        # self._connection = ftplib.FTP(user=login, passwd=passwd, timeout=20)
        # self._connection.connect(host=self.url.netloc, port=self.url.port)
# 
        # logger.reportInfo('FTP backup thread connection is open.')
# 
    # def _closeConnection(self):
        # if not self._connection: return
# 
        # try:
            # self._connection.quit()
        # except Exception as e:
            # logger.reportException()
        # self._connection = None
        # logger.reportInfo('FTP backup thread connection is closed.')
# 
    # def _getErrorCodeFromException(self):
        # excep = sys.exc_info()[1]
        # logger.reportDebug('FTP exception: {0}.'.format(excep))
        # return int(excep.message[:3])
# 
    # def _cwd(self, directoryOnServer, createsIfNotFound):
        # """ Performs a current directory change relative to the motion root on server. """
        # directory = os.path.join(self.url.path, directoryOnServer)
        # try:
            # self.getConnection().cwd(directory)
        # except ftplib.all_errors:
            # errorCode = self._getErrorCodeFromException()
            # currentDir = ''
            # if errorCode == 550 and createsIfNotFound:
                # # Create.
                # for level in directory.split('/'):
                    # if level == '': continue # Happens if directoryOnServer has a leading '/'
                    # self._mkdOneLevel(level, True)
                # logger.reportInfo('{0} created on FTP server.'.format(directory))
            # else:
                # raise
# 
            # # Try cwd'ing again.
            # self._cwd(directoryOnServer, False)
# 
    # def _mkdOneLevel(self, level, createsIfNotFound):
        # try:
            # self.getConnection().cwd(level)
        # except ftplib.all_errors as e:
            # if createsIfNotFound:
                # self.getConnection().mkd(level)
                # self._mkdOneLevel(level, False)
            # else:
                # raise e
# 
    # def run(self):
        # logger.reportInfo('FTP backup thread is ready. Configured for {0}'.format(self.url.geturl()))
# 
        # while not self.isTerminated:
            # try:
                # # Search for pictures to backup.
                # for camera in self._daemon.cameras:
                    # while camera.picturesToBackup:
                        # picture = camera.picturesToBackup.pop(0)
                        # if self.isTerminated:
                            # return
                        # pathOnServer, filename = os.path.split(os.path.relpath(picture, self._daemon.motionOutputDir))
                        # # Change directory on server.
                        # self._cwd(pathOnServer, True)
# 
                        # try:
                            # # Push file.
                            # pictureFile = None
                            # pictureFile = open(picture, 'rb')
                            # logger.reportDebug('Sending {0} to FTP server...'.format(filename))
                            # self.getConnection().storbinary('STOR {0}'.format(filename), pictureFile)
                            # logger.reportInfo(filename + ' has been sent to remote FTP server.')
                        # finally:
                            # if pictureFile: pictureFile.close()
                            # pictureFile = None
            # except Exception as e:
                # logger.reportException()
                # self.stop()
            # finally:
                # self._closeConnection()
                # time.sleep(2)
        # logger.reportInfo('FTP backup thread is now stopped.')

class EmailDescriptor(object):
    def __init__(self):
        self.text = {} # Email text lines stored by sensor: {sensor, [lines]}
        self.attachments = {} # Email attachments stored in tuples for each sensor({sensor, (file, description)}
        self._currentSensor = None # Sensor currently implementing alert.

    def setCurrentSensor(self, sensor):
        self._currentSensor = sensor

    @property
    def isEmpty(self):
        return len(self._emailText) == 0 and len(self._emailAttachments) == 0

    def addEmailText(self, text):
        if not self._currentSensor in self.text: self.text[self._currentSensor] = []
        self.text[self._currentSensor].append(text)

    def addEmailAttachment(self, attachment, description):
        if not self._currentSensor in self.attachments: self.attachments[self._currentSensor] = []
        self.attachments[self._currentSensor].append((attachment, description))

class Alert(object):
    class Status:
        STOPPED = 'stopped' # Alert is not currently fired and no sensor is triggered.
        INITIALIZING = 'initializing' # Alert is not currently fired but at least one sensor is in prealert state.
        ACTIVE = 'active' # Alert is currently fired.
        PAUSED = 'paused' # Alert has been fired. It is in a state in which no sensor is currently in alert. But if a sensor raises alert again, the alert would be resumed immediately.

    """ Represents a type of alert in the system. """
    def __init__(self, daemon, config):
        self.daemon = daemon
        self._lock = threading.RLock()
        self._config = config
        self._sensorsInPrealert = set()
        self._sensorsInAlert = set()
        self._sensorsInAlertOnLastUpdateStatus = set()
        self.status = Alert.Status.STOPPED
        self._sensorTimers = {} # Timers indexed by sensors. Each timer represents the prealert or alert timer for its associated sensor, depending on alert's current state.
        self.persistenceObject = daemon.linknx.getObject(config.persistenceObjectId) if config.persistenceObjectId != None else None
        self.inhibitionObject = daemon.linknx.getObject(config.inhibitionObjectId) if config.inhibitionObjectId != None else None
        self.eventManager = EventManager(daemon)
        self.isStatusDirty = False
        for eventConfig in self.daemon.configuration.alerts.events + self._config.events:
            self.eventManager.addEvent(eventConfig)

    @property
    def name(self):
        return self._config.name

    @property
    def inhibitionObjectId(self):
        return self._config.inhibitionObjectId

    @property
    def persistenceObjectId(self):
        return self._config.persistenceObjectId

    @property
    def isInitializing(self):
        return self.status == Alert.Status.INITIALIZING

    @property
    def isActive(self):
        return self.status == Alert.Status.ACTIVE

    @property
    def isStopped(self):
        return self.status == Alert.Status.STOPPED

    @property
    def isStarted(self):
        return not (self.isStopped or self.isPaused)

    @property
    def isPaused(self):
        return self.status == Alert.Status.PAUSED

    @property
    def sensors(self):
        for sensor in self.daemon.sensors:
            if sensor.alert == self:
                yield sensor

    @property
    def sensorsInPrealert(self):
        return self._sensorsInPrealert

    @property
    def sensorsInAlert(self):
        return self._sensorsInAlert

    @property
    def pausedSensors(self):
        def isSensorPaused(sensor):
            persistenceObject = sensor.persistenceObject
            if persistenceObject == None or not persistenceObject.value:
                return False
            return not sensor in self.sensorsInAlert # Cannot be in prealert if persistence object is true.
        return [s for s in self.sensors if isSensorPaused(s)]

    # def resetPersistence(self):
        # self.persistenceObject.value = False
# 
    @property
    def isInhibited(self) :
        if self.inhibitionObject != None:
            return self.inhibitionObject.value
        else:
            return False

    def notifyAlertStarted(self):
        self.fireEvent(configuration.AlertEvent.Type.PREALERT_STARTED)

    def notifyAlertActivated(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_ACTIVATED)

    def notifyAlertDeactivated(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_DEACTIVATED)

    def notifyAlertPaused(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_PAUSED)

    def notifyAlertResumed(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_RESUMED)

    def notifyAlertAborted(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_ABORTED)

    def notifyAlertReset(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_RESET)

    def notifyAlertStopped(self):
        self.fireEvent(configuration.AlertEvent.Type.ALERT_STOPPED)

    def notifySensorJoined(self):
        self.fireEvent(configuration.AlertEvent.Type.SENSOR_JOINED)

    def notifySensorLeft(self):
        self.fireEvent(configuration.AlertEvent.Type.SENSOR_LEFT)

    def fireEvent(self, eventType):
        logger.reportInfo('Firing event {0} for {1}'.format(eventType, self))
        self.eventManager.fireEvent(eventType, 'Alert {0}: {1}'.format(self.name, eventType), self)

    def updateStatus(self):
        """
        Updates the status of this alert and raises the required events accordingly.

        """
        # Do not update if the daemon is in a process that may trigger
        # irrelevant intermediary states.
        if self.daemon.areAlertStatusUpdatesSuspended: return

        if not self.isStatusDirty:
            logger.reportDebug('Status of {0} is already up-to-date, nothing to change.'.format(self))
            return
        logger.reportDebug('Updating status of {0}'.format(self))

        # Compute current status.
        if self._sensorsInAlert:
            newStatus = Alert.Status.ACTIVE
        elif self._sensorsInPrealert:
            newStatus = Alert.Status.INITIALIZING
        elif self.status == Alert.Status.ACTIVE and (self.persistenceObject != None and self.persistenceObject.value):
            # PAUSED status may only occur if persistence is supported.
            # Otherwise, as soon as last sensor leaves the alert, alert is
            # stopped and will start if a sensor gets triggered afterwards. This
            # is not the most convenient behaviour but with it, the user is free not to
            # define persistence.
            newStatus = Alert.Status.PAUSED
        else:
            newStatus = Alert.Status.STOPPED

        logger.reportDebug('New status for {0} is {1}'.format(self, newStatus))

        # When the alert is active, all sensors should leave the "prealert"
        # state to join the alert.
        if newStatus in (Alert.Status.ACTIVE, Alert.Status.PAUSED): # PAUSED is to be on the safe side as alert should always go through the ACTIVE state before going to PAUSED.
            for sensor in self._sensorsInPrealert:
                if not sensor in self._sensorsInAlert:
                    self._sensorsInAlert.add(sensor) # None at this point. Timers will be created later in this method.   # sensor.makeAlertTimer(onTimeoutReached=None, onTerminated=lambda: self.removeSensorFromAlert(sensor))
            self._sensorsInPrealert = set()

        # Diff registered sensors.
        joiningSensors = self._sensorsInAlert - self._sensorsInAlertOnLastUpdateStatus
        leavingSensors = self._sensorsInAlertOnLastUpdateStatus- self._sensorsInAlert
        logger.reportDebug('Updating status for {0}: joiningSensors={1}, leavingSensors={2}'.format(self, joiningSensors, leavingSensors))

        if newStatus == Alert.Status.ACTIVE:
            if self.persistenceObject != None: self.persistenceObject.value = True

        # Handle consequences of status change.
        if self.status == Alert.Status.STOPPED:
            if newStatus == Alert.Status.STOPPED:
                # No change.
                pass
            elif newStatus == Alert.Status.INITIALIZING:
                self.notifyAlertStarted()
            else:
                # Should not happen.
                logger.reportError('Unsupported switch from "{old}" to "{new}" for alert {alert}'.format(alert=self, old=self.status, new=newStatus))
        elif self.status == Alert.Status.ACTIVE:
            if newStatus == Alert.Status.ACTIVE:
                # Check if a sensor joined or left.
                if joiningSensors:
                    self.notifySensorJoined()
                if leavingSensors:
                    self.notifySensorLeft()
            elif newStatus in (Alert.Status.PAUSED, Alert.Status.STOPPED):
                if not leavingSensors:
                    logger.reportError('A sensor should have left the alert.')
                else:
                    self.notifySensorLeft()

                self.notifyAlertDeactivated()

                if newStatus == Alert.Status.STOPPED:
                    self.notifyAlertReset()
                    self.notifyAlertStopped()
                elif newStatus == Alert.Status.PAUSED:
                    self.notifyAlertPaused()
                else:
                    raise Exception('Not implemented.')

            else:
                # Should not happen.
                logger.reportError('Unsupported switch from "{old}" to "{new}" for alert {alert}'.format(alert=self, old=self.status, new=newStatus))
        elif self.status == Alert.Status.PAUSED:
            if newStatus == Alert.Status.PAUSED:
                # No change.
                pass
            elif newStatus == Alert.Status.STOPPED:
                self.notifyAlertReset()
                self.notifyAlertStopped()
            elif newStatus == Alert.Status.ACTIVE:
                self.notifyAlertResumed()
                if not joiningSensors:
                    logger.reportError('A sensor should have joined the alert.')
                else:
                    self.notifySensorJoined()
                self.notifyAlertActivated()
        elif self.status == Alert.Status.INITIALIZING:
            if newStatus == Alert.Status.INITIALIZING:
                # No change.
                pass
            elif newStatus == Alert.Status.ACTIVE:
                # Events to raise: started, sensor-joined, activated.
                if not joiningSensors:
                    logger.reportError('A sensor should have joined the alert.')
                else:
                    self.notifySensorJoined()
                self.notifyAlertActivated()
            elif newStatus == Alert.Status.STOPPED:
                self.notifyAlertAborted()
                self.notifyAlertStopped()

        # Stop obsolete timers for all sensors related to this alert.
        if newStatus in (Alert.Status.PAUSED, Alert.Status.STOPPED) or (self.status == Alert.Status.INITIALIZING and newStatus == Alert.Status.ACTIVE):
            for sensor in self.sensors:
                # Get the optional timer currently running for this sensor.
                timer = self._sensorTimers.get(sensor)
                if timer == None: continue

                timer.stop()
                timer = None
                del self._sensorTimers[sensor]

        for sensor in self._sensorsInAlert.union(self._sensorsInPrealert):
            # Start a new timer?
            if newStatus in (Alert.Status.INITIALIZING, Alert.Status.ACTIVE) and self._sensorTimers.get(sensor) == None:
                timer = sensor.makePrealertTimer() if newStatus == Alert.Status.INITIALIZING else sensor.makeAlertTimer()
                self._sensorTimers[sensor] = timer # Prealert timer has been deleted above if applicable.
                timer.start()

        # Update persistence objects for all sensors.
        for s in self._sensorsInAlert:
            if s.persistenceObject != None:
                s.persistenceObject.value = True

        # Store current status.
        self._sensorsInAlertOnLastUpdateStatus = self._sensorsInAlert.copy()
        self.status = newStatus
        self.isStatusDirty = False

    def invalidateStatus(self):
        self.isStatusDirty = True

    def addSensorToAlert(self, sensor):
        if self.isInhibited:
            logger.reportInfo('{0} will not join {1} since alert is currently inhibited (cf value of {2}).'.format(sensor, self, self.inhibitionObject))
            return

        with self._lock:
            logger.reportInfo('Sensor {0} joins {1}'.format(sensor, self))

            # Decide whether sensor should go through an initial prealert state.
            if self.status in (Alert.Status.STOPPED, Alert.Status.INITIALIZING):
                self._sensorsInPrealert.add(sensor)
                self.invalidateStatus()
            elif self.status in (Alert.Status.PAUSED, Alert.Status.ACTIVE):
                if not sensor in self._sensorsInAlert:
                    # Sensor joins the alert.
                    self._sensorsInAlert.add(sensor)
                    self.invalidateStatus()
                else:
                    # Sensor is retriggered during its alert. Extend alert
                    # duration.
                    self._sensorTimers[sensor].extend()
            self.updateStatus()

    def notifySensorPrealertExpired(self, sensor):
        with self._lock:
            if not sensor in self._sensorsInPrealert: return

            self._sensorsInPrealert.remove(sensor)
            self._sensorsInAlert.add(sensor)
            self.invalidateStatus();
            self.updateStatus()

    def removeSensorFromAlert(self, sensor):
        with self._lock:
            hasChanged = sensor in self._sensorsInPrealert or sensor in self._sensorsInAlert
            self._sensorsInPrealert.discard(sensor)
            self._sensorsInAlert.discard(sensor)
            if hasChanged: self.invalidateStatus()
            self.updateStatus()

    def stop(self):
        with self._lock:
            if self.isStopped: return

            logger.reportDebug('Stopping {0}: sensorsInPrealert={1} sensorsInAlert={2}'.format(self, self._sensorsInPrealert, self._sensorsInAlert))
            hasChanged = len(self._sensorsInPrealert) + len(self._sensorsInAlert) != 0
            self._sensorsInPrealert.clear()
            self._sensorsInAlert.clear()
            self.invalidateStatus()
            self.updateStatus()

    def __repr__(self):
        return 'Alert(\'{0}\')'.format(self.name)

# class _AlertDescription(object):
    # def __init__(self, daemon):
        # self._daemon = daemon
        # self.usesLoudSiren = False
        # self.usesLightweightSiren = False
        # self._emailText = {} # Email text lines stored by sensor: {sensor, [lines]}
        # self._emailAttachments = {} # Email attachments stored in tuples for each sensor({sensor, (file, description)}
        # self.sendsIntrusionSMS = False
        # self.sendsFireSMS = False
        # self.types = set()
        # self._currentSensor = None # Sensor currently implementing alert.
# 
    # @property
    # def daemon(self):
        # return self._daemon
# 
    # def setCurrentSensor(self, sensor):
        # self._currentSensor = sensor
# 
    # def addLoudSiren(self):
        # self.usesLoudSiren = True
# 
    # def addLightSiren(self):
        # self.usesLightweightSiren = True
# 
    # @property
    # def isIntrusion(self):
        # return Daemon.INTRUSION in self.types
# 
    # def setIntrusion(self):
        # self.types.add(Daemon.INTRUSION)
# 
    # @property
    # def isFire(self):
        # return Daemon.FIRE in self.types
# 
    # def setFire(self):
        # self.types.add(Daemon.FIRE)
# 
    # @property
    # def isTemperature(self):
        # return Daemon.TEMPERATURE in self.types
# 
    # def setTemperature(self):
        # self.types.add(Daemon.TEMPERATURE)
# 
    # def addIntrusionSMS(self):
        # logger.reportDebug('{0} asks for intrusion SMS.'.format(self._currentSensor))
        # self.sendsIntrusionSMS = True
# 
    # def addFireSMS(self):
        # logger.reportDebug('{0} asks for fire SMS.'.format(self._currentSensor))
        # self.sendsFireSMS = True
# 
    # @property
    # def sendsEmail(self):
        # return len(self._emailText) > 0 or len(self._emailAttachments) > 0
# 
    # def addEmailText(self, text):
        # if not self._emailText.has_key(self._currentSensor): self._emailText[self._currentSensor] = []
        # self._emailText[self._currentSensor].append(text)
# 
    # def addEmailAttachment(self, attachment, description):
        # if not self._emailAttachments.has_key(self._currentSensor): self._emailAttachments[self._currentSensor] = []
        # self._emailAttachments[self._currentSensor].append((attachment, description))
# 
    # def sendEmail(self, isAlertContinued):
        # subject='Alerte {0}{1}'.format(', '.join(self.types), ' (suite)' if isAlertContinued else '')
        # text='On ' + time.asctime() + ':\n'
        # for sensor, lines in self._emailText.iteritems():
            # text += '\n{0} :\n\t'.format(sensor.description)
            # text += '\n\t'.join(lines)
            # attachments = self._emailAttachments.get(sensor)
            # if attachments:
                # text += '\n\t{0} pièces jointes:'.format(len(attachments))
                # for file, desc in attachments:
                    # text += '\n\t' + os.path.basename(file) + ': ' + desc
# 
        # allAttachments=[]
        # for sensor, attachments in self._emailAttachments.iteritems():
            # for attachment in attachments:
                # allAttachments.append(attachment[0])
# 
        # self.daemon.sendEmail(toAddr=self.daemon.alertAddresses, subject=subject, text=text, attachments=allAttachments)

class EventManager(object):
    def __init__(self, daemon):
        self.daemon = daemon
        self.eventConfigs = [] # configuration.Event objects (subclasses of it, actually)

    def addEvent(self, eventConfig):
        self.eventConfigs.append(eventConfig)

    def fireEvent(self, eventType, description, context):
        """ Raises event (i.e executes every action related to this event). """
        logger.reportDebug('Firing event {0}'.format(description))
        for event in self.eventConfigs:
            if event.type != eventType: continue

            # Set up the various actions for that event type.
            logger.reportDebug('Executing actions {0}'.format(event.actions))
            for actionConfig in event.actions:
                if actionConfig.type == 'send-email':
                    action = SendEmailAction(self.daemon, actionConfig)
                elif actionConfig.type == 'send-sms':
                    action = SendSMSAction(self.daemon, actionConfig)
                elif actionConfig.type == 'shell-cmd':
                    action = ShellCommandAction(self.daemon, actionConfig)
                else:
                    # Delegate execution to linknx.
                    action = LinknxAction(self.daemon, actionConfig)

                action.execute(context)
        logger.reportDebug('Event {0} is now finished.'.format(description))

class Mode(object):
    def __init__(self, daemon, config):
        self._config = config
        self.daemon = daemon
        self.eventManager = EventManager(daemon)

        for eventConfig in daemon._config.modesRepository.events + config.events:
            self.eventManager.addEvent(eventConfig)

    @property
    def name(self):
        return self._config.name

    @property
    def value(self):
        return self._config.value

    @property
    def sensorNames(self):
        return self._config.sensorNames

    def makeEventContext(self):
        return {'mode' : self.name}

    def notifyEntered(self):
        self.eventManager.fireEvent(configuration.ModeEvent.Type.ENTERED, description='Entered mode {mode}', context=self)

    def notifyLeft(self):
        self.eventManager.fireEvent(configuration.ModeEvent.Type.LEFT, description='Left mode {mode}', context=self)

    def __repr__(self):
        return '{0} (value={1})'.format(self.name, self.value)

class Daemon(object):
    def __init__(self, communicator, configuration):
        configuration.resolve() # Does check integrity too.
        self._lock = threading.RLock()
        self.linknx = communicator.linknx
        self._config = configuration
        self.communicator = communicator
        self._modeValueObject = self.linknx.getObject(self._config.modesRepository.objectId)
        self._modes = {} # Key is mode's numeral value, value is mode object.
        for modeConfig in configuration.modesRepository.modes:
            self._modes[modeConfig.value] = Mode(self, modeConfig)
        self._alerts = {} # Key is alert name, value is alert object.
        self._suspendAlertStatusUpdates = False # Whether alerts should not update their statuses immediately.
        for alertConfig in configuration.alerts:
            self._alerts[alertConfig.name] = Alert(self, alertConfig)
        self._sensors = {} # Key is sensor name, value is sensor object.
        for sensorConfig in configuration.sensors:
            self._sensors[sensorConfig.name] = self._makeSensor(sensorConfig, configuration)
        self._isTerminated = False

        self._currentMode = None

        self._updateModeFromLinknx()

    def suspendAlertStatusUpdates(self):
        return AlertStatusBlocker(self)

    @property
    def areAlertStatusUpdatesSuspended(self):
        return self._suspendAlertStatusUpdates

    @property
    def configuration(self):
        return self._config

    @property
    def modes(self):
        return self._modes

    def getMode(self, modeNameOrValue):
        if isinstance(modeNameOrValue, int):
            return self._modes[modeNameOrValue]
        elif isinstance(modeNameOrValue, str):
            modesByThatName = [m for m in self._modes.values() if m.name == modeNameOrValue]
            if not modesByThatName: raise Exception('No mode {0}.'.format(modeNameOrValue))
            if len(modesByThatName) > 1: raise Exception('Several mode hold the name {0}'.format(modeNameOrValue))
            return modesByThatName[0]

    def _makeSensor(self, sensorConfiguration, hwConfig):
        if hwConfig.doesSensorInherit(sensorConfiguration, configuration.Sensor.Type.BOOLEAN):
            return sensor.BooleanSensor(self, sensorConfiguration)
        elif hwConfig.doesSensorInherit(sensorConfiguration, configuration.Sensor.Type.FLOAT):
            return sensor.FloatSensor(self, sensorConfiguration)
        else:
            raise Exception('Unable to instanciate sensor of type {0}'.format(sensorConfiguration.type))

    @property
    def modeValue(self):
        return self._modeValueObject.value

    @property
    def modeValueObject(self):
        return self._modeValueObject

    # @property
    # def motionConfigDir(self):
        # return self._config.servicesRepository.motion.configDirectory

    # @property
    # def motionOutputDir(self):
        # return self._config.servicesRepository.motion.outputDirectory

    @property
    def currentMode(self):
        return self._currentMode

    @currentMode.setter
    def currentMode(self, value):
        self.modeValueObject.value = self.getMode(value).value

    # def getInhibitedAlertTypes(self):
        # types = set()
        # if self._isIntrusionAlertInhibitedObject.value:
            # types.add(Daemon.INTRUSION)
        # if self._isFireAlertInhibitedObject.value:
            # types.add(Daemon.FIRE)
        # return types

    # def isAlertInhibited(self, alertType):
        # if alertType == Daemon.INTRUSION:
            # return self._isIntrusionAlertInhibitedObject.value
        # elif alertType == Daemon.FIRE:
            # return self._isFireAlertInhibitedObject.value
        # else:
            # return False

    # def _addSensor(self, sensor):
        # sensorId = (sensor.name, sensor.type)
        # if self._sensors.has_key(sensorId):
            # raise Exception('A sensor named {0} already exist.'.format(sensor.name))
        # self._sensors[sensorId] = sensor

    def getAlertByPersistenceObjectId(self, objectId):
        for alert in self.alerts:
            if alert.persistenceObjectId == objectId: return alert

        raise Exception('No alert whose persistent object is {0}.'.format(objectId))

    def getAlertByInhibitionObjectId(self, objectId):
        for alert in self.alerts:
            if alert.inhibitionObjectId == objectId: return alert

        raise Exception('No alert whose inhibition object is {0}.'.format(objectId))

    def onPersistentAlertChanged(self, persistentObject):
        logger.reportDebug('onPersistentAlertChanged {0}={1}'.format(persistentObject.id, persistentObject.value))

        # Do nothing when persistent alert becomes true.
        if persistentObject.value: return

        # Reset persistence of sensors that belong to this alert type.
        deactivatedAlert = self.getAlertByPersistenceObjectId(persistentObject.id)

        # Not found.
        if deactivatedAlert is None:
            raise Exception('Persistent alert object does not match any alert type.')

        deactivatedAlert.stop()

        # Reset persistent alert for all sensors.
        for sensor in [s for s in self.sensors if s.alert == deactivatedAlert]:
            if sensor.persistenceObject != None: sensor.persistenceObject.value = False

    @property
    def sensors(self):
        return self._sensors.values()

    @property
    def sensorsInAlert(self):
        return [s for s in self.sensors if s.isEnabled and s.isAlertActive]

    @property
    def alerts(self):
        return self._alerts.values()

    def getAlertByName(self, name):
        return self._alerts[name]

    def getSensorByName(self, sensorName):
        return self._sensors[sensorName]

    def notifyWatchedObjectChanged(self, objectId):
        """ Notifies the daemon that one of its sensors' watched objects has just changed. """
        # Search for related sensors.
        relatedSensors = []
        for sensor in self.sensors:
            if sensor.watchedObjectId == objectId:
                relatedSensors.append(sensor)

        if not relatedSensors:
            raise Exception('No sensor watches the object {0}.'.format(objectId))

        # Notify sensors.
        for sensor in relatedSensors:
            sensor.notifyWatchedObjectChanged()

    # def findSensorByTemperatureObjectId(self, objectId):
        # """ Get a temperature probe identified by its temperature object id. """
        # for s in self.sensors:
            # if s.type != SensorType.TEMPERATURE_PROBE: continue
            # if s.temperatureObject.id == objectId: return s
        # raise Exception('No sensor uses the object {0} as temperature object.'.format(objectId))

    def terminate(self):
        logger.reportInfo('Terminating homewatcher daemon...')
        self._isTerminated = True
        self.disableAllSensors()
        # if self._ftpBackupThread != None: self._ftpBackupThread.stop()

    def disableAllSensors(self):
        for sensor in self.sensors:
            sensor.isEnabled = False

    # def updateAlertStatus(self):
        # try:
            # logger.reportDebug('Waiting for lock...')
            # self._lock.acquire()
            # logger.reportDebug('Lock acquired!')
            # logger.reportDebug('Updating alert status...')
# 
            # # Gather alerts that should be currently active.
            # activeAlerts = set()
            # for sensor in self.sensors:
                # if sensor.isAlertActive:
                    # activeAlerts.add(sensor.alert)
# 
            # # Update each alert's status.
            # for alert in self.alerts:
                # alert.fire()
# 
        # finally:
            # self._lock.release()
            # logger.reportDebug('Lock released.')

    def onAlertInhibited(self, inhibitionObjectId):
        pass
        # # Identify alert that got inhibited.
        # alert = self.getAlertByInhibitionObjectId(inhibitionObjectId)
# 
        # # Stop alert of all sensors that match this alert.
        # for sensor in self.sensors:
            # if sensor.alert == alert:
                # sensor.setAlertActiveRaw(False)
# 
        # logger.reportDebug('onAlertInhibited, isIntrusionInhibited={0} isFireInhibited={1}'.format(isIntrusionInhibited, isFireInhibited))
# 
        # alert.stop()

    def onModeValueChanged(self, value):
        logger.reportDebug('onModeValueChanged value={0}'.format(value))
        self._updateModeFromLinknx()

    def sendEmail(self, actionXml):
        if self.configuration.servicesRepository.linknx.ignoreEmail:
            return

        self.linknx.executeAction(actionXml)
        # smtpConfig = self.linknx.emailServerInfo
        # if smtpConfig is None:
            # logger.reportError('No emailing capability has been set up for the linknx daemon.')
            # return
# 
        # host, port, fromAddress = smtpConfig
# 
        # msg = MIMEMultipart()
        # msg['From'] = fromAddress
        # msg['To'] = COMMASPACE.join(toAddr)
        # msg['Date'] = formatdate(localtime=True)
        # msg['Subject'] = '{0}'.format(email.header.Header(subject, 'utf-8'))
        # msg.attach( MIMEText(_text=text, _charset='utf-8') )
# 
        # for file in attachments:
            # part = MIMEBase('application', "octet-stream")
            # part.set_payload( open(file,"rb").read() )
            # Encoders.encode_base64(part)
            # part.add_header('Content-Disposition', 'attachment; filename="{0}"'.format(os.path.basename(file)))
            # msg.attach(part)
# 
        # smtp = smtplib.SMTP(host=host, port=port)
        # smtp.sendmail(fromAddress, toAddr, msg.as_string())
        # logger.reportInfo('Email sent to {0} with subject {1} and {2} attachments.'.format(','.join(toAddr), subject, len(attachments)))
        # smtp.close()
# 
    # def _sendModeChangedEmail(self):
        # ignoredSensors = []
        # text = '{0}\nLa maison est maintenant en mode {1}'.format(time.asctime(), self._currentMode)
# 
        # # List sensors that are watched and those that can't be enabled
        # # immediately.
        # if self._currentMode.activeSensorIds:
            # text += '\n\nCapteurs surveillés :'
            # for sensorId in self._currentMode.activeSensorIds:
                # sensor = self.getSensorByName(sensorId[0], sensorId[1])
                # if sensor.canBeEnabled():
                    # if sensor.getActivationDelay() == 0:
                        # stateStr = 'est activé immédiatement'
                    # else:
                        # stateStr = 'sera activé dans {0} secondes'.format(sensor.getActivationDelay())
                # else:
                    # stateStr = 'ignoré tant que {0} retourne False.'.format(sensor.canBeEnabled)
                    # ignoredSensors.append(sensor)
                # text += '\n-{0} ({1}): {2}'.format(sensor, sensor.type, stateStr)
        # else:
            # text += '\n\nAucun capteur n\'est associé à ce mode.'
# 
        # # List all sensors that are currently triggered (even if they do not
        # # participate in the current mode.
        # triggeredSensorNotices = []
        # for sensor in self.sensors:
            # if sensor.isTriggered:
                # triggeredSensorNotices.append('-{0} ({1})'.format(sensor.name, sensor.type))
        # if triggeredSensorNotices:
            # text += '\n\nListe des capteurs actuellement déclenchés :\n'
            # text += '\n'.join(triggeredSensorNotices)
# 
        # subject='Nouveau mode : {0}'.format(self._currentMode)
        # if ignoredSensors:
            # subject += ' sans [' + (','.join([s.description for s in ignoredSensors])) + ']'
        # self.sendEmail(toAddr=self._infoAddresses, subject=subject, text=text)

    def _updateModeFromLinknx(self):
        """ Update integral mode to reflect the current mode in linknx.
        """
        with self.suspendAlertStatusUpdates():
            modeValue = self.modeValue
            newMode = self.getMode(modeValue)

            if self._isTerminated:
                self.disableAllSensors()
                return

            # Notify mode change.
            hasModeChanged = self._currentMode == None or self._currentMode != newMode
            if not hasModeChanged:
                self._currentMode = newMode
                return

            # Mode left event.
            if self._currentMode != None:
                self._currentMode.notifyLeft()
            self._currentMode = newMode
            logger.reportInfo('Current alarm mode is now {0}'.format(self._currentMode))

            # Update sensors enabled state.
            for sensor in self.sensors:
                if sensor.isRequiredByCurrentMode():
                    if not sensor.isEnabled:
                        sensor.startActivationTimer()
                else:
                    sensor.stopActivationTimer() # Issue 23: to help prevent data race with the activation timer.
                    sensor.isEnabled = False
            
            # Mode entered event.
            if self._currentMode != None:
                self._currentMode.notifyEntered()

