#!/usr/bin/python
# -*- coding: utf-8 -*

__author__ = 'ray'

import psycopg2
import psycopg2.extras
import multiprocessing
import raven
import smartmeter
import Queue

class RavenLoggerException(Exception):
    pass


class RavenLoggerError(RavenLoggerException):
    pass


class RavenLogger(object):
    def __init__(self, db_cfg):
        try:
            self.db = psycopg2.connect(host=db_cfg["host"],
                                       port=db_cfg["port"],
                                       database=db_cfg["database"],
                                       user=db_cfg["user"],
                                       password=db_cfg["password"])
            self.cur = self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        except psycopg2.Error as err:
            print "Error opening postgresql database - {code} error {error}".format(code=err.pgcode,
                                                                                    error=err.pgerror)
            raise RavenLoggerError()

        self.trace_id = None
        self.raven_mac_address = None
        self.smartmeter_mac_address = None
        self.raven = raven.RavenMgr(self.db)
        self.smartmeter = smartmeter.SmartMeterMgr(self.db)

        
    def mark_start(self, raven_mac_address, smartmeter_mac_address):
        start_scan_sql = """INSERT INTO traces (trace_id,
                                                raven_mac_address,
                                                smartmeter_mac_address,
                                                start_time)
                                        VALUES (DEFAULT,
                                                %(raven_mac_address)s,
                                                %(smartmeter_mac_address)s,
                                                'now')"""
        get_serial_sql = """SELECT currval('traces_trace_id_seq')"""
        try:
            self.cur.execute(start_scan_sql, {"raven_mac_address"      : raven_mac_address,
                                              "smartmeter_mac_address" : smartmeter_mac_address})
            self.cur.execute(get_serial_sql)
            self.trace_id = self.cur.fetchone()["currval"]
            self.db.commit()
        except psycopg2.Error as err:
            print "Error marking start of a scan - {code} error {error}".format(code=err.pgcode,
                                                                                error=err.pgerror)
            raise RavenLoggerError()
        return self.trace_id

    def mark_done(self):
        end_scan_sql = """UPDATE traces SET end_time = 'now'
                                        WHERE trace_id = %(trace_id)s"""
        try:
            self.cur.execute(end_scan_sql, {"trace_id" : self.trace_id})
            self.db.commit()
        except psycopg2.Error as err:
            print "Error marking end of a scan - code: {code} error {error}".format(code=err.pgcode,
                                                                                    error=err.pgerror)
            raise RavenLoggerError()
        return

    def log_instant(self, msg):
        ins_instant_sql = """INSERT INTO instants (trace_id,
                                                   read_time,
                                                   read_value)
                                           VALUES (%(trace_id)s,
                                                   %(msg_time)s,
                                                   %(msg_value)s)"""
        try:
            msg["trace_id"] = self.trace_id
            self.cur.execute(ins_instant_sql, msg)
        except psycopg2.Error as err:
            print "Error logging instant reading - {code} error {error}".format(code=err.pgcode,
                                                                                error=err.pgerror)
            raise RavenLoggerError()
        return

    def log_summary(self, msg):
       ins_instant_sql = """INSERT INTO summaries (trace_id,
                                                   read_time,
                                                   read_value)
                                           VALUES (%(trace_id)s,
                                                   %(msg_time)s,
                                                   %(msg_value)s)"""
       try:
           msg["trace_id"] = self.trace_id
           self.cur.execute(ins_instant_sql, msg)
           self.db.commit()
       except psycopg2.Error as err:
           print "Error logging summary - {code} error {error}".format(code=err.pgcode,
                                                                               error=err.pgerror)
           raise RavenLoggerError()
       return

    def register_trace(self, raven_mac_address, smartmeter_mac_address):
        if not self.raven.is_known(raven_mac_address):
            raven_dict = { "mac_address" : raven_mac_address,
                           "nick"        : None}
            self.raven.add_raven(raven_dict)
        if not self.smartmeter.is_known(smartmeter_mac_address):
            smartmeter_dict = { "mac_address" : smartmeter_mac_address,
                                "nick"        : None}
            self.smartmeter.add_smartmeter(smartmeter_dict)
        self.trace_id = self.mark_start(raven_mac_address, smartmeter_mac_address)
        return self.trace_id

    def commit(self):
#todo
        pass

    def close(self):
#todo
        pass


class RavenRecorder(multiprocessing.Process):
    def __init__(self, db_config, raven_config, q):
        super(RavenRecorder, self).__init__()
        self.db_config = db_config
        self.raven_config = raven_config
        self.q = q
        self.raven_logger = RavenLogger(db_config)
        self.q_msg_handler = {'0'      : self.handle_instantaneous_demand_msg,
                              '1'      : self.handle_current_summation_delivered_msg,
                              '2'      : self.handle_connection_status_msg,
                              '3'      : self.handle_time_cluster_msg,
                              'skip'   : self.handle_skip_msg,
                              'stop'   : self.handle_stop_msg}
        self.is_logging = True
        self.trace_registered = False

    def handle_instantaneous_demand_msg(self, q_msg):
        if not self.trace_registered:
            self.raven_logger.register_trace(q_msg["raven_mac_address"], q_msg["smartmeter_mac_address"])
            self.trace_registered = True
        self.raven_logger.log_instant(q_msg)
        return

    def handle_current_summation_delivered_msg(self, q_msg):
        if not self.trace_registered:
            self.raven_logger.register_trace(q_msg["raven_mac_address"], q_msg["smartmeter_mac_address"])
        self.raven_logger.log_summary(q_msg)
        return

    def handle_connection_status_msg(self, q_msg):
        return

    def handle_time_cluster_msg(self, q_msg):
        return

    def handle_skip_msg(self, q_msg):
        return

    def handle_stop_msg(self, q_msg):
        self.is_logging = False
        return

    def run(self):
        while self.is_logging:
            try:
                q_msq = self.q.get(block=True, timeout=60)
                type = q_msq["type"]
                if type in self.q_msg_handler.keys():
                    status = self.q_msg_handler[type](q_msq)
                else:
                    print "unexpected message type"
                    continue
            except Queue.Empty:
                self.is_logging = False
        else:
            self.q.close()
            self.raven_logger.mark_done()
        return

