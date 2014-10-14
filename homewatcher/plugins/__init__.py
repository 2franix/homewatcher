#!/usr/bin/python3

# Copyright (C) 2012-2014 Cyrille Defranoux
#
# This file is part of Pyknx.
#
# Pyknx is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Pyknx is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pyknx. If not, see <http://www.gnu.org/licenses/>.
#
# For any question, feature requests or bug reports, feel free to contact me at:
# knx at aminate dot net

import os
import glob
import importlib
from pyknx import logger
import homewatcher.plugin
import logging

"""
Homewatcher subpackage that contains the dynamically loaded plugins.
"""

_plugins = []
logger.initLogger(stdoutLogLevel=logging.ERROR)

def loadPlugins():
    global _plugins
    pluginDirectory = os.path.dirname(__file__)

    pluginModules = glob.glob(os.path.join(pluginDirectory, '*.py'))

    # Scan all modules in the 'plugins' subdirectory and instanciate all classes
    # that inherit Plugin.
    for moduleFile in pluginModules:
        if os.path.basename(moduleFile) == '__init__.py': continue
        module = importlib.import_module('homewatcher.plugins.{0}'.format(os.path.splitext(os.path.basename(moduleFile))[0]))
        for symbolName in dir(module):
            symbol = vars(module)[symbolName]
            if isinstance(symbol, type) and issubclass(symbol, homewatcher.plugin.Plugin):
                logger.reportInfo('Loading {0}'.format(symbol))
                plugin = symbol()
                try:
                    plugin.load()
                    logger.reportInfo('{0} loaded.'.format(symbol))
                except Exception as e:
                    logger.reportException('Failed to load plugin {0}'.format(plugin))

loadPlugins()
