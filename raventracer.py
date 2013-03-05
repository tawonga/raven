#!/usr/bin/python
# -*- coding: utf-8 -*

__author__ = 'ray'

import datetime
import serial
import enhancedserial
import xml.etree.ElementTree
import multiprocessing


class RavenPort(object):
    def __init__(self, raven_config):
        try:
            self.ser = enhancedserial.Serial(port=raven_config["port"],
                                             baudrate=raven_config["baudrate"],
                                             timeout=20)
        except serial.SerialException as err:
            raise

    def is_header(self, tag):
        return True if (tag[:1] == "<" and not tag [1:2] == "/") else False

    def is_trailer(self, tag):
        return True if tag[:2] == "</" else False

    def read_clean(self):
        line = self.ser.readline().decode("UTF-8", "ignore")
        return line

    def read(self):
        try:
            line = self.read_clean()
            while not self.is_header(line):
                line = self.read_clean()
            buffer = ''
            while not self.is_trailer(line):
                buffer += line
                line = self.read_clean()
            buffer += line
            return buffer
        except:
            raise


class Raven(object):
    def __init__(self, raven_config):
        self.raven_port = RavenPort(raven_config)
        self.msg_handler = {'InstantaneousDemand'       : self.handle_instantaneous_demand_xml_msg,
                            'CurrentSummationDelivered' : self.handle_current_summation_delivered_xml_msg,
                            'ConnectionStatus'          : self.handle_connection_status_xml_msg,
                            'TimeCluster'               : self.handle_time_cluster_xml_msg}
        self.skip_message = {"type" : "skip"}
        self.stop_message = {"type" : "stop"}
        self.raw_xml_msg = ''

    def calc_date(self, secs_since_epoch):
        base = datetime.datetime(year=2000, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        since = datetime.timedelta(seconds=int(secs_since_epoch,16))
        return base + since


    def derive_mac_address(self, raw_mac_address):
        mac_address = raw_mac_address[0:2]
        for i in range(1, 6):
            mac_address  += ":" + raw_mac_address[2*i:(2*i)+2]
        return mac_address

    def handle_instantaneous_demand_xml_msg(self, stanza):
        msg = {"type" : '0',
               "msg_time"                : self.calc_date(stanza.find("TimeStamp").text),
               "msg_value"               : int(stanza.find("Demand").text, 16),
               "raven_mac_address"       : self.derive_mac_address(stanza.find("DeviceMacId").text[6:]),
               "smartmeter_mac_address"  : self.derive_mac_address(stanza.find("MeterMacId").text[6:])}
        return msg

    def handle_current_summation_delivered_xml_msg(self, stanza):
        msg = {"type" : '1',
               "msg_time"                : self.calc_date(stanza.find("TimeStamp").text),
               "msg_value"               : int(stanza.find("SummationDelivered").text, 16),
               "raven_mac_address"       : self.derive_mac_address(stanza.find("DeviceMacId").text[6:]),
               "smartmeter_mac_address"  : self.derive_mac_address(stanza.find("MeterMacId").text[6:])}
        return msg

    def handle_time_cluster_xml_msg(self, stanza):
        msg = {"type" : '2',
               "utc_time"      : self.calc_date(stanza.find("UTCTime").text),
               "local_time"    : self.calc_date(stanza.find("LocalTime").text)}
        return msg

    def handle_connection_status_xml_msg(self, stanza):
        msg = {"type" : '3',
               "status"        : stanza.find("Status").text + ":" + stanza.find("Description").text,
               "channel"       : int(stanza.find("Channel").text),
               "link_strength" : int(stanza.find("LinkStrength").text, 16)}
        return msg

    def read(self):
        try:
            self.raw_xml_msg = self.raven_port.read()
            stanza = xml.etree.ElementTree.fromstring(self.raw_xml_msg)
            if stanza.tag in self.msg_handler.keys():
                parsed_msg = self.msg_handler[stanza.tag](stanza)
                return parsed_msg
            else:
                print "unexpected message type"
                return self.skip_message
        except xml.etree.ElementTree.ParseError as err:
            print "parse error - probably corrupt message - skipping"
            print self.raw_xml_msg
            return self.skip_message

    def display(self):
        pass


class RavenTracer(multiprocessing.Process):
    def __init__(self, raven_config, q, stop_request):
        multiprocessing.Process.__init__(self)
        self.raven_config = raven_config
        self.q = q
        self.stop_request = stop_request
        self.r = Raven(self.raven_config)

    def run(self):
        while not self.stop_request.is_set():
            msg = self.r.read()
            self.q.put(msg)
            print msg
        else:
            self.q.put({"type" : "stop"})
        return

