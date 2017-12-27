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

from xml.dom.minidom import parse
from pyknx import logger
import pyknx.configurator
from homewatcher import configuration
import sys
import getopt
import codecs
import logging

class Configurator(pyknx.configurator.Configurator):
    class ConfigurationException(Exception):
        def __init__(self, message, hwconfHint=None):
            Exception.__init__(self, message)
            self.hwconfHint = hwconfHint

        def __str__(self):
            if self.hwconfHint != None:
                return Exception.__str__(self) + '\nWhen configuring with hwconf.py, consider using the ' + self.hwconfHint + ' option.'
            else:
                return Exception.__str__(self)

    """ Object able to automatically patch the linknx configuration xml to add python callbacks. """
    def __init__(self, homewatcherConfig, sourceFile, outputFile):
        if homewatcherConfig is None:
            self._homewatcherConfig = configuration.Configuration.parseString(self.readFileFromStdIn())
        elif isinstance(homewatcherConfig, str):
            self._homewatcherConfig = configuration.Configuration.parseFile(homewatcherConfig)
        elif isinstance(homewatcherConfig, configuration.Configuration):
            self._homewatcherConfig = homewatcherConfig
        else:
            raise Exception('Unexpected type of object for configuration {0}. Expected a configuration object, a path to a file or None to read from standard input.'.format(homewatcherConfig))
        self._homewatcherConfig.resolve()

        servicesRepo = self._homewatcherConfig.servicesRepository
        daemonAddress = (servicesRepo.daemon.host, servicesRepo.daemon.port)
        pyknx.configurator.Configurator.__init__(self, sourceFile, outputFile, daemonAddress, 'homewatcher')

    @property
    def callbackAttributeName(self):
        if pyknx.version < pyknx.Version(2, 2, 0):
            # Up to v2.1, the attribute name was hardcoded.
            return 'pyknxcallback'
        else:
            return super().callbackAttributeName

    def addCallbackForObject(self, objectId, callbackName, callbackDestination):
        if objectId == None or objectId == '':
            logger.reportWarning('{0} is not defined, skipping callback.'.format(callbackDestination))
            return

        # Search object in config.
        found = False
        callbackAttributeName = self.callbackAttributeName

        for objectXmlConfig in self.config.getElementsByTagName('object'):
            if objectXmlConfig.getAttribute('id') == objectId:
                if found:
                    raise Exception('Two objects with id {id} found.'.format(id=objectId))
                found = True
                objectXmlConfig.setAttribute(callbackAttributeName, callbackName)
                logger.reportInfo('Added callback {0} for {1}'.format(callbackName, objectId))
        if not found:
            raise Exception('Object {id} not found in linknx configuration'.format(id=objectId))

    def cleanConfig(self):
        callbackAttributeName = self.callbackAttributeName
        for objectXmlConfig in self.config.getElementsByTagName('object'):
            if objectXmlConfig.hasAttribute(callbackAttributeName):
                logger.reportInfo('Removed callback {0} for {1}'.format(objectXmlConfig.getAttribute(callbackAttributeName), objectXmlConfig.getAttribute('id')))
                objectXmlConfig.removeAttribute(callbackAttributeName)
        pyknx.configurator.Configurator.cleanConfig(self)

    def generateConfig(self):
        # Add callback for sensors.
        for sensor in self._homewatcherConfig.sensors:
            self.addCallbackForObject(sensor.watchedObjectId, 'onWatchedObjectChanged', 'Watched object for {0}'.format(sensor))

        # Add callbacks for alerts.
        for alert in self._homewatcherConfig.alerts:
            self.addCallbackForObject(alert.persistenceObjectId, 'onAlertPersistenceObjectChanged', 'Persistence for {0}'.format(alert))
            self.addCallbackForObject(alert.inhibitionObjectId, 'onAlertInhibitionObjectChanged', 'Inhibition for {0}'.format(alert))

        # Add callbacks for modes.
        self.addCallbackForObject(self._homewatcherConfig.modesRepository.objectId, 'onModeObjectChanged', 'Mode object')

        pyknx.configurator.Configurator.generateConfig(self)
