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
from homewatcher import configuration, alarm

alarmDaemon = None

def initializeUserScript(context):
    global alarmDaemon
    logger.reportInfo('hw config is {0}'.format(context.hwconfig))
    # motionConfigDir = context.customArgs.get('motionconfigdir')
    # motionOutputDir = context.customArgs.get('motionoutputdir')

    if isinstance(context.hwconfig, str):
        config = configuration.Configuration.parseFile(context.hwconfig)
    elif isinstance(context.hwconfig, configuration.Configuration):
        config = context.hwconfig
    else:
        raise Exception('The hwconfig argument must be either a string or a homewatcher.configuration.Configuration object. "{0}" was passed.'.format(type(context.hwconfig)))

    # Instanciate daemon.
    alarmDaemon = alarm.Daemon(context.communicator, config)

def finalizeUserScript(context):
    global alarmDaemon
    if alarmDaemon:
        alarmDaemon.terminate()

def endUserScript(context):
    global alarmDaemon
    alarmDaemon = None

def onModeObjectChanged(context):
    global alarmDaemon
    logger.reportDebug('Alarm mode changed to ' + str(context.object.value))
    alarmDaemon.onModeValueChanged(context.object.value)

def onWatchedObjectChanged(context):
    global alarmDaemon
    sensor = alarmDaemon.notifyWatchedObjectChanged(context.objectId)

def onSirenStatusChanged(context):
    global alarmDaemon
    alarmDaemon.onSirenStatusChanged(context)

def onAlertPersistenceObjectChanged(context):
    global alarmDaemon
    alarmDaemon.onPersistentAlertChanged(context.object)

def onAlertInhibited(context):
    global alarmDaemon
    alarmDaemon.onAlertInhibited(context.objectId)

def onTemperatureChanged(context):
    global alarmDaemon
    sensor = alarmDaemon.findSensorByTemperatureObjectId(context.objectId)
    temp = float(context.object.value)
    if temp < sensor.lowLimit:
        sensor.triggerObject.value = True
    elif temp > sensor.highLimit:
        sensor.triggerObject.value = True
    elif temp < sensor.highLimit - sensor.hysteresis and temp > sensor.lowLimit + sensor.hysteresis:
        sensor.triggerObject.value = False

# def purgeTemporaryFiles(context):
    # global alarmDaemon
    # age = context.getArgument('maxAge', '30')
    # age = int(age)
    # alarmDaemon.purgeTemporaryFiles(age)
