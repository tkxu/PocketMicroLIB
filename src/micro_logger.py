"""
File        : micro_logger.py
Description : 
Author      : https://github.com/tkxu/
MicroPython : v1.26
Board       : Raspberry Pi Pico2
Version     : Rev. 0.90  2026-01-01

Copyright 2026 tkxu
License     : MIT License (see LICENSE file)
"""
# micro_logger.py

import utime
import state

LEVEL_DEBUG3 = 0
LEVEL_DEBUG2 = 1
LEVEL_DEBUG = 2
LEVEL_INFO = 3
LEVEL_WARN = 4
LEVEL_ERROR = 5
LEVEL_CRIT = 6


def log_status(msg, level=LEVEL_INFO):
    if level >= state.debug_level:
        if level == LEVEL_DEBUG:
            prefix = "[DEBUG]"
        elif level == LEVEL_DEBUG2:
            prefix = "[DEBUG]"
        elif level == LEVEL_DEBUG3:
            prefix = "[DEBUG]"
        elif level == LEVEL_INFO:
            prefix = "[INFO ]"
        elif level == LEVEL_WARN:
            prefix = "[WARN ]"
        elif level == LEVEL_ERROR:
            prefix = "[ERROR]"
        elif level == LEVEL_CRIT:
            prefix = "[CRITI]"
            
        else:
            prefix = "[LOG　]"
        t = utime.localtime()
        timestamp = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*t[0:6])
        print("{} {} {}".format(prefix, timestamp, msg))
        
#TEST code
if __name__ == "__main__":

    log_status("logger.py test", level=LEVEL_DEBUG3)
    log_status("logger.py test", level=LEVEL_DEBUG2)
    log_status("logger.py test", level=LEVEL_DEBUG)
    log_status("logger.py test", level=LEVEL_INFO)
    log_status("logger.py test", level=LEVEL_WARN)
    log_status("logger.py test", level=LEVEL_ERROR)
    log_status("logger.py test", level=LEVEL_CRIT)

