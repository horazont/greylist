#!/usr/bin/python3
import configparser
import logging
import sqlite3

from datetime import datetime, timedelta

# CONFIGURATION

# See README.md for more details. Use a config file whenever possible instead of
# changing the source code here, to make your own life easier on updates.

db_file = "greylist.db"
auto_whitelist_threshold = 10
greylist_timeout = 60
max_greylist_entries = 100000
max_greylist_entries_per_client_name = 1000
max_whitelist_entries = 1000
greylist_expire = None
whitelist_expire = None
response_pass = "action=dunno\n\n"
response_fail = "action=defer_if_permit You have been greylisted.\n\n"
stats_active_threshold = 3600

# END OF CONFIGURATION

class RESPONSE:
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return self.name

    def __repr__(self):
        return "<response={}>".format(self.name)

PASSED = RESPONSE("PASSED")
FAILED = RESPONSE("FAILED")

del RESPONSE

SCHEMA = {}
SCHEMA[("table", "whitelist")] = """CREATE TABLE whitelist
   (
      id INTEGER PRIMARY KEY,
      client_name TEXT,
      last_seen TIMESTAMP,
      hit_count INTEGER,
      CONSTRAINT client_name UNIQUE (client_name)
   )"""
SCHEMA[("table", "greylist")] = """CREATE TABLE greylist
   (
      id INTEGER PRIMARY KEY,
      client_name TEXT,
      sender TEXT,
      recipient TEXT,
      first_seen TIMESTAMP,
      last_seen TIMESTAMP,
      CONSTRAINT match UNIQUE (client_name, sender, recipient)
  )"""
SCHEMA[("index", "whitelist_last_seen")] = """CREATE INDEX whitelist_last_seen ON greylist (last_seen)"""
SCHEMA[("index", "greylist_last_seen")] = """CREATE INDEX greylist_last_seen ON greylist
(last_seen)"""

_dbconn = None

def clean_request(attrs):
    if "client_name" not in attrs:
        attrs["client_name"] = attrs["client_address"]
    # make sure that critical attributes are in place
    attrs["sender"]
    attrs["recipient"]

def create_db(dbconn):
    logger.info("(re-)creating database")
    tables = ((table, sql)
              for (type_, table), sql in SCHEMA.items()
              if type_ == "table")
    for table, sql in tables:
        logger.info("creating table %s", table)
        dbconn.execute("DROP TABLE IF EXISTS {}".format(table))
        dbconn.execute(sql)
        logger.info("created table %s", table)

    indicies = ((index, sql)
                for (type_, index), sql in SCHEMA.items()
                if type_ == "index")
    for index, sql in indicies:
        logger.info("creating index %s", index)
        dbconn.execute(sql)
        logger.info("created index %s", index)

def get_db():
    global _dbconn
    if _dbconn is None:
        logger.debug("opening database at %s", db_file)
        _dbconn = sqlite3.connect(db_file,
                                  detect_types=sqlite3.PARSE_DECLTYPES)
        setup_db(_dbconn)
    return _dbconn

def getint_or_none(config, section, option, fallback):
    try:
        v = config.get(section, option).lower()
    except configparser.NoOptionError:
        return fallback
    if v in {"none", "off", "disabled"}:
        return None
    return int(v)

def getresponse(config, section, option, fallback):
    try:
        v = config.get(section, option).upper()
    except configparser.NoOptionError:
        return fallback

    try:
        return {
            "PASSED": PASSED,
            "FAILED": FAILED
        }[v]
    except ValueError:
        raise ValueError("Invalid response type: {}".format(v))

def gc_db():
    dbconn = get_db()
    cursor = dbconn.cursor()
    now = datetime.utcnow()
    try:
        if greylist_expire is not None:
            cursor.execute("DELETE FROM greylist WHERE (julianday(?) - julianday(last_seen))*86400.0 >= ?",
                           (now, greylist_expire))
            if cursor.rowcount > 0:
                logger.info("removed %s greylist entries due to expiry",
                             cursor.rowcount)

        if whitelist_expire is not None:
            cursor.execute("""DELETE FROM whitelist
            WHERE (julianday(?) - julianday(last_seen))*86400.0 >= ?""",
                           (now, whitelist_expire))
            if cursor.rowcount > 0:
                logger.info("removed %s whitelist entries due to expiry",
                             cursor.rowcount)

        if dbconn.in_transaction:
            dbconn.commit()

        cursor.execute("SELECT COUNT(*) FROM greylist")
        greylist_count, = cursor.fetchone()

        # only trigger if the limit is set, and either the global limit is unset
        # or it has been surpassed
        if (max_greylist_entries_per_client_name is not None
            and (max_greylist_entries is None
                 or greylist_count > max_greylist_entries)):
            cursor.execute("""SELECT client_name, COUNT(*) as count
            FROM greylist
            GROUP BY client_name
            HAVING count > ?""",
                           (max_greylist_entries_per_client_name,))
            results = list(cursor)
            for client_name, count in results:
                logging.warn("client_name=%r crossed entry limit, count=%s",
                             client_name, count)
                to_purge = count - max_greylist_entries_per_client_name
                cursor.execute("""DELETE FROM greylist
                WHERE id IN (SELECT id FROM greylist
                             WHERE client_name=?
                             ORDER BY last_seen DESC LIMIT ?)""",
                               (client_name, to_purge))
                logger.info("purged %s entries from client_name=%r",
                            cursor.rowcount, client_name)

        if max_greylist_entries is not None:
            cursor.execute("SELECT COUNT(*) FROM greylist")
            count, = cursor.fetchone()
            if count > max_greylist_entries:
                to_purge = count - max_greylist_entries
                logger.info("purging %s entries from greylist (oversized)",
                             to_purge)
                cursor.execute("""DELETE FROM greylist WHERE id IN (
                SELECT id FROM greylist ORDER BY last_seen ASC LIMIT ?)""",
                               (to_purge,))

        if max_whitelist_entries is not None:
            cursor.execute("SELECT COUNT(*) FROM whitelist")
            count, = cursor.fetchone()
            if count > max_whitelist_entries:
                to_purge = count - max_whitelist_entries
                logger.info("purging %s entries from whitelist (oversized)",
                             to_purge)
                cursor.execute("""DELETE FROM whitelist WHERE id IN (
                SELECT id FROM whitelist ORDER BY last_seen ASC LIMIT ?)""",
                               (to_purge,))


        if dbconn.in_transaction:
            dbconn.commit()
    finally:
        if dbconn.in_transaction:
            dbconn.commit()
        cursor.close()

def load_config(f):
    global db_file
    global auto_whitelist_threshold, greylist_timeout, max_greylist_entries
    global max_whitelist_entries, greylist_expire, whitelist_expire
    global stats_active_threshold, response_pass, response_fail
    global max_greylist_entries_per_client_name
    config = configparser.ConfigParser()
    with f as f:
        config.read_file(f)

    db_file = config.get(
        "DEFAULT", "db_file",
        fallback=db_file)

    auto_whitelist_threshold = getint_or_none(
        config,
        "DEFAULT", "auto_whitelist_threshold",
        fallback=auto_whitelist_threshold)

    greylist_timeout = config.getint(
        "DEFAULT", "greylist_timeout",
        fallback=greylist_timeout)

    max_greylist_entries = getint_or_none(
        config,
        "DEFAULT", "max_greylist_entries",
        fallback=max_greylist_entries)

    max_greylist_entries_per_client_name = getint_or_none(
        config,
        "DEFAULT", "max_greylist_entries_per_client_name",
        fallback=max_greylist_entries_per_client_name)

    max_whitelist_entries = getint_or_none(
        config,
        "DEFAULT", "max_whitelist_entries",
        fallback=max_whitelist_entries)

    greylist_expire = getint_or_none(
        config,
        "DEFAULT", "greylist_expire",
        fallback=greylist_expire)

    whitelist_expire = getint_or_none(
        config,
        "DEFAULT", "whitelist_expire",
        fallback=whitelist_expire)

    stats_active_threshold = getint_or_none(
        config,
        "DEFAULT", "stats_active_threshold",
        fallback=stats_active_threshold)

    response_pass = getint_or_none(
        config,
        "DEFAULT", "response_pass",
        fallback=response_pass)

    response_fail = getint_or_none(
        config,
        "DEFAULT", "response_fail",
        fallback=response_fail)

def read_request(instream):
    attrs = {}
    for line in map(str.strip, instream):
        if not line:
            break
        lhs, _, rhs = line.partition("=")
        if not _:
            raise ValueError("Input format violation")
        attrs[lhs] = rhs
    else:
        return None
    return attrs

def _check_whitelist(cursor, client_name):
    if auto_whitelist_threshold is not None:
        cursor.execute("SELECT hit_count FROM whitelist WHERE client_name=?",
                       (client_name,))
        match = cursor.fetchone()
        if match is not None:
            hit_count, = match
            if hit_count >= auto_whitelist_threshold:
                logger.debug("whitelist check: client_name=%r succeeded",
                              client_name)
                return True
    return False

def _check_greylist(dbconn, cursor, sender, recipient, client_name):
    key = sender, recipient, client_name
    now = datetime.utcnow()
    cursor.execute("""SELECT first_seen FROM greylist
    WHERE sender=? AND recipient=? AND client_name=?""",
                   key)

    match = cursor.fetchone()
    if match is None:
        logger.debug("greylist check: no match, creating new entry")
        # no entry yet
        cursor.execute("""INSERT INTO greylist (sender, recipient, client_name,
        first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?)""",
                       key + (now, now))
        cursor.close()
        dbconn.commit()
        return FAILED
    else:
        first_seen, = match
        logger.debug("greylist check: match, first_seen=%s", first_seen)
        delta = now - first_seen
        if delta.total_seconds() >= greylist_timeout:
            logger.debug("greylist check: passed, increasing whitelist hit"
                          " counter")
            cursor.execute("""
INSERT OR IGNORE INTO whitelist (client_name, hit_count) VALUES (?, 0);""",
                           (client_name, ))
            cursor.execute("""
UPDATE whitelist SET last_seen = ?, hit_count = hit_count + 1;""",
                           (now,))
            dbconn.commit()
            return PASSED
        cursor.execute("""UPDATE greylist
        SET last_seen = ?
        WHERE sender=? AND recipient=? AND client_name=?""",
                       (now,) + key)
        dbconn.commit()
        logger.debug("greylist check: defer")
        return FAILED

def process_request(attrs):
    dbconn = get_db()
    cursor = dbconn.cursor()

    try:
        sender = attrs["sender"]
        recipient = attrs["recipient"]
        client_name = attrs["client_name"]

        logger.debug("processing request: sender=%r, recipient=%r, client_name=%r",
                      sender, recipient, client_name)
        if _check_whitelist(cursor, client_name):
            return PASSED

        return _check_greylist(dbconn, cursor, sender, recipient, client_name)
    finally:
        cursor.close()

def setup_db(dbconn):
    try:
        verify_db(dbconn)
        logger.info("database schema verified successfully")
    except ValueError as err:
        logger.warn("database schema has errors: %s", err)
        create_db(dbconn)

def verify_db(dbconn):
    cursor = dbconn.execute("SELECT * FROM SQLITE_MASTER")
    try:
        found = set()
        for type_, name, _, _, sql in cursor:
            if sql is None:
                continue
            try:
                if sql != SCHEMA[(type_, name)]:
                    logger.warn("verifying: sql schema differs. found %r", sql)
                    logger.info("verifying: expected %r", SCHEMA[(type_, name)])
                    raise ValueError("Schema differs")
            except KeyError as err:
                raise ValueError("Unexpected {}: {}".format(type_, err))
            found.add(name)
        missing = set(table
                      for (type_, table) in SCHEMA.keys()
                      if type_ == "table") - found
        if missing:
            raise ValueError("Missing tables: {}".format(", ".join(missing)))
    finally:
        cursor.close()

if __name__ == "__main__":
    import argparse
    import logging
    import sys

    parser = argparse.ArgumentParser(
        description="""Accept Postfix policy check requests on stdin and perform
        greylisting. Returns an action code depending on greylisting result. For
        configuration details please see the comments at the start of
        greylist.py"""
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        type=argparse.FileType("r"),
        metavar="FILE",
        help="Specify a config file to override defaults")
    parser.add_argument(
        "-v",
        dest="verbosity",
        action="count",
        default=0,
        help="Increase verbosity by one step")

    args = parser.parse_args()

    verbosity = {
        0: logging.ERROR,
        1: logging.WARN,
        2: logging.INFO,
        3: logging.DEBUG
    }

    logging.basicConfig(
        level=verbosity.get(args.verbosity, logging.DEBUG),
        stream=sys.stderr)
    logger = logging.getLogger("greylist")

    if args.config is not None:
        load_config(args.config)

    try:
        while True:
            try:
                request = read_request(sys.stdin)
                if request is None:
                    break
                if not request:
                    # ignore empty requests
                    continue
                try:
                    clean_request(request)
                except KeyError as err:
                    raise ValueError("Missing critical attribute: {}".format(err))
            except ValueError as err:
                logger.error("Malformed request: %s", err)
                logger.warn("Returning PASS action")
                print(response_pass)
                continue
            response = process_request(request)
            if response == PASSED:
                print(response_pass)
            elif response == FAILED:
                print(response_fail)
            else:
                raise AssertionError("Programming error")
            # make sure everything is flushed, before doing potentially time
            # consuming GC work
            sys.stdout.flush()
            gc_db()
    except KeyboardInterrupt:
        pass

else:
    # defer configuration of logger until the end
    import logging
    logger = logging.getLogger("greylist")
