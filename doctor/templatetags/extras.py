import math
#from datetime import datetime
from django import template

register = template.Library()

@register.filter
def secToDuration(value, arg = ''):
    """ Seconds-to-Duration Template Tag
    Usage: {{ VALUE|sectodur }}
    """
    secs = int(value)
    daySecs = 86400
    hourSecs = 3600
    minSecs = 60
    days = int(math.floor(secs / int(daySecs)))
    secs = secs - (days * int(daySecs))
    hours = int(math.floor(secs / int(hourSecs)))
    secs = secs - (hours * int(hourSecs))
    minutes = int(math.floor(secs / int(minSecs)))
    secs = secs - (minutes * int(minSecs))
    seconds = secs
    return "%d / %02d:%02d:%02d" % (days, hours, minutes, seconds)

@register.filter
def utcToLocal(value, arg = ''):
    """ UTC to localtime Template Tag
    Usage: {{ DT|utcToLocal }}
    """
    
    secs = int(value)
    daySecs = 86400
    hourSecs = 3600
    minSecs = 60
    days = int(math.floor(secs / int(daySecs)))
    secs = secs - (days * int(daySecs))
    hours = int(math.floor(secs / int(hourSecs)))
    secs = secs - (hours * int(hourSecs))
    minutes = int(math.floor(secs / int(minSecs)))
    secs = secs - (minutes * int(minSecs))
    seconds = secs
    return "%d / %02d:%02d:%02d" % (days, hours, minutes, seconds)
