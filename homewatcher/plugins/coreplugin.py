import homewatcher.plugin
from pyknx import logger

class CorePlugin(homewatcher.plugin.Plugin):
    """
    Core plugin that is part of the standard homewatcher package.

    It provides core functionality such as basic context handlers.
    """
    def load(self):
