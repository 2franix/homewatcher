#!/usr/bin/python
# coding=utf-8
# User file for linknx communicator.

from pyknx import logger
import alarm
import configuration

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
		raise Exception('The hwconfig argument must be either a string or a homewatcher.configuration.Configuration object.')

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
