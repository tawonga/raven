#!/usr/bin/python
# -*- coding: utf-8 -*-

from ConfigParser import SafeConfigParser
import multiprocessing
from optparse import OptionParser
import ravenlogger
import raventracer

import sys


from deluge.log import setupLogger

setupLogger()

MODULE = "raven"
VERSION = "v0.0.2"


class CommandLineParser(object):
    def __init__(self):
        self.options = None
        self.args = None
        self.parser = OptionParser()
        self.parser.add_option("-c", "--config", dest="cfgfile", default="raven.cfg", type="string", metavar="FILE",
                               help=u"Configuration filename. Defaults to raven.cfg")
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
        print "configuration file: {}".format(self.options.cfgfile)
        return

    def print_help(self):
        return self.parser.print_help()


class CfgParser(object):
    def __init__(self, cfg_filename):
        self.server_config = {}
        self.db_config = {}
        self.cfg = SafeConfigParser()
        cfg_found = self.cfg.read(cfg_filename)
        if len(cfg_found) > 0:
            self.sections = self.cfg.sections()
        else:
            print "no configuration file found. falling back to defaults"

    def get_raven_usb_config(self):
        server_config = {opt: value for (opt, value) in self.cfg.items("raven")} if 'raven' in self.sections else {}
        server_config["baudrate"] = int(server_config["baudrate"]) if 'baudrate' in server_config.keys() else 115200
        return server_config

    def get_database_config(self):
        db_config = {opt: value for (opt, value) in self.cfg.items("database")} if 'database' in self.sections else {}
        return db_config


def scan_and_record(raven_usb_config, db_config):

    q = multiprocessing.Queue()

    recorder = ravenlogger.RavenRecorder(db_config, raven_usb_config, q)
    recorder.start()

    tracer = raventracer.RavenTracer(raven_usb_config, q, 60)
    tracer.start()

    recorder.join()
    return

def main():
    parser = CommandLineParser()
    (options, args) = parser.parse_args()
    if options.version:
        print "{module} {version}".format(module=MODULE, version=VERSION)
    if options.verbose:
        parser.state_args()

    cfg = CfgParser(options.cfgfile)
    raven_usb_config = cfg.get_raven_usb_config()
    if len(raven_usb_config) < 1:
        print "no Deluge server configurations in configuration file: {file}".format(file=options.cfgfile)
        sys.exit()

    db_config = cfg.get_database_config()
    if len(db_config) < 1:
        print "no database configuration in config file: {file}".format(file=options.cfgfile)
        sys.exit()

    scan_and_record(raven_usb_config, db_config)


if __name__ == '__main__':
    main()
    sys.exit()
