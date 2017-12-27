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

class ContextHandler(object):
    __contextHandlerName__ = None

    def __init__(self, xmlConfig):
        self.xmlConfig = xmlConfig

    def analyzeContext(self, context):
        pass

class ContextHandlerFactory(object):
    _INSTANCE = None

    def __init__(self):
        self._handlerDefinitions = {} # Handler name as key, a JSON describing the handler as value.

    @staticmethod
    def getInstance():
        if ContextHandlerFactory._INSTANCE == None:
            ContextHandlerFactory._INSTANCE = ContextHandlerFactory()
        return ContextHandlerFactory._INSTANCE

    def registerHandler(self, handlerClass):
        self._handlerDefinitions[handlerClass.__contextHandlerName__] = handlerClass

    def makeHandler(self, handlerXMLConfig):
        handlerName = handlerXMLConfig.getAttribute('type')
        if not handlerName in self._handlerDefinitions:
           raise Exception('No context handler named {0} is registered.'.format(handlerName)) 
        handler = self._handlerDefinitions[handlerName](handlerXMLConfig)
        return handler
