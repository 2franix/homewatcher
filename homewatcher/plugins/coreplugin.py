import homewatcher.plugin
import homewatcher.alarm
import homewatcher.contexthandlers
from pyknx import logger

class SensorStatusContextHandler(homewatcher.contexthandlers.ContextHandler):
    __contextHandlerName__ = 'sensor-status'
    def __init__(self, xmlConfig):
        contexthandlers.ContextHandler.__init__(self, xmlConfig)

    def analyzeContext(self, context):
        if isinstance(context, homewatcher.alarm.Alert):
            message = ""
            for header, sensorCollection in (('Sensors in prealert', context.sensorsInPrealert), ('Sensors in alert', context.sensorsInAlert), ('Sensors paused', context.sensorsPaused)):
                if not sensorCollection: continue
                message += '{header}:{sensors}'.format(header, '\n-'.join(str(sensorCollection)))
                message += '\n'

class CorePlugin(homewatcher.plugin.Plugin):
    """
    Core plugin that is part of the standard homewatcher package.

    It provides core functionality such as basic context handlers.
    """
    def load(self):
        homewatcher.contexthandlers.ContextHandlerFactory.getInstance().registerHandler(SensorStatusContextHandler)
