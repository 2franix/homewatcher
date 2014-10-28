import homewatcher.plugin
import homewatcher.alarm
import homewatcher.contexthandlers
from pyknx import logger

class SensorsStatusContextHandler(homewatcher.contexthandlers.ContextHandler):
    __contextHandlerName__ = 'alert.sensors-status'
    def __init__(self, xmlConfig):
        homewatcher.contexthandlers.ContextHandler.__init__(self, xmlConfig)

    def analyzeContext(self, context):
        message = ""
        if isinstance(context, homewatcher.alarm.Alert):
            for header, sensorCollection in (('Sensors in prealert', list(context.sensorsInPrealert)), ('Sensors in alert', list(context.sensorsInAlert)), ('Sensors paused', context.pausedSensors)):
                if not sensorCollection: continue
                sensorCollection.sort(key=lambda sensor: sensor.name)
                message += '{header}:\n-{sensors}'.format(header=header, sensors='\n-'.join([str(s) for s in sensorCollection]))

        return message

class EnabledSensorsContextHandler(homewatcher.contexthandlers.ContextHandler):
    __contextHandlerName__ = 'mode.enabled-sensors'
    def __init__(self, xmlConfig):
        homewatcher.contexthandlers.ContextHandler.__init__(self, xmlConfig)

    def analyzeContext(self, context):
        message = ""

        enabledSensors = [s for s in context.daemon.sensors if s.isEnabled]
        if enabledSensors:
            enabledSensors.sort(key=lambda sensor: sensor.name)
            message += '-{0}'.format('\n-'.join([str(s) for s in enabledSensors]))

        return message

class CurrentModeContextHandler(homewatcher.contexthandlers.ContextHandler):
    __contextHandlerName__ = 'mode.current'
    def __init__(self, xmlConfig):
        homewatcher.contexthandlers.ContextHandler.__init__(self, xmlConfig)

    def analyzeContext(self, context):
        return context.daemon.currentMode.name

class CorePlugin(homewatcher.plugin.Plugin):
    """
    Core plugin that is part of the standard homewatcher package.

    It provides core functionality such as basic context handlers.
    """
    def load(self):
        contextHandlerFactory = homewatcher.contexthandlers.ContextHandlerFactory.getInstance()
        contextHandlerFactory.registerHandler(SensorsStatusContextHandler)
        contextHandlerFactory.registerHandler(EnabledSensorsContextHandler)
        contextHandlerFactory.registerHandler(CurrentModeContextHandler)
