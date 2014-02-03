# Introduction

This program allows to export statistics of all the databases of your PostgreSQL
cluster via SNMP. Those statistics can then be easily monitored or graphed via
all the "usual" SNMP-based tools.

The statistics are gathered from the [pg_stat_database](http://www.postgresql.org/docs/9.2/static/monitoring-stats.html#PG-STAT-DATABASE-VIEW)
table, and then exported using NET-SNMP's *pass_persist* directive.

# Installation

The script sould probably be installed on the PostgreSQL server itself (although
it could be running on any server which can connect to the database).

It requires a valid user which can do a select on the pg_stat_database table.

## Prerequisites

Use pip to get the following packages:
* psycopg2
* snmp_passpersist
* argparse

```bash
sudo pip install psycopg2 snmp_passpersist argparse
```

## Checking

Check that the script runs correctly by launching it manually:
```bash
./snmp_psql_performance.py -U USER -W PASSWORD
```

The program should start. By typing `DUMP<CR>`, you should see a long list of OIDS similar to this one:

```
{'1.1.1.1': {'type': 'STRING', 'value': '1'},
 '1.1.1.10': {'type': 'Counter32', 'value': '0'},
 '1.1.1.11': {'type': 'Counter32', 'value': '2'},
 '1.1.1.12': {'type': 'Counter32', 'value': '0'},
 '1.1.1.13': {'type': 'Counter32', 'value': '0'},
 '1.1.1.19': {'type': 'TIMETICKS', 'value': '19'},
 '1.1.1.2': {'type': 'STRING', 'value': 'template1'},
 '1.1.1.3': {'type': 'GAUGE', 'value': '0'},
```

If this doesn't work, check the logs (probably in `/var/log/messages` , depending on your Syslog configuration)

## Configuring NET-SNMP

Add the following line to `/etc/snmp/snmpd.conf`:

```
pass_persist .1.3.6.1.4.1.42916 /path/to/snmp_psql_performance.py -U USER -W PASSWORD
```

And restart snmpd:

```
sudo /etc/init.d/snmpd restart
```

Check the outcome by doing a direct SNMP request:

```
snmpwalk -Cc -v 1 -c public localhost .1.3.6.1.4.1.42916
```

You should see something similar to this:
```
iso.3.6.1.4.1.42916.1.1.1.1 = STRING: "1"
iso.3.6.1.4.1.42916.1.1.1.2 = STRING: "template1"
iso.3.6.1.4.1.42916.1.1.1.3 = Gauge32: 0
iso.3.6.1.4.1.42916.1.1.1.4 = Counter32: 33
iso.3.6.1.4.1.42916.1.1.1.5 = Counter32: 2
iso.3.6.1.4.1.42916.1.1.1.6 = Counter32: 10
iso.3.6.1.4.1.42916.1.1.1.7 = Counter32: 7
iso.3.6.1.4.1.42916.1.1.1.8 = Counter32: 28
iso.3.6.1.4.1.42916.1.1.1.9 = Counter32: 21
iso.3.6.1.4.1.42916.1.1.1.10 = Counter32: 0
iso.3.6.1.4.1.42916.1.1.1.11 = Counter32: 2
```

The list of OIDs returned is described at the beginning of the source code of the file.

# TODO

* Be compatible with all versions of PostgreSQL (the content of pg_stat_database is not always the same)
* Get an own OID identifier
* Export more data ?
* Write the MIB file to make the SNMP output nicer to read
