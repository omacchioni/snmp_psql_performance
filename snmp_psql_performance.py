#!/usr/bin/python -u
# -*- coding:Utf-8 -*-
# Option -u is needed for communication with snmpd

# Copyright 2014 Olivier Macchioni <olivier.macchioni@wingo.ch>
# based on snmp_xen.py, from cxm - Clustered Xen Management API and tools by Nicolas AGIUS

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import syslog
import sys
import time
import errno

import psycopg2
import snmp_passpersist as snmp
import argparse


# General stuff
POOLING_INTERVAL = 10                     # Update timer, in second
MAX_RETRY = 10                            # Number of successives retry in case of error
OID_BASE = ".1.3.6.1.4.1.42916"           # Sorry Alexey Grenev, I'll ask an own enterprise OID someday
MAX_COUNTER = 2 ^ 32                      # Maximum value for a SNMP "Counter" (32 bits) + 1

# Globals vars
pp = None
args = None


"""
 Map of snmp_psql_performance MIB :

+--psql_cluster(1)
   +--psql_cluster_statistics(1) (based on http://www.postgresql.org/docs/9.2/static/monitoring-stats.html#PG-STAT-DATABASE-VIEW)
      +-- psql_cluster_statistics_database
          +--+ datid(1)
                 OCTET STRING
                 OID of a database
             + datname(2)
                 OCTET STRING
                 Name of this database
             + numbackends(3)
                 Gauge
                 Number of backends currently connected to this database. This is the only column in this view that returns a value reflecting current state; all other columns return the accumulated values since the last reset.
             + xact_commit(4)
                 Counter
                 Number of transactions in this database that have been committed
             + xact_rollback(5)
                 Counter
                 Number of transactions in this database that have been rolled back
             + blks_read(6)
                 Counter
                 Number of disk blocks read in this database
             + blks_hit(7)
                 Counter
                 Number of times disk blocks were found already in the buffer cache, so that a read was not necessary (this only includes hits in the PostgreSQL buffer cache, not the operating system's file system cache)
             + tup_returned(8)
                 Counter
                 Number of rows returned by queries in this database
             + tup_fetched(9)
                 Counter
                 Number of rows fetched by queries in this database
             + tup_inserted(10)
                 Counter
                 Number of rows inserted by queries in this database
             + tup_updated(11)
                 Counter
                 Number of rows updated by queries in this database
             + tup_deleted(12)
                 Counter
                 Number of rows deleted by queries in this database
             + conflicts(13)
                 Counter
                 Number of queries canceled due to conflicts with recovery in this database. (Conflicts occur only on standby servers; see pg_stat_database_conflicts for details.)
             + temp_files(14)
                 Counter
                 Number of temporary files created by queries in this database. All temporary files are counted, regardless of why the temporary file was created (e.g., sorting or hashing), and regardless of the log_temp_files setting.
             + temp_bytes(15)
                 Counter
                 Total amount of data written to temporary files by queries in this database. All temporary files are counted, regardless of why the temporary file was created, and regardless of the log_temp_files setting.
             + deadlocks(16)
                 Counter
                 Number of deadlocks detected in this database
             + blk_read_time(17)
                 TimeTicks (converted from native milliseconds to hundredths of a second)
                 Time spent reading data file blocks by backends in this database, in milliseconds
             + blk_write_time(18)
                 TimeTicks (converted from native milliseconds to hundredths of a second)
                 Time spent writing data file blocks by backends in this database, in milliseconds
             + stats_reset(19)
                 TimeTicks (converted from native time to hundredths of a second)
                 Time at which these statistics were last reset

Shell command to walk through this tree :
    snmpwalk -Cc -v 1 -c netcomm localhost -m all -M/ .1.3.6.1.4.1.42916

"""


def update_data():
    """Update snmp's data from cxm API"""
    global pp
    global node
    global nr_cpu

    conn = psycopg2.connect(
            database=args.database,
            user=args.user,
            password=args.password,
            host=args.host,
            port=args.port,
            )
    cur = conn.cursor()
    sql = """
        SELECT
            datid, datname, numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
            tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted, conflicts,
            COALESCE(EXTRACT(MILLISECONDS FROM NOW()-stats_reset), 0) AS stats_reset
        FROM
            pg_stat_database
        """

    cur.execute(sql)
    for (datid, datname, numbackends, xact_commit, xact_rollback, blks_read, blks_hit,
            tup_returned, tup_fetched, tup_inserted, tup_updated, tup_deleted, conflicts,
            stats_reset) in cur.fetchall():

        oid = '1.1.%d.%%d' % datid

        pp.add_str(oid % 1, datid)
        pp.add_str(oid % 2, datname)
        pp.add_gau(oid % 3, numbackends)
        pp.add_cnt_32bit(oid % 4, xact_commit % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 5, xact_rollback % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 6, blks_read % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 7, blks_hit % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 8, tup_returned % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 9, tup_fetched % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 10, tup_inserted % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 11, tup_updated % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 12, tup_deleted % MAX_COUNTER)
        pp.add_cnt_32bit(oid % 13, conflicts % MAX_COUNTER)
        # Those are not available in 9.1.9
        #pp.add_cnt_32bit(oid % 14, temp_files % MAX_COUNTER)
        #pp.add_cnt_32bit(oid % 15, temp_bytes % MAX_COUNTER)
        #pp.add_cnt_32bit(oid % 16, deadlocks % MAX_COUNTER)
        #pp.add_tt(oid % 17, int(blk_read_time*10) % MAX_COUNTER)
        #pp.add_tt(oid % 18, int(blk_write_time*10) % MAX_COUNTER)
        pp.add_tt(oid % 19, int(stats_reset * 10) % MAX_COUNTER)        # ms -> cs

    cur.close()
    conn.close()


def main():
    """Feed the snmp_xen MIB tree and start listening for snmp's passpersist"""
    global pp

    syslog.openlog(sys.argv[0], syslog.LOG_PID)

    retry_timestamp = int(time.time())
    retry_counter = MAX_RETRY
    while retry_counter > 0:
        try:
            syslog.syslog(syslog.LOG_INFO, "Starting PostgreSQL Performance gathering...")

            # Load helpers
            pp = snmp.PassPersist(OID_BASE)
            pp.start(update_data, POOLING_INTERVAL)     # Should'nt return (except if updater thread has died)

        except KeyboardInterrupt:
            print "Exiting on user request."
            sys.exit(0)
        except IOError, e:
            if e.errno == errno.EPIPE:
                syslog.syslog(syslog.LOG_INFO, "Snmpd had close the pipe, exiting...")
                sys.exit(0)
            else:
                syslog.syslog(syslog.LOG_WARNING, "Updater thread has died: IOError: %s" % (e))
        except Exception, e:
            syslog.syslog(syslog.LOG_WARNING, "Main thread has died: %s: %s" % (e.__class__.__name__, e))
        else:
            syslog.syslog(syslog.LOG_WARNING, "Updater thread as died: %s" % (pp.error))

        syslog.syslog(syslog.LOG_WARNING, "Restarting monitoring in 15 sec...")
        time.sleep(15)

        # Errors frequency detection
        now = int(time.time())
        if (now - 3600) > retry_timestamp:                # If the previous error is older than 1H
            retry_counter = MAX_RETRY                     # Reset the counter
        else:
            retry_counter -= 1                            # Else countdown
        retry_timestamp = now

    syslog.syslog(syslog.LOG_ERR, "Too many retry, aborting... Please check if PostgreSQL is running and if the permissions are OK!")
    sys.exit(1)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description='SNMP PostgreSQL Performance monitoring.',
        add_help=False,     # -h would conflict with the host declaration bellow
        )
    parser.add_argument(
        '--help',
        action='help',
        help='show this help message and exit')
    # Trying to be compatible with the CLI tool "psql"
    parser.add_argument('-U', '--user', help='DB username', required=True)
    parser.add_argument('-W', '--password', help='DB password', required=True)
    parser.add_argument('-h', '--host', help='DB host', default='localhost')
    parser.add_argument('-d', '--database', help='DB database', default='postgres')
    parser.add_argument('-p', '--port', help='DB port', default=5432)

    args = parser.parse_args()

    main()

# vim: ts=4:sw=4:ai
