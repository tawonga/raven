#!/usr/bin/python
# -*- coding: utf-8 -*-

from ConfigParser import SafeConfigParser
import multiprocessing
from optparse import OptionParser
import re
import ravenlogger
import raventracer
import serial.tools.list_ports_posix
import time
import sys


MODULE = "raven"
VERSION = "v0.0.2"


class CommandLineParser(object):
    def __init__(self):
        self.options = None
        self.args = None
        self.parser = OptionParser()
        self.parser.add_option("-c", "--config", dest="configuration_file", default="raven.cfg", type="string",
                               metavar="FILE", help=u"Configuration filename. Defaults to raven.cfg")
        self.parser.add_option("-v", "--verbose", dest="verbose", default=False, action="store_true",
                               help=u"Request verbose output")
        self.parser.add_option("-V", "--version", dest="version", default=False, action="store_true",
                               help=u"Displays the version of the script.")

    def parse_args(self):
        (options, args) = self.parser.parse_args()
        self.options = options
        self.args = args
        return options, args

    def state_args(self):
        print "configuration file: {}".format(self.options.configuration_file)
        return

    def print_help(self):
        return self.parser.print_help()


class CfgParser(object):
    def __init__(self, configuration_filename):
        self.server_config = {}
        self.db_config = {}
        self.cfg = SafeConfigParser()
        cfg_found = self.cfg.read(configuration_filename)
        if len(cfg_found) > 0:
            self.sections = self.cfg.sections()
        else:
            print "no configuration file found. falling back to defaults"

    def get_raven_usb_config(self):
        raven_config = {opt: value for (opt, value) in self.cfg.items("raven")} if 'raven' in self.sections else {}
        if "port" in raven_config.keys():
            raven_config["baudrate"] = int(raven_config["baudrate"]) if 'baudrate' in raven_config.keys() else 115200
        else:
            raven_config = {}
        return raven_config

    def get_database_config(self):
        db_config = {opt: value for (opt, value) in self.cfg.items("database")} if 'database' in self.sections else {}
        return db_config

    def auto_find_raven_usb_config(self):
        ports = [port for (port, desc, id) in serial.tools.list_ports_posix.comports() if re.search("0403:8a28", id)]
        return  {"port" : ports[0], "baudrate" : 115200} if len(ports) == 1 else {}


def scan_and_record(raven_usb_config, db_config):

    q = multiprocessing.Queue()

    recorder = ravenlogger.RavenRecorder(db_config, raven_usb_config, q)
    recorder.start()

    tracer = raventracer.RavenTracer(raven_usb_config, q, 20)
    tracer.start()

    stop_request = multiprocessing.Event()
    stop_request.clear()

    tracer = raventracer.RavenTracer(raven_usb_config, q, stop_request)
    tracer.start()

    time.sleep(20)
    stop_request.set()

    recorder.join()
    return

def main():
    parser = CommandLineParser()
    (options, args) = parser.parse_args()
    if options.version:
        print "{module} {version}".format(module=MODULE, version=VERSION)
    if options.verbose:
        parser.state_args()

    cfg = CfgParser(options.configuration_file)

    raven_usb_config = cfg.get_raven_usb_config()
    if len(raven_usb_config) < 1:
        raven_usb_config = cfg.auto_find_raven_usb_config()
        if len(raven_usb_config) < 1:
            print "no raven in configuration file: {file} and cannot auto find".format(file=options.configuration_file)
            sys.exit()

    db_config = cfg.get_database_config()
    if len(db_config) < 1:
        print "no database configuration in config file: {file}".format(file=options.configuration_file)
        sys.exit()

    scan_and_record(raven_usb_config, db_config)


if __name__ == '__main__':
    main()
    sys.exit()
