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

import sys

if sys.version_info.major < 3:
    print('Homewatcher is designed to work with Python 3 or above. Your current version is ' + sys.version)

try:
    import pyknx
except ImportError:
    print('Could not import package "pyknx". Make sure it is installed before continuing. You can install it from PyPI with "pip3 install pyknx"')
    exit(1)

# Even if Pyknx is successfully installed, we have to check that its version is
# >=2 or Homewatcher will not work.
pyknxVersion = None
if hasattr(pyknx, 'version'):
    pyknxVersion = pyknx.version

if pyknxVersion == None:
    print('The installed version of Pyknx is too old to be compatible with Homewatcher. Please upgrade it with, for instance, "pip3 install --pre --upgrade pyknx"')
    exit(2)
