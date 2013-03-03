#!/usr/bin/python
# -*- coding: utf-8 -*

__author__ = 'ray'

import psycopg2
import psycopg2.extras


class SmartMeterException(Exception):
    pass


class SmartMeterError(SmartMeterException):
    pass


class SmartMeterMgr(object):
    def __init__(self, db):
        self.db = db
        try:
            self.cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        except psycopg2.Error as err:
            print "Error initialising real dict cursor in SmartMeterMgr - {code} error {error}".format(code=err.pgcode,
                                                                                                    error=err.pgerror)
            raise SmartMeterError()
        self.cached = False
        self.cache = []
        self.cached_smartmeters = []
        self.col_names = ["mac_address", "nick"]

    def is_known(self, mac_address):
        """Do we have a record of the smartmeter in the postgresql database?
        """
        sel = """SELECT mac_address
                 FROM smartmeters
                 WHERE mac_address = %(mac_address)s"""
        try:
            self.cur.execute(sel, { "mac_address" : mac_address})
            return True if not self.cur.fetchone() is None else False
        except psycopg2.Error as err:
            print "Error checking for smart meter existence - {code} error {error}".format(code=err.pgcode,
                                                                                          error=err.pgerror)
            raise SmartMeterError()

    def cache_smartmeters(self):
        sel = "SELECT nick, mac_address FROM smartmeters"
        try:
            self.cur.execute(sel)
            self.cache = self.cur.fetchall()
        except psycopg2.Error as err:
            print "Error caching smart meters - {code} error {error}".format(code=err.pgcode,
                                                                             error=err.pgerror)
            raise SmartMeterError()

    def add_smartmeter(self, smartmeter):
        ins = """INSERT INTO smartmeters (nick, mac_address)
                                  VALUES (%(nick)s, %(mac_address)s)"""
        try:
            self.cur.execute(ins, smartmeter)
            return
        except psycopg2.Error as err:
            print "Error inserting smartmeter - {code} error {error}".format(code=err.pgcode,
                                                                             error=err.pgerror)
            raise SmartMeterError()

    def update_smartmeter(self, smartmeter):
        upd = """UPDATE smartmeters
                 SET (nick,
                      mac_address)
                   =
                     (%(nick)s,
                      %(mac_address)s)
                 WHERE mac_address = %(mac_address)s"""
        try:
            self.cur.execute(upd, smartmeter)
            return
        except psycopg2.Error as err:
            print "Error updating smartmeter - {code} error {error}".format(code=err.pgcode,
                                                                            error=err.pgerror)
            raise SmartMeterError()
