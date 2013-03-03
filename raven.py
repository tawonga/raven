#!/usr/bin/python
# -*- coding: utf-8 -*

__author__ = 'ray'

import psycopg2
import psycopg2.extras

class RavenException(Exception):
    pass


class RavenError(RavenException):
    pass


class RavenMgr(object):
    def __init__(self, db):
        self.db = db
        try:
            self.cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        except psycopg2.Error as err:
            print "Error initialising real dict cursor in RavenMgr - {code} error {error}".format(code=err.pgcode,
                                                                                                       error=err.pgerror)
            raise RavenError()
        self.cached = False
        self.cache = []
        self.cached_ravens = []
        self.col_names = ["mac_address", "nick"]

    def is_known(self, mac_address):
        """Do we have a record of the raven in the postgresql database?
        """
        sel = """SELECT mac_address
                 FROM raven
                 WHERE mac_address = %(mac_address)s"""
        try:
            self.cur.execute(sel, {"mac_address" : mac_address})
            return True if not self.cur.fetchone() is None else False
        except psycopg2.Error as err:
            print "Error checking for raven existence - {code} error {error}".format(code=err.pgcode,
                                                                                           error=err.pgerror)
            raise RavenError()

    def cache_ravens(self):
        """Cache all raven records from the database
        """
        sel = """SELECT nick, mac_address
                 FROM ravens"""
        try:
            self.cur.execute(sel)
            self.cache = self.cur.fetchall()
        except psycopg2.Error as err:
            print "Error caching ravens - {code} error {error}".format(code=err.pgcode,
                                                                             error=err.pgerror)
            raise RavenError()

    def add_raven(self, raven):
        ins = """INSERT INTO raven (nick,
                                     mac_address)
                      VALUES (%(nick)s,
                              %(mac_address)s)"""
        try:
            self.cur.execute(ins, raven)
            return
        except psycopg2.Error as err:
            print "Error inserting raven - {code} error {error}".format(code=err.pgcode,
                                                                             error=err.pgerror)
            raise RavenError()

    def update_raven(self, raven):
        upd = """UPDATE ravens SET (nick,
                                    mac_address)
                                =
                                   (%(nick)s,
                                    %(mac_address)s)
                             WHERE mac_address = %(mac_address)s"""
        try:
            self.cur.execute(upd, raven)
            return
        except psycopg2.Error as err:
            print "Error updating raven - {code} error {error}".format(code=err.pgcode,
                                                                            error=err.pgerror)
            raise RavenError()
