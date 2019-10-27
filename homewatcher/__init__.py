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

from pyknx import Version
import homewatcher.plugins

"""
Homewatcher is a package that provides a daemon that plays the role of centralized home surveillance (the way an alarm system does). It exposes high level capabilities that drastically simplifies
the configuration of the installation compared to one set up entirely with linknx functionality.
"""
__all__ = ['alarm', 'configuration', 'configurator', 'sensor', 'timer']

version = Version(1, 3, 2)
__version__=str(version)

